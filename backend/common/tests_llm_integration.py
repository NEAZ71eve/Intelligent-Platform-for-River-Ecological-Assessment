"""Cross-app lifecycle and admin verification; all provider responses are synthetic."""
import io
import tempfile
import uuid
from datetime import timedelta
from unittest.mock import patch

from PIL import Image
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import issue_session
from assets.models import Asset
from assets.services import create_asset
from llm.context import build_messages
from llm.models import GatewayConfig, LLMSession, LLMTurn, UsageLedger
from llm.worker import process_one
from recognition.models import RecognitionJob

REPLY = {'text': '模拟上游测试回答：模型候选需要结合实物观察。', 'model': 'deepseek-flash',
         'usage': {'prompt_tokens': 120, 'completion_tokens': 50, 'total_tokens': 170}, 'upstream_id': 'test-only'}


@override_settings(LLM_ENABLED=True, DEEPSEEK_API_KEY='synthetic-key-never-sent', DEEPSEEK_MODEL='deepseek-flash')
class LLMCrossAppTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.directory.name)
        self.override.enable()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.override.disable)
        self.user = User.objects.create_user(username='llm-cross-app', auth_kind='dev')
        token, _ = issue_session(self.user)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        GatewayConfig.objects.update_or_create(pk=1, defaults={'enabled': True})
        image = io.BytesIO()
        Image.new('RGB', (64, 64), '#448855').save(image, 'JPEG')
        self.asset = create_asset(self.user, SimpleUploadedFile('fixture.jpg', image.getvalue(), content_type='image/jpeg'), 'recognition')
        self.job = RecognitionJob.objects.create(owner=self.user, asset=self.asset, status='succeeded',
            expires_at=timezone.now() + timedelta(days=30),
            result={'decision': 'uncertain', 'reason': 'LOW_IMAGE_QUALITY', 'candidates': []})

    def conversation(self, include_image=False):
        response = self.api.post('/api/v1/llm/sessions/', {
            'recognition_job_id': str(self.job.pk), 'include_image': include_image,
            'consent_version': 'deepseek-v1'}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        session = response.json()['data']['id']
        response = self.api.post(f'/api/v1/llm/sessions/{session}/turns/', {
            'request_id': str(uuid.uuid4()), 'question': '测试问题，请解释不确定结果。'}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        return session, response.json()['data']['id']

    def test_health_and_status_share_effective_gate_without_exposing_key(self):
        for value in (False, True):
            with override_settings(LLM_ENABLED=value):
                health = self.api.get('/api/v1/health/')
                state = self.api.get('/api/v1/llm/status/')
                self.assertEqual(health.json()['data']['features']['llm'], value)
                self.assertEqual(state.json()['data']['enabled'], value)
                self.assertNotIn('synthetic-key', state.content.decode())
                self.assertEqual(state.json()['data']['quota']['limit'], 5)
        anonymous = APIClient()
        self.assertIsNone(anonymous.get('/api/v1/llm/status/').json()['data']['quota'])
        self.assertEqual(anonymous.get('/api/v1/llm/sessions/').status_code, 401)

    def test_account_deletion_erases_conversation_but_keeps_anonymous_cost(self):
        self.conversation()
        with patch('llm.worker.provider.generate', return_value=REPLY):
            self.assertTrue(process_one())
        self.assertEqual(self.api.delete('/api/v1/me/').status_code, 204)
        self.assertFalse(LLMSession.objects.exists())
        self.assertFalse(LLMTurn.objects.exists())
        entry = UsageLedger.objects.get()
        self.assertIsNone(entry.owner_id)
        self.assertIsNone(entry.session_id)
        self.assertEqual(entry.accounted_tokens, 170)
        self.assertEqual(entry.status, 'succeeded')

    def test_source_deletion_cancels_queued_conversation(self):
        self.conversation()
        self.assertEqual(self.api.delete(f'/api/v1/recognition-jobs/{self.job.pk}/').status_code, 204)
        self.assertFalse(LLMSession.objects.exists())
        self.assertFalse(LLMTurn.objects.exists())
        self.assertEqual(UsageLedger.objects.get().status, 'failed')
        with patch('llm.worker.provider.generate') as upstream:
            self.assertFalse(process_one())
            upstream.assert_not_called()

    def test_account_deleted_during_call_never_gets_a_late_answer(self):
        self.conversation()

        def reply_after_delete(*args, **kwargs):
            self.assertEqual(self.api.delete('/api/v1/me/').status_code, 204)
            return REPLY

        with patch('llm.worker.provider.generate', side_effect=reply_after_delete):
            self.assertTrue(process_one())
        self.assertFalse(LLMSession.objects.exists())
        self.assertFalse(LLMTurn.objects.exists())
        self.assertEqual(UsageLedger.objects.get().accounted_tokens, 170)

    def test_image_deleted_after_preparation_is_not_sent(self):
        self.conversation(include_image=True)

        def prepare_then_delete(turn):
            result = build_messages(turn)
            self.assertTrue(result[1])
            response = self.api.delete(f'/api/v1/uploads/{self.asset.pk}/')
            self.assertEqual(response.status_code, 204)
            return result

        with patch('llm.worker.build_messages', side_effect=prepare_then_delete), patch('llm.worker.provider.generate') as upstream:
            self.assertTrue(process_one())
            upstream.assert_not_called()
        self.assertEqual(LLMTurn.objects.get().status, 'failed')

    def test_existing_cleanup_command_removes_expired_ai_text_not_today_budget(self):
        session, _ = self.conversation()
        with patch('llm.worker.provider.generate', return_value=REPLY):
            process_one()
        LLMSession.objects.filter(pk=session).update(expires_at=timezone.now() - timedelta(seconds=1))
        call_command('cleanup_private_data', dry_run=True, stdout=io.StringIO())
        self.assertTrue(LLMSession.objects.filter(pk=session).exists())
        call_command('cleanup_private_data', stdout=io.StringIO())
        self.assertFalse(LLMSession.objects.filter(pk=session).exists())
        self.assertEqual(UsageLedger.objects.get().status, 'succeeded')
        self.assertEqual(self.api.get('/api/v1/llm/status/').json()['data']['quota']['remaining'], 4)

    def test_admin_view_permission_cannot_change_gate_or_read_key(self):
        staff = User.objects.create_user(username='llm-viewer', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='llm', codename='view_gatewayconfig'))
        self.client.force_login(staff)
        url = '/admin/llm/gatewayconfig/1/change/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('synthetic-key', response.content.decode())
        self.assertEqual(self.client.post(url, {'enabled': '', '_save': '保存'}).status_code, 403)
        self.assertTrue(GatewayConfig.objects.get(pk=1).enabled)

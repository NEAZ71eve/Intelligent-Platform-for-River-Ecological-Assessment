"""Gateway behavior tests use an isolated DB and mocked upstream, never a real key."""
import base64
import io
import json
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from PIL import Image
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from assessments.models import AssessmentJob
from assets.models import Asset
from assets.services import create_asset
from common.exceptions import ServiceError
from common.models import TaskLog
from knowledge.models import Content
from recognition.models import RecognitionJob
from .context import build_messages, text_bytes
from .models import GatewayConfig, LLMSession, LLMTurn, UsageLedger
from .provider import ProviderError
from .services import (CONSENT_VERSION, cleanup_expired, create_session, delete_session, enqueue_turn,
                       get_config, quota)
from .worker import _claim, process_one, recover_stale_jobs

RESPONSE = {'text': '这是模型候选，需结合叶片与花序核实。', 'model': 'deepseek-flash',
            'usage': {'prompt_tokens': 120, 'completion_tokens': 40, 'total_tokens': 160}, 'upstream_id': 'do-not-store'}


class Fixture:
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory(prefix='hyhq-llm-test-')
        self.addCleanup(self.tmp.cleanup)
        self.overrides = override_settings(LLM_ENABLED=True, DEEPSEEK_API_KEY='not-a-real-key-for-mocked-tests',
                                          LLM_DAILY_TURN_LIMIT=5, MEDIA_ROOT=Path(self.tmp.name),
                                          LLM_QUEUE_TIMEOUT_SECONDS=300, LLM_RETENTION_DAYS=30)
        self.overrides.enable()
        self.addCleanup(self.overrides.disable)
        self.config = GatewayConfig.objects.create(enabled=True)
        self.user = User.objects.create_user(username='llm-owner')
        self.other = User.objects.create_user(username='llm-other')
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def job(self, owner=None, image=False, kind='recognition', **extra):
        owner = owner or self.user
        asset = None
        if image:
            data = io.BytesIO()
            picture = Image.new('RGB', (100, 80), 'green')
            picture.save(data, 'JPEG')
            asset = create_asset(owner, SimpleUploadedFile('image.jpg', data.getvalue(), 'image/jpeg'), 'recognition')
        common = {'owner': owner, 'status': 'succeeded', 'asset': asset, 'expires_at': timezone.now() + timedelta(days=30), **extra}
        if kind == 'assessment':
            return AssessmentJob.objects.create(**common, decision='uncertain', reason='NO_SUPPORTED_DETECTIONS',
                                                latitude=39.91234, longitude=116.31234, coordinate_system='GCJ02')
        return RecognitionJob.objects.create(**common, result={'decision': 'uncertain', 'reason': 'LOW_IMAGE_QUALITY',
                                                              'candidates': [{'label': 'daisy', 'name': '雏菊类', 'score': 0.6}]})

    def session(self, owner=None, image=False, kind='recognition', **extra):
        owner = owner or self.user
        job = self.job(owner, image=image, kind=kind, **extra)
        return create_session(owner, {f'{kind}_job_id': job.pk, 'consent_version': CONSENT_VERSION, 'include_image': image})

    def turn(self, session=None, owner=None, question='如何核实这个结果？', request_id=None):
        owner = owner or self.user
        session = session or self.session(owner)
        return enqueue_turn(owner, session.pk, {'request_id': request_id or uuid.uuid4(), 'question': question})[0]

    def complete(self, turn=None):
        turn = turn or self.turn()
        with patch('llm.worker.provider.generate', return_value=RESPONSE) as provider:
            self.assertTrue(process_one())
        turn.refresh_from_db()
        self.assertEqual(turn.status, 'succeeded')
        return turn, provider


class GatewayTests(Fixture, TestCase):
    def test_status_public_contains_no_private_quota_or_secret(self):
        self.complete()
        public = APIClient().get('/api/v1/llm/status/').json()['data']
        self.assertTrue(public['enabled'])
        self.assertIsNone(public['quota'])
        self.assertNotIn('not-a-real-key', json.dumps(public))
        private = self.api.get('/api/v1/llm/status/').json()['data']
        self.assertEqual(private['quota']['used'], 1)
        self.assertEqual(private['quota']['remaining'], 4)
        self.assertTrue(private['quota']['reset_at'].endswith('+08:00'))
        with override_settings(DEEPSEEK_API_KEY=''):
            self.assertFalse(self.api.get('/api/v1/llm/status/').json()['data']['enabled'])
        with override_settings(LLM_DAILY_TURN_LIMIT=3):
            self.assertEqual(quota(self.user)['limit'], 3)

    def test_create_requires_login_exactly_one_own_complete_source_and_consent(self):
        job = self.job()
        data = {'recognition_job_id': str(job.pk), 'include_image': False, 'consent_version': CONSENT_VERSION}
        self.assertEqual(APIClient().post('/api/v1/llm/sessions/', data).status_code, 401)
        self.assertEqual(self.api.post('/api/v1/llm/sessions/', {**data, 'consent_version': 'old'}).status_code, 400)
        self.assertEqual(self.api.post('/api/v1/llm/sessions/', {**data, 'assessment_job_id': str(uuid.uuid4())}).status_code, 400)
        self.assertEqual(self.api.post('/api/v1/llm/sessions/', {**data, 'recognition_job_id': str(self.job(self.other).pk)}).status_code, 404)
        RecognitionJob.objects.filter(pk=job.pk).update(status='running')
        self.assertEqual(self.api.post('/api/v1/llm/sessions/', data).status_code, 409)
        RecognitionJob.objects.filter(pk=job.pk).update(status='succeeded', expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.api.post('/api/v1/llm/sessions/', data).status_code, 409)
        self.assertFalse(LLMSession.objects.exists())

    def test_result_only_session_does_not_require_original_and_counts_first_turn(self):
        session = self.session()
        response = self.api.get(f'/api/v1/llm/sessions/{session.pk}/').json()['data']
        self.assertFalse(response['image_available'])
        self.assertEqual(response['recognition_job_id'], str(session.recognition_job_id))
        self.assertEqual(quota(self.user)['used'], 0)
        turn, mocked = self.complete(self.turn(session))
        messages = mocked.call_args.args[0]
        self.assertIn('本轮无图片', json.dumps(messages, ensure_ascii=False))
        self.assertFalse(turn.used_image)
        self.assertEqual(quota(self.user)['used'], 1)

    def test_user_ownership_and_pagination_of_sessions_turns(self):
        own = self.session()
        turn = self.turn(own)
        other = self.session(self.other)
        other_turn = self.turn(other, self.other)
        response = self.api.get('/api/v1/llm/sessions/').json()
        self.assertEqual(response['meta']['count'], 1)
        self.assertEqual(response['data'][0]['id'], str(own.pk))
        for endpoint in [f'sessions/{other.pk}/', f'sessions/{other.pk}/turns/', f'turns/{other_turn.pk}/']:
            self.assertEqual(self.api.get('/api/v1/llm/' + endpoint).status_code, 404)
        self.assertEqual(self.api.delete(f'/api/v1/llm/sessions/{other.pk}/').status_code, 404)
        self.assertEqual(self.api.get(f'/api/v1/llm/turns/{turn.pk}/').status_code, 200)

    def test_idempotent_replay_and_changed_question_or_session_conflict(self):
        session = self.session()
        request_id = uuid.uuid4()
        data = {'request_id': str(request_id), 'question': '请解读'}
        url = f'/api/v1/llm/sessions/{session.pk}/turns/'
        first = self.api.post(url, data)
        duplicate = self.api.post(url, data)
        self.assertEqual((first.status_code, duplicate.status_code), (201, 200))
        self.assertEqual(first.json()['data']['id'], duplicate.json()['data']['id'])
        changed = self.api.post(url, {**data, 'question': '另一问题'})
        self.assertEqual(changed.json()['error']['code'], 'REQUEST_ID_CONFLICT')
        other_session = self.session()
        changed = self.api.post(f'/api/v1/llm/sessions/{other_session.pk}/turns/', data)
        self.assertEqual(changed.status_code, 409)
        self.complete(LLMTurn.objects.get())
        with override_settings(LLM_ENABLED=False):
            self.assertEqual(self.api.post(url, data).status_code, 200)
        self.assertEqual(UsageLedger.objects.count(), 1)

    def test_five_round_cap_shared_across_sessions_and_survives_delete(self):
        for _ in range(5):
            turn, _ = self.complete()
            delete_session(self.user, turn.session_id)
        self.assertEqual(quota(self.user)['used'], 5)
        with self.assertRaises(ServiceError) as caught:
            self.turn()
        self.assertEqual(caught.exception.get_codes(), 'LLM_DAILY_LIMIT')
        self.assertEqual(UsageLedger.objects.count(), 5)
        self.assertFalse(LLMTurn.objects.exists())

    def test_one_active_turn_per_user_and_input_bounds(self):
        session = self.session()
        self.turn(session)
        with self.assertRaises(ServiceError) as caught:
            self.turn(self.session())
        self.assertEqual(caught.exception.get_codes(), 'LLM_USER_BUSY')
        url = f'/api/v1/llm/sessions/{session.pk}/turns/'
        for text in ['', '  ', '字' * 501]:
            self.assertEqual(self.api.post(url, {'question': text, 'request_id': str(uuid.uuid4())}).status_code, 400)

    def test_day_is_beijing_admission_day_even_if_finished_next_day(self):
        before = datetime(2026, 9, 20, 15, 59, 50, tzinfo=dt_timezone.utc)
        after = before + timedelta(seconds=20)
        with patch('llm.services.timezone.now', return_value=before):
            session = self.session()
            turn = self.turn(session)
        with patch('llm.services.timezone.now', return_value=after):
            self.complete(turn)
            self.assertEqual(quota(self.user)['remaining'], 5)
            self.assertEqual(quota(self.user)['date'], '2026-09-21')
        turn.ledger.refresh_from_db()
        self.assertEqual(turn.ledger.day.isoformat(), '2026-09-20')

    def test_failed_and_ambiguous_calls_refund_success_but_count_attempts(self):
        for index in range(10):
            turn = self.turn()
            ambiguous = index % 2 == 0
            with patch('llm.worker.provider.generate', side_effect=ProviderError('LLM_TIMEOUT', '请求超时', ambiguous=ambiguous)) as mocked:
                process_one()
            mocked.assert_called_once()
            turn.refresh_from_db()
            self.assertEqual(turn.status, 'failed')
            entry = UsageLedger.objects.get(pk=turn.ledger_id)
            self.assertEqual(entry.accounted_tokens, entry.reserved_tokens if ambiguous else 0)
        self.assertEqual(quota(self.user)['remaining'], 5)
        with self.assertRaises(ServiceError) as caught:
            self.turn()
        self.assertEqual(caught.exception.get_codes(), 'LLM_ATTEMPT_LIMIT')

    def test_global_budget_reserves_full_input_and_known_usage_settles_exactly(self):
        self.config.global_daily_token_limit = 33400
        self.config.save()
        first = self.turn()
        with self.assertRaises(ServiceError) as caught:
            self.turn(owner=self.other)
        self.assertEqual(caught.exception.get_codes(), 'LLM_BUDGET_LIMIT')
        self.complete(first)
        self.config.global_daily_token_limit = 33600
        self.config.save()
        self.turn(owner=self.other)

    def test_global_attempt_and_queue_limits_are_enforced(self):
        self.config.queue_limit = 1
        self.config.save()
        turn = self.turn()
        with self.assertRaises(ServiceError) as caught:
            self.turn(owner=self.other)
        self.assertEqual(caught.exception.get_codes(), 'LLM_QUEUE_FULL')
        self.complete(turn)
        self.config.global_daily_attempt_limit = 1
        self.config.save()
        with self.assertRaises(ServiceError) as caught:
            self.turn(owner=self.other)
        self.assertEqual(caught.exception.get_codes(), 'LLM_GLOBAL_LIMIT')

    def test_actual_usage_above_reservation_is_recorded_and_stops_later_budget(self):
        self.config.global_daily_token_limit = 40000
        self.config.save()
        turn = self.turn()
        response = {**RESPONSE, 'usage': {'prompt_tokens': 50000, 'completion_tokens': 100, 'total_tokens': 50100}}
        with patch('llm.worker.provider.generate', return_value=response):
            process_one()
        self.assertEqual(UsageLedger.objects.get(pk=turn.ledger_id).accounted_tokens, 50100)
        with self.assertRaises(ServiceError) as caught:
            self.turn()
        self.assertEqual(caught.exception.get_codes(), 'LLM_BUDGET_LIMIT')

    def test_switching_off_after_queue_never_contacts_provider(self):
        turn = self.turn()
        self.config.enabled = False
        self.config.save()
        with patch('llm.worker.provider.generate') as mocked:
            process_one()
        mocked.assert_not_called()
        turn.refresh_from_db()
        self.assertEqual(turn.error_code, 'LLM_DISABLED')
        self.assertEqual(quota(self.user)['remaining'], 5)
        for overrides in [{'LLM_ENABLED': False}, {'DEEPSEEK_API_KEY': ''}]:
            with override_settings(**overrides), self.assertRaises(ServiceError):
                self.session()

    def test_expired_image_fails_opt_in_create_then_existing_session_falls_back(self):
        session = self.session(image=True)
        Asset.objects.filter(pk=session.recognition_job.asset_id).update(original_expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ServiceError) as caught:
            create_session(self.user, {'recognition_job_id': session.recognition_job_id,
                                      'consent_version': CONSENT_VERSION, 'include_image': True})
        self.assertEqual(caught.exception.get_codes(), 'IMAGE_UNAVAILABLE')
        turn, mocked = self.complete(self.turn(session))
        self.assertFalse(turn.used_image)
        self.assertNotIn('data:image', json.dumps(mocked.call_args.args[0]))

    def test_image_reencoded_and_location_model_secrets_not_sent(self):
        session = self.session(image=True, kind='assessment')
        turn, mocked = self.complete(self.turn(session))
        messages = mocked.call_args.args[0]
        wire = json.dumps(messages, ensure_ascii=False)
        self.assertTrue(turn.used_image)
        self.assertNotIn('39.91234', wire)
        self.assertNotIn('116.31234', wire)
        self.assertNotIn(str(self.user.pk), wire)
        self.assertNotIn('latitude', wire)
        image_url = messages[-1]['content'][1]['image_url']['url']
        with Image.open(io.BytesIO(base64.b64decode(image_url.split(',')[1]))) as picture:
            self.assertFalse(picture.getexif())
            self.assertLessEqual(max(picture.size), 512)
        self.assertLessEqual(text_bytes(messages), 16384)
        self.assertNotIn('do-not-store', json.dumps(UsageLedger.objects.get(pk=turn.ledger_id).usage))

    def test_only_published_related_knowledge_is_forwarded(self):
        Content.objects.create(title='可引用雏菊', slug='llm-pub', body='核实叶片', status='published', plant_label='daisy', source='测试科普来源')
        Content.objects.create(title='草稿秘密', slug='llm-draft', body='不应发出', status='draft', plant_label='daisy')
        Content.objects.create(title='无关文章', slug='llm-other', body='不应发出', status='published', plant_label='tulips')
        _, mocked = self.complete()
        text = json.dumps(mocked.call_args.args[0], ensure_ascii=False)
        self.assertIn('可引用雏菊', text)
        self.assertIn('测试科普来源', text)
        self.assertNotIn('草稿秘密', text)
        self.assertNotIn('无关文章', text)
        self.assertIn('uncertain', text)

    def test_session_or_source_deleted_during_call_is_not_resurrected(self):
        for source in [False, True]:
            turn = self.turn()
            entry_id = turn.ledger_id
            def delete_while_calling(*args, **kwargs):
                if source:
                    RecognitionJob.objects.filter(pk=turn.session.recognition_job_id).delete()
                else:
                    delete_session(self.user, turn.session_id)
                return RESPONSE
            with patch('llm.worker.provider.generate', side_effect=delete_while_calling):
                process_one()
            self.assertFalse(LLMTurn.objects.filter(pk=turn.pk).exists())
            self.assertEqual(UsageLedger.objects.get(pk=entry_id).accounted_tokens, 160)
            self.assertEqual(quota(self.user)['remaining'], 5)

    def test_account_deleted_during_call_keeps_anonymous_budget_only(self):
        turn = self.turn()
        entry_id = turn.ledger_id
        def delete_account(*args, **kwargs):
            self.user.delete()
            return RESPONSE
        with patch('llm.worker.provider.generate', side_effect=delete_account):
            process_one()
        entry = UsageLedger.objects.get(pk=entry_id)
        self.assertIsNone(entry.owner_id)
        self.assertIsNone(entry.session_id)
        self.assertEqual(entry.accounted_tokens, 160)
        self.assertFalse(LLMSession.objects.exists())
        self.assertFalse(LLMTurn.objects.exists())

    def test_deleted_or_deactivated_authenticated_owner_rejected(self):
        session = self.session()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(ServiceError) as caught:
            self.turn(session)
        self.assertEqual(caught.exception.status_code, 401)
        with self.assertRaises(ServiceError):
            create_session(self.user, {'recognition_job_id': session.recognition_job_id,
                                      'consent_version': CONSENT_VERSION, 'include_image': False})
        User.objects.filter(pk=self.user.pk).delete()
        with self.assertRaises(ServiceError):
            enqueue_turn(self.user, session.pk, {'request_id': uuid.uuid4(), 'question': '测试'})

    def test_deleted_running_session_keeps_slot_until_settled_and_queued_releases(self):
        turn = self.turn()
        _claim()
        delete_session(self.user, turn.session_id)
        self.assertEqual(UsageLedger.objects.get(pk=turn.ledger_id).status, 'running')
        with self.assertRaises(ServiceError) as caught:
            self.turn()
        self.assertEqual(caught.exception.get_codes(), 'LLM_USER_BUSY')
        UsageLedger.objects.filter(pk=turn.ledger_id).update(lease_until=timezone.now() - timedelta(seconds=1))
        recover_stale_jobs()
        queued = self.turn()
        delete_session(self.user, queued.session_id)
        self.assertEqual(UsageLedger.objects.get(pk=queued.ledger_id).status, 'failed')
        self.assertEqual(quota(self.user)['remaining'], 5)

    def test_stale_recovery_is_conservative_and_does_not_touch_active_lease(self):
        turn = self.turn()
        _claim()
        self.assertEqual(recover_stale_jobs(), 0)
        UsageLedger.objects.filter(pk=turn.ledger_id).update(dispatched=True, lease_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(recover_stale_jobs(), 1)
        entry = UsageLedger.objects.get(pk=turn.ledger_id)
        self.assertTrue(entry.usage_estimated)
        self.assertEqual(entry.accounted_tokens, entry.reserved_tokens)
        queued = self.turn()
        UsageLedger.objects.filter(pk=queued.ledger_id).update(created_at=timezone.now() - timedelta(minutes=6))
        self.assertEqual(recover_stale_jobs(), 1)
        self.assertEqual(UsageLedger.objects.get(pk=queued.ledger_id).accounted_tokens, 0)

    def test_cleanup_dry_run_preserves_private_data_then_removes_expired_sessions(self):
        turn, _ = self.complete()
        LLMSession.objects.filter(pk=turn.session_id).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(cleanup_expired(dry_run=True)['sessions'], 1)
        self.assertTrue(LLMTurn.objects.exists())
        cleanup_expired()
        self.assertFalse(LLMTurn.objects.exists())
        self.assertEqual(quota(self.user)['used'], 1)
        UsageLedger.objects.update(day=timezone.now().date() - timedelta(days=40))
        self.assertEqual(cleanup_expired()['ledger_rows'], 1)
        self.assertFalse(UsageLedger.objects.exists())

    def test_admin_viewer_cannot_change_gateway_and_secret_is_never_displayed(self):
        staff = User.objects.create_user(username='llm-viewer', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='llm', codename='view_gatewayconfig'))
        self.client.force_login(staff)
        url = '/admin/llm/gatewayconfig/1/change/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'not-a-real-key-for-mocked-tests')
        self.assertEqual(self.client.post(url, {'enabled': False}).status_code, 403)
        self.config.refresh_from_db()
        self.assertTrue(self.config.enabled)

    def test_image_expires_after_context_preparation_never_goes_to_provider(self):
        session = self.session(image=True)
        turn = self.turn(session)
        original_builder = build_messages
        def expire_after_build(current):
            messages = original_builder(current)
            Asset.objects.filter(pk=session.recognition_job.asset_id).update(original_expires_at=timezone.now() - timedelta(seconds=1))
            return messages
        with patch('llm.worker.build_messages', side_effect=expire_after_build), patch('llm.worker.provider.generate') as mocked:
            process_one()
        mocked.assert_not_called()
        turn.refresh_from_db()
        self.assertEqual(turn.error_code, 'IMAGE_UNAVAILABLE')
        self.assertEqual(turn.ledger.accounted_tokens, 0)

    def test_deactivating_queued_owner_stops_dispatch(self):
        turn = self.turn()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        with patch('llm.worker.provider.generate') as mocked:
            process_one()
        mocked.assert_not_called()
        turn.refresh_from_db()
        self.assertEqual(turn.error_code, 'SOURCE_UNAVAILABLE')

    def test_only_successful_bounded_history_is_assembled_server_side(self):
        session = self.session()
        first = self.turn(session, question='第一轮花卉问题')
        self.complete(first)
        second = self.turn(session, question='失败问题不会作为历史')
        with patch('llm.worker.provider.generate', side_effect=ProviderError('LLM_PROVIDER_RATE_LIMIT', '稍后再试')):
            process_one()
        third = self.turn(session, question='继续核实')
        messages, _ = build_messages(third)
        text = json.dumps(messages, ensure_ascii=False)
        self.assertIn('第一轮花卉问题', text)
        self.assertIn(RESPONSE['text'], text)
        self.assertNotIn('失败问题不会作为历史', text)
        self.assertLessEqual(text_bytes(messages), 16384)
        self.assertEqual(messages[-1]['content'], '继续核实')

    def test_known_usage_on_incomplete_response_charged_without_success_round(self):
        turn = self.turn()
        with patch('llm.worker.provider.generate', side_effect=ProviderError('LLM_RESPONSE_INCOMPLETE', '未完整生成',
                   ambiguous=True, usage=RESPONSE['usage'])) as mocked:
            process_one()
        mocked.assert_called_once()
        entry = UsageLedger.objects.get(pk=turn.ledger_id)
        self.assertEqual(entry.accounted_tokens, 160)
        self.assertFalse(entry.usage_estimated)
        self.assertEqual(quota(self.user)['used'], 0)

    def test_logs_and_ledger_never_store_question_response_or_upstream_id(self):
        turn, _ = self.complete()
        entry = UsageLedger.objects.get(pk=turn.ledger_id)
        logged = str(entry.__dict__) + str(list(TaskLog.objects.values()))
        self.assertNotIn(turn.question, logged)
        self.assertNotIn(turn.answer, logged)
        self.assertNotIn('do-not-store', logged)


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL row locking is required for concurrency checks')
class ConcurrencyTests(Fixture, TransactionTestCase):
    def test_parallel_last_available_round_admits_exactly_one(self):
        session = self.session()
        for _ in range(4):
            self.complete(self.turn(session))
        barrier = Barrier(6)
        def submit(_):
            close_old_connections()
            try:
                owner = User.objects.get(pk=self.user.pk)
                barrier.wait(timeout=10)
                try:
                    return enqueue_turn(owner, session.pk, {'request_id': uuid.uuid4(), 'question': '最后一回合'})[0].status
                except ServiceError as exc:
                    return str(exc.get_codes())
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = list(pool.map(submit, range(6)))
        self.assertEqual(outcomes.count('queued'), 1)
        self.assertEqual(quota(self.user)['used'] + quota(self.user)['reserved'], 5)
        with patch('llm.worker.provider.generate', return_value=RESPONSE):
            process_one()
        self.assertEqual(quota(self.user)['used'], 5)
        with self.assertRaises(ServiceError) as caught:
            self.turn(session)
        self.assertEqual(caught.exception.get_codes(), 'LLM_DAILY_LIMIT')

    def test_parallel_workers_claim_at_most_global_concurrency(self):
        for index in range(4):
            owner = User.objects.create_user(username=f'concurrent-owner-{index}')
            self.turn(owner=owner)
        barrier = Barrier(4)
        def claim(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return bool(_claim())
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(claim, range(4)))
        self.assertEqual(sum(outcomes), 2)
        self.assertEqual(UsageLedger.objects.filter(status='running').count(), 2)

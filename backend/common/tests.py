import hashlib
import io
import logging
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AuthSession, User
from accounts.services import issue_session
from activity.models import Favorite, History
from assets.models import Asset
from common.logging import RedactFilter
from common.models import AuditLog, TaskLog
from ecology.models import Place
from knowledge.models import Content
from recognition.models import RecognitionJob
from recognition.worker import process_one, recover_stale_jobs


def image_upload(name='test.jpg', metadata=False):
    output = io.BytesIO()
    image = Image.new('RGB', (80, 60), '#72a37b')
    exif = Image.Exif()
    if metadata:
        exif[270] = 'private-location-detail'
    image.save(output, 'JPEG', exif=exif)
    return SimpleUploadedFile(name, output.getvalue(), content_type='image/jpeg')


@override_settings(ENV='development', DEBUG=True, ALLOW_DEV_AUTH=True)
class FoundationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', no_observations=True, stdout=io.StringIO())

    def setUp(self):
        cache.clear()
        self.directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.directory.name)
        self.media_override.enable()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.media_override.disable)
        self.api = APIClient()
        self.user = User.objects.create_user(username='test-person', password=None)
        self.other = User.objects.create_user(username='other-person', password=None)
        self.token, _ = issue_session(self.user)
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        self.place = Place.objects.filter(is_published=True).first()

    def upload(self, purpose='recognition', metadata=False):
        response = self.api.post('/api/v1/uploads/', {'file': image_upload(metadata=metadata), 'purpose': purpose}, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['data']

    def test_public_read_and_contract(self):
        anonymous = APIClient()
        response = anonymous.get('/api/v1/places/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['data']), 12)
        self.assertEqual(payload['meta']['count'], 12)
        self.assertTrue(payload['request_id'])
        self.assertEqual(response['X-Request-ID'], payload['request_id'])
        self.assertEqual(anonymous.get('/api/v1/me/').status_code, 401)

    def test_dev_login_is_gated_and_non_privileged(self):
        client = APIClient()
        response = client.post('/api/v1/auth/dev/', {'device_id': 'development-device-123'})
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        user = User.objects.get(pk=data['user']['id'])
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertNotIn('wechat_openid', data['user'])
        self.assertTrue(AuthSession.objects.filter(user=user, token_digest=hashlib.sha256(data['token'].encode()).hexdigest()).exists())
        self.assertFalse(AuthSession.objects.filter(token_digest=data['token']).exists())
        with override_settings(ALLOW_DEV_AUTH=False):
            self.assertEqual(client.post('/api/v1/auth/dev/', {'device_id': 'development-device-123'}).status_code, 404)
        with override_settings(ENV='production', ALLOW_DEV_AUTH=True, DEBUG=True):
            self.assertEqual(client.post('/api/v1/auth/dev/', {'device_id': 'development-device-123'}).status_code, 404)

    def test_rotation_expiry_and_logout_revoke_access(self):
        new_token, _ = issue_session(self.user)
        self.assertEqual(self.api.get('/api/v1/me/').status_code, 401)
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {new_token}')
        AuthSession.objects.filter(user=self.user).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.api.get('/api/v1/me/').status_code, 401)
        new_token, _ = issue_session(self.user)
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {new_token}')
        self.assertEqual(self.api.post('/api/v1/auth/logout/').status_code, 204)
        self.assertEqual(self.api.get('/api/v1/me/').status_code, 401)

    @override_settings(WECHAT_APP_ID='', WECHAT_APP_SECRET='')
    def test_wechat_without_credentials_is_explicit(self):
        response = self.api.post('/api/v1/auth/wechat/', {'code': 'temporary-code'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'WECHAT_NOT_CONFIGURED')

    @patch('accounts.views.exchange_wechat_code', return_value='synthetic-wechat-openid')
    def test_wechat_adapter_issues_session_without_exposing_openid(self, exchange):
        response = self.api.post('/api/v1/auth/wechat/', {'code': 'one-time-code'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['user']['auth_kind'], 'wechat')
        self.assertNotIn('synthetic-wechat-openid', response.content.decode())
        exchange.assert_called_once_with('one-time-code')

    @override_settings(WECHAT_APP_ID='test', WECHAT_APP_SECRET='not-real-secret')
    @patch('accounts.services.urlopen')
    def test_wechat_invalid_upstream_is_rejected(self, upstream):
        upstream.return_value.__enter__.return_value.read.return_value = b'{"openid":""}'
        response = self.api.post('/api/v1/auth/wechat/', {'code': 'one-time-code'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'WECHAT_CODE_INVALID')

    def test_profile_cannot_elevate_permissions(self):
        response = self.api.patch('/api/v1/me/', {'nickname': '校园访客', 'is_staff': True, 'is_superuser': True, 'wechat_openid': 'attack'})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, '校园访客')
        self.assertFalse(self.user.is_staff or self.user.is_superuser)
        self.assertIsNone(self.user.wechat_openid)

    def test_stale_profile_update_does_not_reenable_history(self):
        from accounts.serializers import UserSerializer
        first = User.objects.get(pk=self.user.pk)
        stale = User.objects.get(pk=self.user.pk)
        privacy = UserSerializer(first, data={'record_history': False}, partial=True)
        privacy.is_valid(raise_exception=True)
        privacy.save()
        nickname = UserSerializer(stale, data={'nickname': '仅修改昵称'}, partial=True)
        nickname.is_valid(raise_exception=True)
        nickname.save()
        self.user.refresh_from_db()
        self.assertFalse(self.user.record_history)
        self.assertEqual(self.user.nickname, '仅修改昵称')

    def test_upload_reencodes_strips_metadata_and_checks_ownership(self):
        data = self.upload(metadata=True)
        asset = Asset.objects.get(pk=data['id'])
        with asset.original.open('rb') as file, Image.open(file) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(len(image.getexif()), 0)
        response = self.api.get(data['thumbnail_url'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        # Consume via Django's test streaming wrapper, which handles request-finished
        # signals without closing the enclosing TestCase transaction connection.
        self.assertTrue(b''.join(response.streaming_content).startswith(b'\xff\xd8'))
        another = APIClient()
        other_token, _ = issue_session(self.other)
        another.credentials(HTTP_AUTHORIZATION=f'Bearer {other_token}')
        self.assertEqual(another.get(data['thumbnail_url']).status_code, 404)
        self.assertEqual(another.delete(f'/api/v1/uploads/{asset.pk}/').status_code, 404)
        self.assertEqual(APIClient().get(data['thumbnail_url']).status_code, 401)
        self.assertEqual(APIClient().get(f'/media/{asset.original.name}').status_code, 404)

    def test_invalid_and_oversized_upload_do_not_leave_files(self):
        response = self.api.post('/api/v1/uploads/', {'file': SimpleUploadedFile('x.jpg', b'not-image'), 'purpose': 'recognition'}, format='multipart')
        self.assertEqual(response.json()['error']['code'], 'INVALID_IMAGE')
        with override_settings(MAX_UPLOAD_BYTES=10):
            response = self.api.post('/api/v1/uploads/', {'file': image_upload()}, format='multipart')
        self.assertEqual(response.status_code, 413)
        self.assertEqual(Asset.objects.count(), 0)
        self.assertEqual(list(Path(self.directory.name).rglob('*.jpg')), [])

    def test_avatar_persists_and_replacement_cleans_previous_files(self):
        first = self.upload('avatar')
        self.assertEqual(self.api.patch('/api/v1/me/', {'avatar_asset_id': first['id']}).status_code, 200)
        self.assertIsNone(Asset.objects.get(pk=first['id']).expires_at)
        second = self.upload('avatar')
        old_paths = [Asset.objects.get(pk=first['id']).original.path, Asset.objects.get(pk=first['id']).thumbnail.path]
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.api.patch('/api/v1/me/', {'avatar_asset_id': second['id']}).status_code, 200)
        self.assertFalse(Asset.objects.filter(pk=first['id']).exists())
        self.assertTrue(all(not Path(path).exists() for path in old_paths))
        self.assertTrue(self.api.get('/api/v1/me/').json()['data']['avatar_url'])

    def test_other_users_asset_cannot_become_avatar_or_job(self):
        data = self.upload('avatar')
        other_token, _ = issue_session(self.other)
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {other_token}')
        self.assertEqual(self.api.patch('/api/v1/me/', {'avatar_asset_id': data['id']}).status_code, 400)
        self.assertEqual(self.api.post('/api/v1/recognition-jobs/', {'asset_id': data['id']}).status_code, 404)

    def test_cleanup_expires_original_then_record_and_thumb(self):
        data = self.upload()
        asset = Asset.objects.get(pk=data['id'])
        original_path, thumb_path = asset.original.path, asset.thumbnail.path
        Asset.objects.filter(pk=asset.pk).update(original_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.api.get(f'/api/v1/uploads/{asset.pk}/content/?variant=original').status_code, 410)
        call_command('cleanup_private_data', dry_run=True, stdout=io.StringIO())
        self.assertTrue(Path(original_path).exists())
        with self.captureOnCommitCallbacks(execute=True):
            call_command('cleanup_private_data', stdout=io.StringIO())
        self.assertFalse(Path(original_path).exists())
        self.assertTrue(Path(thumb_path).exists())
        Asset.objects.filter(pk=asset.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.captureOnCommitCallbacks(execute=True):
            call_command('cleanup_private_data', stdout=io.StringIO())
        self.assertFalse(Path(thumb_path).exists())
        self.assertFalse(Asset.objects.filter(pk=asset.pk).exists())

    def test_queue_deduplicates_and_worker_never_fabricates_prediction(self):
        data = self.upload()
        first = self.api.post('/api/v1/recognition-jobs/', {'asset_id': data['id']})
        second = self.api.post('/api/v1/recognition-jobs/', {'asset_id': data['id']})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['data']['id'], second.json()['data']['id'])
        self.assertTrue(process_one())
        job = RecognitionJob.objects.get(pk=first.json()['data']['id'])
        self.assertEqual(job.status, 'failed')
        self.assertEqual(job.error_code, 'MODEL_NOT_CONFIGURED')
        self.assertEqual(job.result, {})
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.finished_at)
        self.assertTrue(TaskLog.objects.filter(error_code='MODEL_NOT_CONFIGURED').exists())

    @override_settings(RECOGNITION_QUEUE_LIMIT=1)
    def test_queue_capacity_applies_across_users(self):
        first = self.upload()
        self.assertEqual(self.api.post('/api/v1/recognition-jobs/', {'asset_id': first['id']}).status_code, 201)
        other_token, _ = issue_session(self.other)
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {other_token}')
        second = self.upload()
        response = self.api.post('/api/v1/recognition-jobs/', {'asset_id': second['id']})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['error']['code'], 'QUEUE_FULL')

    def test_stale_tasks_recovered_and_job_ownership_enforced(self):
        data = self.upload()
        response = self.api.post('/api/v1/recognition-jobs/', {'asset_id': data['id']})
        job_id = response.json()['data']['id']
        RecognitionJob.objects.filter(pk=job_id).update(status='running', started_at=timezone.now() - timedelta(minutes=10))
        self.assertEqual(recover_stale_jobs(), 1)
        self.assertEqual(RecognitionJob.objects.get(pk=job_id).error_code, 'WORKER_TIMEOUT')
        other_token, _ = issue_session(self.other)
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {other_token}')
        self.assertEqual(self.api.get('/api/v1/recognition-jobs/').json()['data'], [])
        self.assertEqual(self.api.delete(f'/api/v1/recognition-jobs/{job_id}/').status_code, 404)

    def test_favorites_history_and_visits_are_owned_and_idempotent(self):
        target = {'place_id': str(self.place.pk)}
        for endpoint in ('favorites', 'histories', 'visits'):
            first = self.api.post(f'/api/v1/{endpoint}/', target)
            second = self.api.post(f'/api/v1/{endpoint}/', target)
            self.assertEqual(first.status_code, 201, first.content)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(first.json()['data']['id'], second.json()['data']['id'])
            self.assertEqual(first.json()['data']['place']['name'], self.place.name)
        self.api.patch('/api/v1/me/', {'record_history': False})
        self.assertEqual(self.api.post('/api/v1/histories/', target).status_code, 409)
        favorite = Favorite.objects.get(owner=self.user)
        other_token, _ = issue_session(self.other)
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {other_token}')
        self.assertEqual(self.api.get('/api/v1/favorites/').json()['data'], [])
        self.assertEqual(self.api.delete(f'/api/v1/favorites/{favorite.pk}/').status_code, 404)

    def test_draft_cannot_be_recorded_or_leaked_from_old_favorite(self):
        content = Content.objects.filter(status='published').first()
        self.api.post('/api/v1/favorites/', {'content_id': str(content.pk)})
        content.status = 'draft'
        content.save()
        self.assertIsNone(self.api.get('/api/v1/favorites/').json()['data'][0]['content'])
        self.assertEqual(self.api.post('/api/v1/histories/', {'content_id': str(content.pk)}).status_code, 400)

    def test_account_delete_revokes_tokens_and_removes_owned_data(self):
        data = self.upload()
        self.api.post('/api/v1/favorites/', {'place_id': str(self.place.pk)})
        self.api.post('/api/v1/recognition-jobs/', {'asset_id': data['id']})
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.api.delete('/api/v1/me/').status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Asset.objects.exists())
        self.assertFalse(Favorite.objects.exists())
        self.assertFalse(RecognitionJob.objects.exists())
        self.assertEqual(list(Path(self.directory.name).rglob('*.jpg')), [])
        self.assertEqual(self.api.get('/api/v1/me/').status_code, 401)
        self.assertIsNone(AuditLog.objects.get(event='user.deleted').actor_id)

    def test_admin_can_login_and_regular_user_cannot(self):
        admin = User.objects.create_superuser('admin-test', password='TestOnly-Admin-Passphrase-993!')
        self.assertTrue(self.client.login(username=admin.username, password='TestOnly-Admin-Passphrase-993!'))
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/admin/').status_code, 302)

    def test_logs_redact_common_credentials(self):
        record = logging.LogRecord('test', logging.INFO, '', 0, 'token=not-a-real-token password=bad Bearer secret-bearer openid=private', (), None)
        RedactFilter().filter(record)
        for text in ('not-a-real-token', 'password=bad', 'secret-bearer', 'openid=private'):
            self.assertNotIn(text, record.getMessage())

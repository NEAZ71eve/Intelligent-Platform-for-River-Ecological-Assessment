"""Cross-module ownership, capacity and retention regressions for river integration."""
import io
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import issue_session
from assessments.models import AssessmentJob, RuleSet
from assessments.rules import RULE_V1
from assets.models import Asset
from assets.services import create_asset
from recognition.models import QueueControl, RecognitionJob


class AssessmentIntegrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.directory.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = User.objects.create_user(username='river-integration-user', password=None)
        token, _ = issue_session(self.user)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        RuleSet.objects.create(version='integration-v1', definition=RULE_V1, is_active=True)

    def asset(self):
        stream = io.BytesIO()
        Image.new('RGB', (80, 60), 'green').save(stream, 'PNG')
        return create_asset(self.user, SimpleUploadedFile('fixture.png', stream.getvalue(), content_type='image/png'), 'recognition')

    def test_same_upload_cannot_be_shared_between_two_task_types(self):
        for first_path, second_path in [
            ('assessment-jobs/', 'recognition-jobs/'),
            ('recognition-jobs/', 'assessment-jobs/'),
        ]:
            asset = self.asset()
            first = self.api.post('/api/v1/' + first_path, {'asset_id': str(asset.pk)})
            self.assertEqual(first.status_code, 201, first.content)
            second = self.api.post('/api/v1/' + second_path, {'asset_id': str(asset.pk)})
            self.assertEqual(second.status_code, 409, second.content)
            self.assertEqual(second.json()['error']['code'], 'ASSET_IN_USE')
            duplicate = self.api.post('/api/v1/' + first_path, {'asset_id': str(asset.pk)})
            self.assertEqual(duplicate.status_code, 200)
            self.assertEqual(first.json()['data']['id'], duplicate.json()['data']['id'])

    @override_settings(RECOGNITION_QUEUE_LIMIT=1)
    def test_queue_capacity_is_shared_in_both_directions(self):
        first = AssessmentJob.objects.create(owner=self.user, asset=self.asset(), expires_at=timezone.now() + timedelta(days=1))
        response = self.api.post('/api/v1/recognition-jobs/', {'asset_id': str(self.asset().pk)})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['error']['code'], 'QUEUE_FULL')
        first.delete()
        RecognitionJob.objects.create(owner=self.user, asset=self.asset(), expires_at=timezone.now() + timedelta(days=1))
        response = self.api.post('/api/v1/assessment-jobs/', {'asset_id': str(self.asset().pk)})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['error']['code'], 'QUEUE_FULL')

    def test_expiration_cleanup_removes_river_records_and_private_files(self):
        asset = self.asset()
        storage, original, thumbnail = asset.original.storage, asset.original.name, asset.thumbnail.name
        past = timezone.now() - timedelta(seconds=1)
        Asset.objects.filter(pk=asset.pk).update(expires_at=past, original_expires_at=past)
        job = AssessmentJob.objects.create(owner=self.user, asset=asset, expires_at=past)
        call_command('cleanup_private_data', dry_run=True, stdout=io.StringIO())
        self.assertTrue(AssessmentJob.objects.filter(pk=job.pk).exists())
        with self.captureOnCommitCallbacks(execute=True):
            call_command('cleanup_private_data', stdout=io.StringIO())
        self.assertFalse(AssessmentJob.objects.filter(pk=job.pk).exists())
        self.assertFalse(Asset.objects.filter(pk=asset.pk).exists())
        self.assertFalse(storage.exists(original))
        self.assertFalse(storage.exists(thumbnail))

    def test_account_deletion_removes_river_coordinates_jobs_and_assets(self):
        asset = self.asset()
        job = AssessmentJob.objects.create(owner=self.user, asset=asset, latitude=30.25, longitude=120.25,
                                          coordinate_system='GCJ02', expires_at=timezone.now() + timedelta(days=1))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.api.delete('/api/v1/me/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AssessmentJob.objects.filter(pk=job.pk).exists())
        self.assertFalse(Asset.objects.filter(pk=asset.pk).exists())
        self.assertEqual(self.api.get('/api/v1/assessment-jobs/').status_code, 401)


@override_settings(RECOGNITION_QUEUE_LIMIT=1)
class ConcurrentAssessmentQueueTests(TransactionTestCase):
    def test_different_users_and_task_types_cannot_overfill_one_slot(self):
        if connection.vendor != 'postgresql':
            self.skipTest('This regression verifies PostgreSQL row locking.')
        cache.clear()
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            RuleSet.objects.create(version='concurrency-v1', definition=RULE_V1, is_active=True)
            QueueControl.objects.create(name='recognition')
            inputs = []
            for index, endpoint in enumerate(['recognition-jobs/', 'assessment-jobs/']):
                user = User.objects.create_user(username=f'concurrent-river-{index}', password=None)
                token, _ = issue_session(user)
                stream = io.BytesIO()
                Image.new('RGB', (80, 60), 'green').save(stream, 'PNG')
                asset = create_asset(user, SimpleUploadedFile('fixture.png', stream.getvalue(), content_type='image/png'), 'recognition')
                inputs.append((endpoint, token, str(asset.pk)))
            barrier = threading.Barrier(2)

            def submit(item):
                close_old_connections()
                try:
                    endpoint, token, asset_id = item
                    api = APIClient()
                    api.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
                    barrier.wait(timeout=5)
                    response = api.post('/api/v1/' + endpoint, {'asset_id': asset_id})
                    return response.status_code
                finally:
                    connections.close_all()

            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(submit, inputs))
            self.assertEqual(sorted(statuses), [201, 429])
            self.assertEqual(RecognitionJob.objects.count() + AssessmentJob.objects.count(), 1)

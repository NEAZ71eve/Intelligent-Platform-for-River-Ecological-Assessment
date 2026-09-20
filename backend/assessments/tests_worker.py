import copy
import time
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from assets.models import Asset
from recognition.artifacts import ModelError
from recognition.isolation import execution_lock
from .models import AssessmentJob, DetectionModel, RuleSet
from .rules import RULE_V1, activate_rules
from .tests_api import AssessmentFixture
from .worker import _claim, _finish, process_one, recover_stale_jobs


class WorkerTests(AssessmentFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.model = DetectionModel.objects.create(name='test-only', version='v1', enabled=True)
        self.snapshot = {
            'id': str(self.model.pk), 'name': self.model.name, 'version': self.model.version, 'threshold': .4,
            'labels': [{'id': 9, 'name': '漂浮物', 'eval_category': 'floating_debris'}],
            'preprocessing': {'supported_class_ids': [9]},
        }
        snapshot = patch('assessments.worker.snapshot_for', side_effect=lambda model: copy.deepcopy(self.snapshot))
        snapshot.start()
        self.addCleanup(snapshot.stop)
        self.result = {
            'detections': [{'class_id': 9, 'label': '漂浮物', 'eval_category': 'floating_debris', 'confidence': .9,
                            'bbox': [0, 0, 20, 20], 'area_ratio': .05}],
            'image_width': 100, 'image_height': 80, 'decision': 'detected', 'reason': '',
        }

    def job(self):
        return AssessmentJob.objects.create(owner=self.user, asset=self.asset(), rule_set=self.rule,
                                            rule_snapshot=copy.deepcopy(self.rule.definition), rule_version=self.rule.version,
                                            expires_at=timezone.now() + timedelta(days=1))

    def run_job(self, result=None):
        with patch('assessments.worker.run_detection', return_value=copy.deepcopy(self.result if result is None else result)) as runtime:
            self.assertTrue(process_one())
            return runtime

    def test_success_freezes_versions_and_uses_detection_timeout(self):
        job = self.job()
        runtime = self.run_job()
        self.assertEqual(runtime.call_args.args[4], settings.ASSESSMENT_RUN_TIMEOUT_SECONDS)
        job.refresh_from_db()
        self.assertEqual(job.status, 'succeeded')
        self.assertEqual(job.decision, 'assessed')
        self.assertEqual(job.score, 85)
        self.assertEqual(job.image_width, 100)
        self.assertEqual(job.image_height, 80)
        self.assertEqual(job.model_version_id, self.model.pk)
        self.assertEqual(job.model_snapshot, self.snapshot)
        self.assertEqual(job.rule_snapshot, RULE_V1)
        self.model.scope = 'changed'
        with self.assertRaises(ValidationError):
            self.model.save()

    def test_empty_and_low_quality_results_are_uncertain_with_no_score(self):
        for reason in ['NO_SUPPORTED_DETECTIONS', 'LOW_IMAGE_QUALITY']:
            job = self.job()
            self.run_job(dict(self.result, detections=[], decision='uncertain', reason=reason))
            job.refresh_from_db()
            self.assertEqual(job.status, 'succeeded')
            self.assertEqual(job.decision, 'uncertain')
            self.assertEqual(job.reason, reason)
            self.assertIsNone(job.score)

    def test_rule_activation_after_admission_does_not_change_job(self):
        job = self.job()
        definition = copy.deepcopy(RULE_V1)
        definition['floating_debris']['count_steps'][1][1] = 6
        second = RuleSet.objects.create(version='v2', definition=definition)
        activate_rules(second.pk)
        self.run_job()
        job.refresh_from_db()
        self.assertEqual(job.score, 85)
        self.assertEqual(job.rule_version, 'test-v1')

    def test_shared_cpu_lock_prevents_claim(self):
        job = self.job()
        with execution_lock(settings.RECOGNITION_LOCK_PATH) as fd:
            self.assertIsNotNone(fd)
            self.assertFalse(process_one())
        job.refresh_from_db()
        self.assertEqual(job.status, 'queued')

    def test_timeout_and_child_errors_fail_without_score(self):
        job = self.job()
        with patch('assessments.worker.run_detection', side_effect=ModelError('INFERENCE_TIMEOUT')):
            self.assertTrue(process_one())
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertEqual(job.error_code, 'INFERENCE_TIMEOUT')
        self.assertIsNone(job.score)

    def test_recovery_fails_old_running_and_queued_tasks(self):
        running = self.job()
        queued = self.job()
        AssessmentJob.objects.filter(pk=running.pk).update(status='running', started_at=timezone.now())
        AssessmentJob.objects.filter(pk=queued.pk).update(created_at=timezone.now() - timedelta(seconds=settings.RECOGNITION_QUEUE_TIMEOUT_SECONDS + 1))
        self.assertEqual(recover_stale_jobs(), 2)
        running.refresh_from_db()
        queued.refresh_from_db()
        self.assertEqual(running.error_code, 'WORKER_INTERRUPTED')
        self.assertEqual(queued.error_code, 'QUEUE_TIMEOUT')

    def test_deleted_job_is_never_recreated_when_inference_finishes(self):
        job = self.job()
        def delete_during_inference(*args):
            AssessmentJob.objects.filter(pk=job.pk).delete()
            return self.result
        with patch('assessments.worker.run_detection', side_effect=delete_during_inference):
            self.assertTrue(process_one())
        self.assertFalse(AssessmentJob.objects.filter(pk=job.pk).exists())

    def test_deleted_asset_during_inference_cannot_succeed(self):
        job = self.job()
        def delete_during_inference(*args):
            Asset.objects.filter(pk=job.asset_id).delete()
            return self.result
        with patch('assessments.worker.run_detection', side_effect=delete_during_inference):
            self.assertTrue(process_one())
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertEqual(job.error_code, 'ASSET_EXPIRED')

    def test_expired_asset_never_starts_inference(self):
        job = self.job()
        Asset.objects.filter(pk=job.asset_id).update(original_expires_at=timezone.now() - timedelta(seconds=1))
        with patch('assessments.worker.run_detection') as runtime:
            self.assertTrue(process_one())
            runtime.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.error_code, 'ASSET_EXPIRED')

    def test_invalid_or_unsupported_child_output_fails_closed(self):
        for changed in [dict(self.result['detections'][0], class_id=0),
                        dict(self.result['detections'][0], confidence=float('nan')),
                        dict(self.result['detections'][0], eval_category='bloom_blackwater'),
                        dict(self.result['detections'][0], bbox=[0, 0, 101, 20])]:
            job = self.job()
            self.run_job(dict(self.result, detections=[changed]))
            job.refresh_from_db()
            self.assertEqual(job.status, 'failed')
            self.assertIsNone(job.score)

    def test_finish_cannot_overwrite_recovered_failure(self):
        job = self.job()
        claimed = _claim()
        self.assertEqual(claimed.pk, job.pk)
        AssessmentJob.objects.filter(pk=job.pk).update(status='failed', error_code='WORKER_INTERRUPTED')
        _finish(claimed, time.monotonic(), detections=[], assessment={'score': 100})
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertIsNone(job.score)

    def test_missing_model_has_explicit_error(self):
        DetectionModel.objects.update(enabled=False)
        job = self.job()
        with patch('assessments.worker.run_detection') as runtime:
            self.assertTrue(process_one())
            runtime.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.error_code, 'MODEL_NOT_CONFIGURED')

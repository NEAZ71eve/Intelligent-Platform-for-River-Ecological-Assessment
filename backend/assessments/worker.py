"""The assessment queue shares the single host CPU lock with flower inference."""
import math
import time
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from assets.models import Asset
from common.models import TaskLog
from recognition.artifacts import ModelError
from recognition.isolation import execution_lock
from .isolation import run_detection
from .models import AssessmentJob, DetectionModel
from .registry import registry_lock, snapshot_for
from .rules import assess

ERROR_MESSAGES = {
    'MODEL_NOT_CONFIGURED': '河道检测模型暂未启用，请稍后重试',
    'RULE_NOT_CONFIGURED': '图像教学规则暂未启用，请联系管理员',
    'INFERENCE_TIMEOUT': '评估已超时，请换一张图片重试',
    'ASSET_EXPIRED': '图片已过期或被删除，请重新上传',
    'IMAGE_UNAVAILABLE': '图片已过期或无法读取，请重新上传',
    'MODEL_CHECKSUM_MISMATCH': '模型文件校验失败，请联系管理员',
    'MODEL_CONFIG_MISMATCH': '模型配置校验失败，请联系管理员',
}


def _recover_locked():
    now = timezone.now()
    count = AssessmentJob.objects.filter(status='running', started_at__lt=now - timedelta(seconds=settings.ASSESSMENT_RUN_TIMEOUT_SECONDS)).update(
        status='failed', error_code='WORKER_TIMEOUT', message='处理已超时，请重新提交图片', finished_at=now)
    # A surviving child inherits the shared lock; acquiring it proves that child exited.
    count += AssessmentJob.objects.filter(status='running').update(
        status='failed', error_code='WORKER_INTERRUPTED', message='处理进程已中断，请重新提交图片', finished_at=now)
    count += AssessmentJob.objects.filter(status='queued', created_at__lt=now - timedelta(seconds=settings.RECOGNITION_QUEUE_TIMEOUT_SECONDS)).update(
        status='failed', error_code='QUEUE_TIMEOUT', message='排队已超时，请重新提交图片', finished_at=now)
    count += AssessmentJob.objects.filter(status='queued', expires_at__lte=now).update(
        status='failed', error_code='ASSET_EXPIRED', message=ERROR_MESSAGES['ASSET_EXPIRED'], finished_at=now)
    if count:
        TaskLog.objects.create(task='assessment.recovery', status='succeeded', count=count)
    return count


def recover_stale_jobs():
    with execution_lock(settings.RECOGNITION_LOCK_PATH) as lock_fd:
        return 0 if lock_fd is None else _recover_locked()


def _claim():
    with transaction.atomic():
        registry_lock()
        queryset = AssessmentJob.objects.filter(status='queued').order_by('created_at')
        queryset = queryset.select_for_update(skip_locked=True) if connection.features.has_select_for_update_skip_locked else queryset.select_for_update()
        job = queryset.first()
        if job is None:
            return None
        model = DetectionModel.objects.select_for_update().filter(enabled=True).first()
        job.status, job.started_at = 'running', timezone.now()
        if model:
            job.model_version = model
            try:
                job.model_snapshot = snapshot_for(model)
            except ModelError:
                job.model_snapshot = {'invalid': True}
        job.save(update_fields=['status', 'started_at', 'model_version', 'model_snapshot'])
        return job


def _result(job, result):
    """Reject malformed child output and re-check supported heads before scoring."""
    if not isinstance(result, dict) or result.get('decision') not in {'detected', 'uncertain'}:
        raise ModelError('MODEL_OUTPUT_INVALID')
    width, height = result.get('image_width'), result.get('image_height')
    if type(width) is not int or type(height) is not int or not 1 <= width <= 2048 or not 1 <= height <= 2048:
        raise ModelError('MODEL_OUTPUT_INVALID')
    detections = result.get('detections')
    if not isinstance(detections, list) or len(detections) > 300:
        raise ModelError('MODEL_OUTPUT_INVALID')
    labels = {item['id']: item for item in job.model_snapshot['labels']}
    supported = job.model_snapshot['preprocessing']['supported_class_ids']
    for detection in detections:
        if not isinstance(detection, dict) or type(detection.get('class_id')) is not int:
            raise ModelError('MODEL_OUTPUT_INVALID')
        class_id = detection['class_id']
        confidence = detection.get('confidence')
        label = labels.get(class_id, {})
        if class_id not in supported or label.get('eval_category') != 'floating_debris' or detection.get('eval_category') != 'floating_debris':
            raise ModelError('MODEL_OUTPUT_INVALID')
        if not isinstance(confidence, (float, int)) or isinstance(confidence, bool) or not math.isfinite(confidence) or not job.model_snapshot['threshold'] <= confidence <= 1:
            raise ModelError('MODEL_OUTPUT_INVALID')
        detection['label'] = label['name']
    reason = result.get('reason', '')
    if reason not in {'', 'LOW_IMAGE_QUALITY', 'NO_SUPPORTED_DETECTIONS'}:
        raise ModelError('MODEL_OUTPUT_INVALID')
    if result['decision'] == 'uncertain':
        if detections or reason not in {'LOW_IMAGE_QUALITY', 'NO_SUPPORTED_DETECTIONS'}:
            raise ModelError('MODEL_OUTPUT_INVALID')
    elif not detections or reason:
        raise ModelError('MODEL_OUTPUT_INVALID')
    assessed = assess(detections, job.rule_snapshot, width, height, reason=reason)
    assessed.update(image_width=width, image_height=height)
    # Persist a small public schema, never arbitrary child-provided fields.
    cleaned = []
    for detection in detections:
        x1, y1, x2, y2 = detection['bbox']
        cleaned.append({'class_id': detection['class_id'], 'label': detection['label'],
                        'eval_category': 'floating_debris', 'confidence': float(detection['confidence']),
                        'bbox': list(detection['bbox']), 'area_ratio': round((x2 - x1) * (y2 - y1) / (width * height), 6)})
    return cleaned, assessed


def _finish(job, started, *, detections=None, assessment=None, error_code=''):
    duration = int((time.monotonic() - started) * 1000)
    with transaction.atomic():
        current = AssessmentJob.objects.select_for_update().filter(pk=job.pk, status='running').first()
        if current is None:
            return
        now = timezone.now()
        asset = Asset.objects.filter(pk=current.asset_id).first() if current.asset_id else None
        # A concurrent delete/expiry cannot leave a successful result or revive a job.
        if not error_code and (current.expires_at <= now or asset is None or not asset.original or asset.original_expires_at <= now or (asset.expires_at and asset.expires_at <= now)):
            error_code = 'ASSET_EXPIRED'
        status = 'failed' if error_code else 'succeeded'
        assessment = {} if error_code else (assessment or {})
        AssessmentJob.objects.filter(pk=current.pk, status='running').update(
            status=status, detections=[] if error_code else (detections or []), score=assessment.get('score'),
            image_width=assessment.get('image_width'), image_height=assessment.get('image_height'),
            grade=assessment.get('grade', ''), causes=assessment.get('causes', []), issues=assessment.get('issues', {}),
            decision=assessment.get('decision', ''), reason=assessment.get('reason', ''), error_code=error_code,
            message=ERROR_MESSAGES.get(error_code, '评估暂不可用，请重试或联系管理员') if error_code else '',
            finished_at=now, duration_ms=duration)
        TaskLog.objects.create(task='assessment', status=status, error_code=error_code, count=1, duration_ms=duration)


def process_one():
    with execution_lock(settings.RECOGNITION_LOCK_PATH) as lock_fd:
        if lock_fd is None:
            return False
        _recover_locked()
        job = _claim()
        if job is None:
            return False
        started = time.monotonic()
        try:
            if not job.model_version_id:
                raise ModelError('MODEL_NOT_CONFIGURED')
            if job.model_snapshot.get('invalid'):
                raise ModelError('MODEL_CONFIG_INVALID')
            if not job.rule_snapshot or not job.rule_version:
                raise ModelError('RULE_NOT_CONFIGURED')
            asset = Asset.objects.filter(pk=job.asset_id).first() if job.asset_id else None
            now = timezone.now()
            if asset is None or not asset.original or asset.original_expires_at <= now or (asset.expires_at and asset.expires_at <= now) or job.expires_at <= now:
                raise ModelError('ASSET_EXPIRED')
            result = run_detection(job.model_snapshot, asset.original.path,
                                   getattr(settings, 'ASSESSMENT_MODEL_ROOT', settings.RECOGNITION_MODEL_ROOT), settings.MEDIA_ROOT,
                                   settings.ASSESSMENT_RUN_TIMEOUT_SECONDS, lock_fd)
            detections, assessment = _result(job, result)
            _finish(job, started, detections=detections, assessment=assessment)
        except ModelError as exc:
            _finish(job, started, error_code=exc.code)
        except (OSError, ValueError, TypeError, KeyError, ValidationError):
            _finish(job, started, error_code='INFERENCE_FAILED')
        return True

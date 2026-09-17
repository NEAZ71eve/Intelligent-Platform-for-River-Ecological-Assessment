"""One inference at a time on this host; the child never touches the database."""
import time
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from common.models import TaskLog
from knowledge.models import Content
from .artifacts import ModelError
from .isolation import execution_lock, run_child
from .models import ModelVersion, RecognitionJob
from .registry import registry_lock, snapshot_for

ERROR_MESSAGES = {
    'MODEL_NOT_CONFIGURED': '图像识别模型暂未启用，请稍后重试',
    'INFERENCE_TIMEOUT': '识别已超时，请换一张图片重试',
    'ASSET_EXPIRED': '图片已过期或被删除，请重新上传',
    'IMAGE_UNAVAILABLE': '图片已过期或无法读取，请重新上传',
    'MODEL_CHECKSUM_MISMATCH': '模型文件校验失败，请联系管理员',
    'MODEL_CONFIG_MISMATCH': '模型配置校验失败，请联系管理员',
}


def _recover_locked():
    now = timezone.now()
    stale = RecognitionJob.objects.filter(status='running', started_at__lt=now - timedelta(seconds=settings.RECOGNITION_RUN_TIMEOUT_SECONDS))
    count = stale.update(status='failed', error_code='WORKER_TIMEOUT', message='处理已超时，请重新提交图片', finished_at=now)
    # The inherited file lock proves that no compliant old child is still alive.
    count += RecognitionJob.objects.filter(status='running').update(status='failed', error_code='WORKER_INTERRUPTED', message='处理进程已中断，请重新提交图片', finished_at=now)
    count += RecognitionJob.objects.filter(status='queued', created_at__lt=now - timedelta(seconds=settings.RECOGNITION_QUEUE_TIMEOUT_SECONDS)).update(status='failed', error_code='QUEUE_TIMEOUT', message='排队已超时，请重新提交图片', finished_at=now)
    if count:
        TaskLog.objects.create(task='recognition.recovery', status='succeeded', count=count)
    return count


def recover_stale_jobs():
    with execution_lock(settings.RECOGNITION_LOCK_PATH) as lock_fd:
        return 0 if lock_fd is None else _recover_locked()


def _claim():
    with transaction.atomic():
        registry_lock()
        queryset = RecognitionJob.objects.filter(status='queued').order_by('created_at')
        queryset = queryset.select_for_update(skip_locked=True) if connection.features.has_select_for_update_skip_locked else queryset.select_for_update()
        job = queryset.first()
        if job is None:
            return None
        model = ModelVersion.objects.select_for_update().filter(enabled=True).first()
        job.status = 'running'
        job.started_at = timezone.now()
        if model:
            job.model_version = model
            # JSON serialization on save detaches these values from registry edits.
            try:
                job.model_snapshot = snapshot_for(model)
            except ModelError:
                job.model_snapshot = {'invalid': True}
        job.save(update_fields=['status', 'started_at', 'model_version', 'model_snapshot'])
        return job


def _finish(job, started, result=None, error_code=''):
    duration = int((time.monotonic() - started) * 1000)
    status = 'failed' if error_code else 'succeeded'
    with transaction.atomic():
        changed = RecognitionJob.objects.filter(pk=job.pk, status='running').update(
            status=status, result={} if result is None else result, error_code=error_code,
            message=ERROR_MESSAGES.get(error_code, '识别暂不可用，请重试或联系管理员') if error_code else '',
            finished_at=timezone.now(), duration_ms=duration)
        if changed:
            TaskLog.objects.create(task='recognition', status=status, error_code=error_code, count=1, duration_ms=duration)


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
            asset = job.asset
            now = timezone.now()
            if asset is None or not asset.original or asset.original_expires_at <= now or (asset.expires_at and asset.expires_at <= now) or job.expires_at <= now:
                raise ModelError('ASSET_EXPIRED')
            result = run_child(job.model_snapshot, asset.original.path, settings.RECOGNITION_MODEL_ROOT,
                               settings.MEDIA_ROOT, settings.RECOGNITION_RUN_TIMEOUT_SECONDS, lock_fd)
            labels = [candidate['label'] for candidate in result['candidates']]
            contents = {}
            for content in Content.objects.filter(status='published', plant_label__in=labels):
                contents.setdefault(content.plant_label, str(content.pk))
            for candidate in result['candidates']:
                candidate['content_id'] = contents.get(candidate['label'])
            _finish(job, started, result=result)
        except ModelError as exc:
            _finish(job, started, error_code=exc.code)
        except (FileNotFoundError, OSError, ValueError, TypeError, KeyError):
            _finish(job, started, error_code='INFERENCE_FAILED')
        return True

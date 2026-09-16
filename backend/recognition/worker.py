"""M1 queue lifecycle only. Never invent a prediction when no model is installed."""
import time
from datetime import timedelta
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from common.models import TaskLog
from .models import RecognitionJob


def recover_stale_jobs():
    now = timezone.now()
    stale_running = RecognitionJob.objects.filter(status='running', started_at__lt=now - timedelta(seconds=settings.RECOGNITION_RUN_TIMEOUT_SECONDS))
    stale_queued = RecognitionJob.objects.filter(status='queued', created_at__lt=now - timedelta(seconds=settings.RECOGNITION_QUEUE_TIMEOUT_SECONDS))
    count = stale_running.update(status='failed', error_code='WORKER_TIMEOUT', message='处理已超时，请重新提交图片', finished_at=now)
    count += stale_queued.update(status='failed', error_code='QUEUE_TIMEOUT', message='排队已超时，请重新提交图片', finished_at=now)
    if count:
        TaskLog.objects.create(task='recognition.recovery', status='succeeded', count=count)
    return count


def process_one():
    recover_stale_jobs()
    with transaction.atomic():
        queryset = RecognitionJob.objects.filter(status='queued').order_by('created_at')
        queryset = queryset.select_for_update(skip_locked=True) if connection.features.has_select_for_update_skip_locked else queryset.select_for_update()
        job = queryset.first()
        if job is None:
            return False
        job.status = 'running'
        job.started_at = timezone.now()
        job.save(update_fields=['status', 'started_at'])
    started = time.monotonic()
    # M3 supplies an actual inference adapter. Registered metadata alone cannot enable inference.
    duration = int((time.monotonic() - started) * 1000)
    with transaction.atomic():
        changed = RecognitionJob.objects.filter(pk=job.pk, status='running').update(status='failed', error_code='MODEL_NOT_CONFIGURED', message='图像识别模型将在 M3 接入；图片上传与任务流程已验证', finished_at=timezone.now(), duration_ms=duration)
        if changed:
            TaskLog.objects.create(task='recognition', status='failed', error_code='MODEL_NOT_CONFIGURED', count=1, duration_ms=duration)
    return True


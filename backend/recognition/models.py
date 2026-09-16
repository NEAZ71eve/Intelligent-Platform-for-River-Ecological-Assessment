import uuid
from django.conf import settings
from django.db import models


class QueueControl(models.Model):
    """A singleton row serializes queue admission on PostgreSQL."""
    name = models.CharField(primary_key=True, max_length=32, default='recognition')


class ModelVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80)
    version = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False)
    source = models.URLField(blank=True)
    license = models.CharField(max_length=100, blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    labels = models.JSONField(default=list, blank=True)
    preprocessing = models.JSONField(default=dict, blank=True)
    threshold = models.FloatField(default=0.8)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['name', 'version'], name='unique_model_version'), models.CheckConstraint(condition=models.Q(threshold__gte=0, threshold__lte=1), name='model_threshold_range')]
        verbose_name = '模型版本'
        verbose_name_plural = verbose_name


class RecognitionJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    asset = models.ForeignKey('assets.Asset', null=True, blank=True, on_delete=models.SET_NULL)
    model_version = models.ForeignKey(ModelVersion, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=16, default='queued', choices=[(x, x) for x in ['queued', 'running', 'succeeded', 'failed']], db_index=True)
    result = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    message = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['owner', 'asset'], condition=models.Q(asset__isnull=False), name='one_job_per_owner_asset')]
        verbose_name = '识别任务'
        verbose_name_plural = verbose_name

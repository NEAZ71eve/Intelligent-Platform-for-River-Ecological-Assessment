import uuid
from django.core.exceptions import ValidationError
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
    artifact = models.CharField(max_length=500, blank=True)
    config_digest = models.CharField(max_length=64, blank=True)
    scope = models.TextField(blank=True)
    evaluation = models.JSONField(default=dict, blank=True)

    def clean(self):
        super().clean()
        if self.pk and not self._state.adding and RecognitionJob.objects.filter(model_version_id=self.pk).exists():
            from .artifacts import CONFIG_FIELDS
            old = type(self).objects.get(pk=self.pk)
            if any(getattr(old, field) != getattr(self, field) for field in (*CONFIG_FIELDS, 'config_digest')):
                raise ValidationError('已用于识别的模型版本不可修改，请登记新版本。')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} / {self.version}'

    class Meta:
        constraints = [models.UniqueConstraint(fields=['name', 'version'], name='unique_model_version'), models.CheckConstraint(condition=models.Q(threshold__gte=0, threshold__lte=1), name='model_threshold_range'), models.UniqueConstraint(fields=['enabled'], condition=models.Q(enabled=True), name='one_enabled_recognition_model')]
        verbose_name = '模型版本'
        verbose_name_plural = verbose_name


class RecognitionJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    asset = models.ForeignKey('assets.Asset', null=True, blank=True, on_delete=models.SET_NULL)
    model_version = models.ForeignKey(ModelVersion, null=True, blank=True, on_delete=models.SET_NULL)
    model_snapshot = models.JSONField(default=dict, blank=True)
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

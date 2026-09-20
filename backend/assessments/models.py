import math
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction


class DetectionModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80)
    version = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False)
    source = models.URLField(blank=True)
    license = models.CharField(max_length=100, blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    artifact = models.CharField(max_length=500, blank=True)
    labels = models.JSONField(default=list, blank=True)
    preprocessing = models.JSONField(default=dict, blank=True)
    threshold = models.FloatField(default=0.4)
    scope = models.TextField(blank=True)
    evaluation = models.JSONField(default=dict, blank=True)
    config_digest = models.CharField(max_length=64, blank=True)

    def clean(self):
        super().clean()
        if not math.isfinite(self.threshold):
            raise ValidationError({'threshold': '阈值必须是有限数字。'})
        if not self._state.adding and AssessmentJob.objects.filter(model_version_id=self.pk).exists():
            from .artifacts import CONFIG_FIELDS
            old = type(self).objects.get(pk=self.pk)
            if any(getattr(old, field) != getattr(self, field) for field in (*CONFIG_FIELDS, 'config_digest')):
                raise ValidationError('已用于评估的模型版本不可修改，请登记新版本。')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} / {self.version}'

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'version'], name='unique_detection_model_version'),
            models.CheckConstraint(condition=models.Q(threshold__gte=0, threshold__lte=1), name='detection_threshold_range'),
            models.UniqueConstraint(fields=['enabled'], condition=models.Q(enabled=True), name='one_enabled_detection_model'),
        ]
        verbose_name = '河道检测模型版本'
        verbose_name_plural = verbose_name


class RuleSet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.CharField(max_length=32, unique=True)
    definition = models.JSONField()
    is_active = models.BooleanField(default=False)
    notes = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        from .rules import validate_definition
        validate_definition(self.definition)
        if not self._state.adding and self.jobs.exists():
            old = type(self).objects.get(pk=self.pk)
            if old.version != self.version or old.definition != self.definition:
                raise ValidationError('已用于评估的规则不可修改，请创建新版本。')

    def save(self, *args, **kwargs):
        # Serialize edits with admission, which pins this row's definition.
        with transaction.atomic():
            if not self._state.adding:
                type(self).objects.select_for_update().get(pk=self.pk)
            self.full_clean()
            return super().save(*args, **kwargs)

    def __str__(self):
        return f'图像规则分(教学) / {self.version}'

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['is_active'], condition=models.Q(is_active=True), name='one_active_image_ruleset')]
        verbose_name = '图像教学规则版本'
        verbose_name_plural = verbose_name


class AssessmentJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assessment_jobs')
    asset = models.ForeignKey('assets.Asset', null=True, blank=True, on_delete=models.SET_NULL, related_name='assessment_jobs')
    model_version = models.ForeignKey(DetectionModel, null=True, blank=True, on_delete=models.SET_NULL)
    model_snapshot = models.JSONField(default=dict, blank=True)
    rule_set = models.ForeignKey(RuleSet, null=True, blank=True, on_delete=models.SET_NULL, related_name='jobs')
    rule_snapshot = models.JSONField(default=dict, blank=True)
    rule_version = models.CharField(max_length=32, blank=True)
    water_body = models.ForeignKey('ecology.WaterBody', null=True, blank=True, on_delete=models.SET_NULL, related_name='assessment_jobs')
    station = models.ForeignKey('ecology.Station', null=True, blank=True, on_delete=models.SET_NULL, related_name='assessment_jobs')
    latitude = models.FloatField(null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    coordinate_system = models.CharField(max_length=10, blank=True, choices=[('WGS84', 'WGS84'), ('GCJ02', 'GCJ02')])
    status = models.CharField(max_length=16, default='queued', choices=[(x, x) for x in ['queued', 'running', 'succeeded', 'failed']], db_index=True)
    detections = models.JSONField(default=list, blank=True)
    image_width = models.PositiveIntegerField(null=True, blank=True)
    image_height = models.PositiveIntegerField(null=True, blank=True)
    issues = models.JSONField(default=dict, blank=True)
    score = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MaxValueValidator(100)])
    grade = models.CharField(max_length=20, blank=True)
    causes = models.JSONField(default=list, blank=True)
    decision = models.CharField(max_length=20, blank=True)
    reason = models.CharField(max_length=80, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    message = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)

    def clean(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError('经纬度必须成对填写。')
        if self.latitude is not None and self.coordinate_system not in {'GCJ02', 'WGS84'}:
            raise ValidationError({'coordinate_system': '经纬度必须注明 GCJ02 或 WGS84 坐标系。'})
        if any(value is not None and not math.isfinite(value) for value in (self.latitude, self.longitude)):
            raise ValidationError('坐标必须是有限数字。')
        if not self._state.adding:
            old = type(self).objects.get(pk=self.pk)
            for field in ('model_snapshot', 'rule_snapshot', 'rule_version'):
                if getattr(old, field) and getattr(old, field) != getattr(self, field):
                    raise ValidationError('任务模型与规则快照不可修改。')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'asset'], condition=models.Q(asset__isnull=False), name='one_assessment_per_owner_asset'),
            models.CheckConstraint(condition=models.Q(score__isnull=True) | models.Q(score__gte=0, score__lte=100), name='image_rule_score_range'),
        ]
        verbose_name = '河道图像评估任务'
        verbose_name_plural = verbose_name

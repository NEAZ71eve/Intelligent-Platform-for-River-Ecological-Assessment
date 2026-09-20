import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


KINDS = [('weather', '当前天气'), ('air', '当前空气质量'), ('alerts', '当前天气预警')]


class WeatherLocation(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField('名称', max_length=120)
    latitude = models.DecimalField('WGS84 纬度', max_digits=5, decimal_places=2, validators=[MinValueValidator(Decimal('-90')), MaxValueValidator(Decimal('90'))])
    longitude = models.DecimalField('WGS84 经度', max_digits=5, decimal_places=2, validators=[MinValueValidator(Decimal('-180')), MaxValueValidator(Decimal('180'))])
    scope_note = models.CharField('范围说明', max_length=400, default='附近约 1 公里网格的气象资料，不代表校园内实测。')
    coordinate_source = models.CharField('坐标核对来源', max_length=500)
    is_active = models.BooleanField('公开可查询', default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = '天气查询地点'
        verbose_name_plural = verbose_name

    def clean(self):
        if any(not value.is_finite() for value in (self.latitude, self.longitude) if isinstance(value, Decimal)):
            raise ValidationError('坐标必须为有限数值。')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class WeatherMonth(models.Model):
    month = models.CharField(max_length=7, primary_key=True)
    reserved = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-month']
        verbose_name = '天气月度请求账本'
        verbose_name_plural = verbose_name
        constraints = [models.CheckConstraint(condition=models.Q(reserved__lte=30000), name='weather_month_hard_limit')]


class WeatherGate(models.Model):
    """Single locked row serializes budgets across every API worker."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    blocked_until = models.DateTimeField(null=True, blank=True)
    block_reason = models.CharField(max_length=40, blank=True)


class WeatherRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    month = models.ForeignKey(WeatherMonth, on_delete=models.PROTECT, related_name='requests')
    location = models.ForeignKey(WeatherLocation, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10, choices=KINDS)
    point = models.CharField(max_length=30)
    reserved_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=30, default='reserved')
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-reserved_at']
        verbose_name = '天气上游请求记录'
        verbose_name_plural = verbose_name


class WeatherCache(models.Model):
    location = models.ForeignKey(WeatherLocation, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10, choices=KINDS)
    point = models.CharField(max_length=30)
    payload = models.JSONField(null=True, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    retry_at = models.DateTimeField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    last_reason = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['location', 'kind', 'point'], name='weather_cache_unique_point')]
        verbose_name = '天气持久缓存'
        verbose_name_plural = verbose_name

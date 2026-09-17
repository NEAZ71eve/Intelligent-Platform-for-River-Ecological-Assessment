from datetime import timedelta
from uuid import UUID

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.pagination import StandardPagination

from .models import DataSource, MapLayout, Metric, Observation, Place, Region, SimulationRun, Station
from .serializers import DataSourceSerializer, MapSerializer, MetricSerializer, ObservationSerializer, PlaceSerializer, RegionSerializer, StationSerializer


def by_identifier(queryset, value, slug_field="slug"):
    try:
        identifier = UUID(str(value))
    except (ValueError, TypeError):
        return queryset.filter(**{slug_field: value})
    return queryset.filter(pk=identifier)


def resolve_region(request):
    value = request.query_params.get("region", "demo-campus")
    region = by_identifier(Region.objects.all(), value).first()
    if region is None:
        raise NotFound("未找到所选区域，请先初始化示范数据。")
    return region


class PublicList(generics.ListAPIView):
    permission_classes = [AllowAny]
    pagination_class = StandardPagination


class RegionList(PublicList):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer


class PlaceList(PublicList):
    serializer_class = PlaceSerializer

    def get_queryset(self):
        queryset = Place.objects.filter(is_published=True).select_related("region", "water_body")
        if self.request.query_params.get("region"):
            queryset = queryset.filter(region=resolve_region(self.request))
        if kind := self.request.query_params.get("kind"):
            if kind not in Place.Kind.values:
                raise ValidationError({"kind": "无效的地点类型。"})
            queryset = queryset.filter(kind=kind)
        return queryset


class PlaceDetail(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    queryset = Place.objects.filter(is_published=True).select_related("region", "water_body")
    serializer_class = PlaceSerializer


class MapList(PublicList):
    serializer_class = MapSerializer

    def get_queryset(self):
        return MapLayout.objects.filter(region=resolve_region(self.request), is_active=True)


class StationList(PublicList):
    serializer_class = StationSerializer

    def get_queryset(self):
        queryset = Station.objects.filter(is_active=True).filter(Q(place__isnull=True) | Q(place__is_published=True)).select_related("region")
        if self.request.query_params.get("region"):
            queryset = queryset.filter(region=resolve_region(self.request))
        if kind := self.request.query_params.get("kind"):
            if kind not in Station.Kind.values:
                raise ValidationError({"kind": "无效的监测站类型。"})
            queryset = queryset.filter(kind=kind)
        if place := self.request.query_params.get("place"):
            found = by_identifier(Place.objects.filter(is_published=True), place).first()
            if not found:
                raise ValidationError({"place": "无效的地点。"})
            queryset = queryset.filter(place=found)
        return queryset


class MetricList(PublicList):
    queryset = Metric.objects.all()
    serializer_class = MetricSerializer


class SourceList(PublicList):
    queryset = DataSource.objects.filter(is_active=True)
    serializer_class = DataSourceSerializer


def source_queryset(request, queryset):
    """A query selects one source and (for simulation) one successful run, never blends batches."""
    source_type = request.query_params.get("source_type", "simulation")
    if source_type not in DataSource.Kind.values:
        raise ValidationError({"source_type": "仅支持 api、dataset、simulation、manual。"})
    queryset = queryset.filter(source__kind=source_type, source__is_active=True)
    source_value = request.query_params.get("source")
    if source_value:
        source = by_identifier(DataSource.objects.filter(kind=source_type, is_active=True), source_value, "code").first()
        if not source:
            raise ValidationError({"source": "数据源不存在或与 source_type 不一致。"})
        queryset = queryset.filter(source=source)
    if source_type == DataSource.Kind.SIMULATION:
        run_value = request.query_params.get("simulation_run")
        runs = SimulationRun.objects.filter(status="succeeded", observations__in=queryset).distinct()
        if run_value:
            try:
                runs = runs.filter(pk=UUID(run_value))
            except ValueError:
                raise ValidationError({"simulation_run": "批次 ID 必须为 UUID。"})
        else:
            runs = runs.filter(scenario__code=request.query_params.get("scenario", "normal"))
        run = runs.order_by("-created_at").first()
        if run_value and not run:
            raise ValidationError({"simulation_run": "未找到匹配区域及来源的成功批次。"})
        return queryset.filter(simulation_run=run) if run else queryset.none()
    source_ids = list(queryset.order_by().values_list("source_id", flat=True).distinct()[:2])
    if len(source_ids) > 1:
        raise ValidationError({"source": "该范围存在多个数据源，请指定一个 source，避免混合来源。"})
    return queryset


def parse_timestamp(value, field):
    try:
        parsed = parse_datetime(value)
    except (ValueError, TypeError):
        parsed = None
    if parsed is None or timezone.is_naive(parsed):
        raise ValidationError({field: "请提供含时区的 ISO 8601 时间，例如 2026-09-16T00:00:00Z。"})
    return parsed


class ObservationList(PublicList):
    serializer_class = ObservationSerializer

    def get_queryset(self):
        queryset = Observation.objects.select_related("station", "metric", "source").filter(station__is_active=True).filter(Q(station__place__isnull=True) | Q(station__place__is_published=True))
        if self.request.query_params.get("region"):
            queryset = queryset.filter(station__region=resolve_region(self.request))
        if station_value := self.request.query_params.get("station"):
            station = by_identifier(Station.objects.filter(is_active=True), station_value, "code").first()
            if not station:
                raise ValidationError({"station": "监测站不存在。"})
            queryset = queryset.filter(station=station)
        if metric_value := self.request.query_params.get("metric"):
            metric = by_identifier(Metric.objects.all(), metric_value, "code").first()
            if not metric:
                raise ValidationError({"metric": "指标不存在。"})
            queryset = queryset.filter(metric=metric)
        queryset = source_queryset(self.request, queryset)
        latest = queryset.order_by("-observed_at").values_list("observed_at", flat=True).first()
        end = parse_timestamp(self.request.query_params["end"], "end") if "end" in self.request.query_params else (latest + timedelta(seconds=1) if latest else timezone.now())
        start = parse_timestamp(self.request.query_params["start"], "start") if "start" in self.request.query_params else end - timedelta(hours=48)
        if start >= end or end - start > timedelta(days=31):
            raise ValidationError({"start": "查询时间必须递增，且跨度不能超过 31 天。"})
        try:
            limit = int(self.request.query_params.get("limit", 1000))
        except (ValueError, TypeError):
            raise ValidationError({"limit": "点数必须为 1 至 1000 的整数。"})
        if not 1 <= limit <= 1000:
            raise ValidationError({"limit": "点数必须为 1 至 1000 的整数。"})
        return queryset.filter(observed_at__gte=start, observed_at__lt=end).order_by("observed_at", "station__code", "metric__code")[:limit]


class EnvironmentalSummary(APIView):
    permission_classes = [AllowAny]
    station_kind = Station.Kind.WEATHER

    def get(self, request):
        region = resolve_region(request)
        if request.query_params.get("source_type", "simulation") != "simulation":
            raise ValidationError({"source_type": "M1 天气及空气摘要仅启用模拟来源。"})
        queryset = Observation.objects.filter(station__region=region, station__kind=self.station_kind, station__is_active=True).filter(Q(station__place__isnull=True) | Q(station__place__is_published=True)).select_related("station", "metric", "source")
        queryset = source_queryset(request, queryset)
        station_code = queryset.order_by("station__code").values_list("station__code", flat=True).first()
        queryset = queryset.filter(station__code=station_code)
        observed_at = queryset.order_by("-observed_at").values_list("observed_at", flat=True).first()
        rows = list(queryset.filter(observed_at=observed_at)) if observed_at else []
        metrics = [dict(metric_code=row.metric.code, name=row.metric.name, value=row.value, unit=row.unit, quality_status=row.quality_status) for row in rows]
        result = {
            "region": RegionSerializer(region).data,
            "source_type": "simulation", "is_simulated": True,
            "source": DataSourceSerializer(rows[0].source).data if rows else None,
            "station": StationSerializer(rows[0].station).data if rows else None,
            "simulation_run_id": str(rows[0].simulation_run_id) if rows else None,
            "status": "available" if rows else "unavailable",
            "observed_at": observed_at, "metrics": metrics,
            "notice": "模拟展示值，仅用于课程演示，不代表真实监测结果。",
        }
        values = {row.metric.code: row.value for row in rows}
        if self.station_kind == Station.Kind.WEATHER:
            result.update(temperature=values.get("temperature"), humidity=values.get("humidity"), condition="模拟天气")
        else:
            result.update(pm25=values.get("pm25"), pm10=values.get("pm10"), no2=values.get("no2"), aqi=None, aqi_standard=None)
        return Response(result)


class AirQuality(EnvironmentalSummary):
    station_kind = Station.Kind.AIR


class WeatherAlerts(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        region = resolve_region(request)
        return Response({"region": RegionSerializer(region).data, "source_type": "simulation", "is_simulated": True, "status": "not_connected", "observed_at": None, "alerts": [], "notice": "官方气象预警服务尚未接入；空列表不代表当前没有真实预警。"})


class Dashboard(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        region = resolve_region(request)
        queryset = Observation.objects.filter(station__region=region, station__is_active=True).filter(Q(station__place__isnull=True) | Q(station__place__is_published=True)).select_related("station", "metric", "source")
        queryset = source_queryset(request, queryset)
        latest = queryset.order_by("-observed_at").values_list("observed_at", flat=True).first()
        rows = list(queryset.filter(observed_at=latest)) if latest else []
        return Response({
            "region": RegionSerializer(region).data,
            "source_type": request.query_params.get("source_type", "simulation"),
            "is_simulated": request.query_params.get("source_type", "simulation") == "simulation",
            "observed_at": latest,
            "place_count": region.places.filter(is_published=True).count(),
            "station_count": region.stations.filter(is_active=True).count(),
            "observation_count": queryset.count(),
            "latest_observations": ObservationSerializer(rows, many=True).data,
            "notice": "按单一来源和模拟批次展示，无综合生态指数及官方水质评级。",
        })


# 河道生态评估任务（AssessmentJob）API：复用 recognition 的鉴权与 asset 模式
from datetime import timedelta
from django.conf import settings as django_settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from assets.models import Asset
from common.audit import audit
from common.exceptions import ServiceError
from .models import AssessmentJob, RuleSet
from .serializers import (AssessmentJobInput, AssessmentJobSerializer,
                          ASSESSMENT_DISCLAIMER)
from . import geo as _geo


class AssessmentJobList(generics.ListCreateAPIView):
    """GET 列出当前用户未过期任务；POST 入队（asset_id + 经纬度）。"""
    permission_classes = [IsAuthenticated]
    serializer_class = AssessmentJobSerializer

    def get_queryset(self):
        qs = AssessmentJob.objects.filter(
            owner=self.request.user, expires_at__gt=timezone.now())
        if wb := self.request.query_params.get("water_body"):
            qs = qs.filter(water_body_id=wb)
        if status_param := self.request.query_params.get("status"):
            qs = qs.filter(status=status_param)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = AssessmentJobInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            asset = get_object_or_404(
                Asset, pk=serializer.validated_data["asset_id"],
                owner=request.user, purpose="recognition",
                expires_at__gt=timezone.now(),
                original_expires_at__gt=timezone.now())
            existing = AssessmentJob.objects.filter(
                owner=request.user, asset=asset).first()
            if existing:
                return Response(AssessmentJobSerializer(existing).data)
            if AssessmentJob.objects.filter(
                    status__in=["queued", "running"]).count() >= django_settings.RECOGNITION_QUEUE_LIMIT:
                raise ServiceError("等待处理的图片较多，请稍后重试", "QUEUE_FULL", 429)
            lat = serializer.validated_data["latitude"]
            lng = serializer.validated_data["longitude"]
            coord_system = serializer.validated_data.get("coordinate_system") or "WGS84"
            match = _geo.match_water_body(lat, lng)
            active_rule = RuleSet.objects.filter(is_active=True).first()
            rule_version = active_rule.version if active_rule else "v1"
            job = AssessmentJob.objects.create(
                owner=request.user, asset=asset,
                latitude=lat, longitude=lng, coordinate_system=coord_system,
                water_body_id=match["water_body_id"] if match else None,
                station_id=match["station_id"] if match else None,
                rule_set=active_rule, rule_version=rule_version,
                expires_at=timezone.now() + timedelta(days=django_settings.RECORD_RETENTION_DAYS))
            audit("assessment.queued", request.user, job.pk)
        return Response(AssessmentJobSerializer(job).data, status=201)


class AssessmentJobDetail(generics.RetrieveDestroyAPIView):
    """GET 单任务详情；DELETE 同时清理关联 asset。"""
    permission_classes = [IsAuthenticated]
    serializer_class = AssessmentJobSerializer

    def get_queryset(self):
        return AssessmentJob.objects.filter(
            owner=self.request.user, expires_at__gt=timezone.now())

    def perform_destroy(self, instance):
        asset = instance.asset
        with transaction.atomic():
            instance.delete()
            if asset:
                asset.delete()

from datetime import timedelta
from uuid import UUID

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.pagination import StandardPagination

from .models import DataSource, MapLayout, Metric, Observation, Place, Region, Station, WaterBody
from .series import public_stations, select_provenance, single_params
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
        single_params(self.request.query_params, ("region", "kind", "place", "water_body"))
        queryset = public_stations().select_related("region")
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
        if water_body := self.request.query_params.get("water_body"):
            try:
                found = WaterBody.objects.filter(pk=UUID(water_body), place__is_published=True).first()
            except (ValueError, TypeError):
                found = None
            if not found:
                raise ValidationError({"water_body": "无效的公开水体。"})
            queryset = queryset.filter(water_body=found)
        return queryset


class MetricList(PublicList):
    queryset = Metric.objects.all()
    serializer_class = MetricSerializer


class SourceList(PublicList):
    queryset = DataSource.objects.filter(is_active=True)
    serializer_class = DataSourceSerializer


def source_queryset(request, queryset):
    """Share the series provenance contract with legacy lists and summaries."""
    single_params(request.query_params, ("source_type", "source", "scenario", "simulation_run"))
    observations, _, _, _ = select_provenance(request.query_params, observations=queryset)
    return observations


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
        queryset = Observation.objects.select_related("station", "metric", "source").filter(station__in=public_stations())
        if self.request.query_params.get("region"):
            queryset = queryset.filter(station__region=resolve_region(self.request))
        if station_value := self.request.query_params.get("station"):
            station = by_identifier(public_stations(), station_value, "code").first()
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
        queryset = Observation.objects.filter(station__region=region, station__kind=self.station_kind, station__in=public_stations()).select_related("station", "metric", "source")
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
        queryset = Observation.objects.filter(station__region=region, station__in=public_stations()).select_related("station", "metric", "source")
        queryset = source_queryset(request, queryset)
        latest = queryset.order_by("-observed_at").values_list("observed_at", flat=True).first()
        rows = list(queryset.filter(observed_at=latest)) if latest else []
        return Response({
            "region": RegionSerializer(region).data,
            "source_type": request.query_params.get("source_type", "simulation"),
            "is_simulated": request.query_params.get("source_type", "simulation") == "simulation",
            "observed_at": latest,
            "place_count": region.places.filter(is_published=True).count(),
            "station_count": public_stations().filter(region=region).count(),
            "observation_count": queryset.count(),
            "latest_observations": ObservationSerializer(rows, many=True).data,
            "notice": "按单一来源和模拟批次展示，无综合生态指数及官方水质评级。",
        })

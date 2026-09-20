"""Bounded public series; choose provenance before aggregation and preserve gaps."""
import math
from datetime import timedelta
from uuid import UUID

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.pagination import StandardPagination
from .models import DataSource, Metric, Observation, Region, SimulationRun, SimulationScenario, Station
from .serializers import DataSourceSerializer, RegionSerializer, StationSerializer

MAX_RAW_ROWS = 50_000
MAX_METRICS = 9


def public_stations():
    return Station.objects.filter(is_active=True).filter(
        Q(place__isnull=True) | Q(place__is_published=True)
    ).filter(Q(water_body__isnull=True) | Q(water_body__place__is_published=True))


def identifier(queryset, value, code='code'):
    try:
        parsed = UUID(str(value))
    except (ValueError, TypeError):
        return queryset.filter(**{code: value})
    return queryset.filter(pk=parsed)


def region_for(params):
    region = identifier(Region.objects.all(), params.get('region', 'demo-campus'), 'slug').first()
    if not region:
        raise NotFound('未找到所选区域，请先初始化示范数据。')
    return region


def single_params(params, fields):
    for field in fields:
        if len(params.getlist(field)) > 1:
            raise ValidationError({field: '参数只能提供一次。'})


def bounded_int(params, field, default, lower, upper):
    value = str(params.get(field, default))
    if len(value) > len(str(upper)) or not value.isascii() or not value.isdigit() or not lower <= int(value) <= upper:
        raise ValidationError({field: f'必须是 {lower} 至 {upper} 的整数。'})
    return int(value)


def parse_time(value, field):
    try:
        parsed = parse_datetime(value)
    except (ValueError, TypeError):
        parsed = None
    if parsed is None or timezone.is_naive(parsed):
        raise ValidationError({field: '请提供包含时区的 ISO 8601 时间。'})
    return parsed


def explicit_source(params, source_type):
    value = params.get('source')
    if value is None:
        return None
    source = identifier(DataSource.objects.filter(is_active=True, kind=source_type), value).first()
    if not source:
        raise ValidationError({'source': '数据源不存在、未启用或与 source_type 不一致。'})
    return source


def select_provenance(params, station=None, observations=None):
    source_type = params.get('source_type', 'simulation')
    if source_type not in DataSource.Kind.values:
        raise ValidationError({'source_type': '仅支持 api、dataset、simulation、manual。'})
    source = explicit_source(params, source_type)
    if observations is None:
        observations = Observation.objects.filter(station=station)
    observations = observations.filter(source__is_active=True, source__kind=source_type)
    if source:
        observations = observations.filter(source=source)
    run = None
    if source_type == DataSource.Kind.SIMULATION:
        runs = SimulationRun.objects.filter(status='succeeded', source__is_active=True, observations__in=observations).distinct()
        run_id = params.get('simulation_run')
        if run_id is not None:
            try:
                runs = runs.filter(pk=UUID(run_id))
            except (ValueError, TypeError):
                raise ValidationError({'simulation_run': '批次 ID 必须为 UUID。'})
        if run_id is None or 'scenario' in params:
            scenario = params.get('scenario', 'normal')
            if not SimulationScenario.objects.filter(code=scenario).exists():
                raise ValidationError({'scenario': '模拟场景不存在。'})
            runs = runs.filter(scenario__code=scenario)
        if not source and runs.order_by().values('source_id').distinct().count() > 1:
            raise ValidationError({'source': '该站点存在多个匹配来源，请指定 source，避免混合来源。'})
        run = runs.select_related('source').order_by('-created_at', '-pk').first()
        if run_id is not None and not run:
            raise ValidationError({'simulation_run': '未找到匹配站点、来源和场景的成功批次。'})
        if run:
            source = run.source
            observations = observations.filter(source=source, simulation_run=run)
        else:
            observations = observations.none()
    else:
        if 'simulation_run' in params or 'scenario' in params:
            raise ValidationError({'simulation_run': '非模拟来源不接受模拟批次或场景。'})
        source_ids = list(observations.order_by().values_list('source_id', flat=True).distinct()[:2])
        if not source and len(source_ids) > 1:
            raise ValidationError({'source': '该站点存在多个来源，请指定 source，避免混合来源。'})
        if not source and source_ids:
            source = DataSource.objects.get(pk=source_ids[0])
        if source:
            observations = observations.filter(source=source)
    return observations, source_type, source, run


def window_for(params, observations):
    explicit_window = 'start' in params or 'end' in params
    if explicit_window:
        if 'start' not in params or 'end' not in params or 'hours' in params:
            raise ValidationError({'start': '请成对填写 start/end，且不要同时填写 hours。'})
        start, end = parse_time(params['start'], 'start'), parse_time(params['end'], 'end')
    else:
        hours = bounded_int(params, 'hours', 48, 1, 744)
        now = timezone.now()
        latest = observations.filter(observed_at__lte=now).order_by('-observed_at').values_list('observed_at', flat=True).first()
        end = min(latest + timedelta(seconds=1), now) if latest else now
        start = end - timedelta(hours=hours)
    if start >= end or end - start > timedelta(days=31):
        raise ValidationError({'start': '查询时间必须递增，且跨度不能超过 31 天。'})
    return start, end


def aggregate_series(metrics, rows, start, end, max_points):
    bucket_seconds = max(1, math.ceil((end - start).total_seconds() / max_points))
    bucket_count = math.ceil((end - start).total_seconds() / bucket_seconds)
    grouped = {metric.pk: [[] for _ in range(bucket_count)] for metric in metrics}
    for row in rows:
        index = min(bucket_count - 1, int((row['observed_at'] - start).total_seconds() // bucket_seconds))
        grouped[row['metric_id']][index].append(row)
    series = []
    for metric in metrics:
        all_rows = [row for bucket in grouped[metric.pk] for row in bucket]
        values = [row['value'] for row in all_rows if row['quality_status'] == Observation.Quality.VALID]
        summary = {
            'valid_count': len(values),
            'missing_count': sum(row['quality_status'] == Observation.Quality.MISSING for row in all_rows),
            'suspect_count': sum(row['quality_status'] == Observation.Quality.SUSPECT for row in all_rows),
            'min': min(values) if values else None, 'max': max(values) if values else None,
            'mean': math.fsum(value / len(values) for value in values) if values else None,
        }
        points = []
        for index, bucket in enumerate(grouped[metric.pk]):
            valid = [row['value'] for row in bucket if row['quality_status'] == Observation.Quality.VALID]
            missing = sum(row['quality_status'] == Observation.Quality.MISSING for row in bucket)
            suspect = sum(row['quality_status'] == Observation.Quality.SUSPECT for row in bucket)
            # A mixed bucket keeps a gap: valid points cannot conceal missing/suspect readings.
            quality = 'suspect' if suspect else ('missing' if missing or not valid else 'valid')
            points.append({
                'at': start + timedelta(seconds=index * bucket_seconds),
                'value': math.fsum(value / len(valid) for value in valid) if valid and quality == 'valid' else None,
                'min': min(valid) if valid else None, 'max': max(valid) if valid else None,
                'valid_count': len(valid), 'missing_count': missing, 'suspect_count': suspect,
                'quality_status': quality,
            })
        latest = all_rows[-1] if all_rows else None
        series.append({
            'metric': {'code': metric.code, 'name': metric.name, 'unit': metric.unit},
            'latest': {key: latest[key] for key in ('value', 'observed_at', 'quality_status')} if latest else None,
            'summary': summary, 'points': points,
        })
    return bucket_seconds, series


class ObservationSeries(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        params = request.query_params
        single_params(params, ('region', 'station', 'metrics', 'source_type', 'source', 'scenario', 'simulation_run', 'hours', 'start', 'end', 'max_points'))
        region = region_for(params)
        if not params.get('station'):
            raise ValidationError({'station': '请选择一个监测站。'})
        station = identifier(public_stations().filter(region=region).select_related('region'), params['station']).first()
        if not station:
            raise ValidationError({'station': '所选区域没有此公开监测站。'})
        metrics = Metric.objects.filter(station_kind=station.kind).order_by('code')
        if 'metrics' in params:
            codes = params['metrics'].split(',')
            if not 1 <= len(codes) <= MAX_METRICS or len(set(codes)) != len(codes) or any(not code for code in codes):
                raise ValidationError({'metrics': '请提供 1 至 9 个不重复的指标代码，以英文逗号分隔。'})
            metrics = metrics.filter(code__in=codes)
            if metrics.count() != len(codes):
                raise ValidationError({'metrics': '指标不存在或不适用于该监测站。'})
        metrics = list(metrics[:MAX_METRICS + 1])
        if len(metrics) > MAX_METRICS:
            raise ValidationError({'metrics': '指标较多，请显式选择最多 9 个指标。'})
        observations, source_type, source, run = select_provenance(params, station)
        start, end = window_for(params, observations)
        max_points = bounded_int(params, 'max_points', 120, 1, 240)
        rows = list(observations.filter(metric__in=metrics, observed_at__gte=start, observed_at__lt=end).order_by('observed_at', 'pk').values('metric_id', 'value', 'observed_at', 'quality_status')[:MAX_RAW_ROWS + 1])
        if len(rows) > MAX_RAW_ROWS:
            raise ValidationError({'start': '所选窗口超过 50000 条原始观测，请缩短时间范围或减少指标。'})
        bucket_seconds, series = aggregate_series(metrics, rows, start, end, max_points)
        return Response({
            'region': RegionSerializer(region).data, 'station': StationSerializer(station).data,
            'source': DataSourceSerializer(source).data if source else None,
            'source_type': source_type, 'is_simulated': source_type == DataSource.Kind.SIMULATION,
            'simulation_run_id': str(run.pk) if run else None,
            'status': 'available' if rows else 'unavailable', 'window': {'start': start, 'end': end},
            'bucket_seconds': bucket_seconds, 'series': series,
            'notice': ('模拟数据，仅用于课程演示，不代表真实监测结果。' if source_type == DataSource.Kind.SIMULATION else '仅展示所选来源的观测数据，请核对来源与观测时间。') + '统计仅使用有效值；缺失、可疑及无记录时段保持断线，不作水质评级或官方 AQI。',
        })


class SimulationRunSerializer(serializers.ModelSerializer):
    source = DataSourceSerializer(read_only=True)
    scenario = serializers.SerializerMethodField()
    # Only the rows matching public stations and requested filters are counted.
    counts = serializers.IntegerField(source='public_counts')

    class Meta:
        model = SimulationRun
        fields = ['id', 'source', 'scenario', 'start', 'end', 'created_at', 'counts', 'generator_version']

    def get_scenario(self, obj):
        return {'code': obj.scenario.code, 'name': obj.scenario.name}


class SimulationRunList(generics.ListAPIView):
    permission_classes = [AllowAny]
    pagination_class = StandardPagination
    serializer_class = SimulationRunSerializer

    def get_queryset(self):
        params = self.request.query_params
        single_params(params, ('region', 'station', 'source', 'scenario'))
        stations = public_stations().filter(region=region_for(params))
        if params.get('station'):
            stations = identifier(stations, params['station'])
            if not stations.exists():
                raise ValidationError({'station': '所选区域没有此公开监测站。'})
        runs = SimulationRun.objects.filter(status='succeeded', source__is_active=True, source__kind=DataSource.Kind.SIMULATION,
                                            observations__station__in=stations).select_related('source', 'scenario')
        if source := explicit_source(params, DataSource.Kind.SIMULATION):
            runs = runs.filter(source=source)
        if 'scenario' in params:
            if not SimulationScenario.objects.filter(code=params['scenario']).exists():
                raise ValidationError({'scenario': '模拟场景不存在。'})
            runs = runs.filter(scenario__code=params['scenario'])
        return runs.annotate(public_counts=Count('observations', distinct=True)).order_by('-created_at', '-pk')

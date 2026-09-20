"""Hourly demonstration sequences; values have no official monitoring interpretation."""
import hashlib
import json
import math
import random
import time
from datetime import timedelta, timezone as datetime_timezone

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .maintenance import lock_catalogue, lock_policy
from .models import DataSource, Metric, Observation, Region, SimulationRun, SimulationScenario, Station

GENERATOR_VERSION = "hourly-v1"
SCENARIOS = {
    "normal": ("正常波动", {}),
    "turbidity": ("突发浑浊", {"turbidity_peak": 75}),
    "missing": ("观测缺失", {"missing_every": 7}),
}
# code, name, unit, station kind, min, max, mean, cycle amplitude, noise amplitude
METRICS = [
    ("water_temperature", "水温", "°C", "water", 0, 45, 22, 2.5, 0.25),
    ("ph", "pH", "pH", "water", 0, 14, 7.2, 0.15, 0.05),
    ("turbidity", "浊度", "NTU", "water", 0, 1000, 8, 1.5, 0.5),
    ("dissolved_oxygen", "溶解氧", "mg/L", "water", 0, 30, 7.8, 0.7, 0.2),
    ("temperature", "气温", "°C", "weather", -80, 60, 25, 4, 0.3),
    ("humidity", "相对湿度", "%", "weather", 0, 100, 65, 10, 2),
    ("pm25", "PM2.5", "μg/m³", "air", 0, 1000, 18, 5, 1.5),
    ("pm10", "PM10", "μg/m³", "air", 0, 2000, 34, 7, 2),
    ("no2", "NO₂", "μg/m³", "air", 0, 1000, 15, 3, 1),
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def observation_key(station, metric, source, observed_at, run=None):
    return digest([station.code, metric.code, source.code, observed_at.astimezone(datetime_timezone.utc).isoformat(), run.key if run else None])


def ensure_simulation_catalogue():
    for code, name, unit, kind, minimum, maximum, *_ in METRICS:
        Metric.objects.get_or_create(code=code, defaults={"name": name, "unit": unit, "station_kind": kind, "min_value": minimum, "max_value": maximum, "description": "演示指标，范围用于输入校验，不是官方评级阈值。"})
    for code, (name, parameters) in SCENARIOS.items():
        SimulationScenario.objects.get_or_create(code=code, defaults={"name": name, "parameters": parameters, "description": "课程演示场景，不用于实际环境评估。"})
        DataSource.objects.get_or_create(code=f"demo-{code}", defaults={"name": f"HYHQ 模拟 · {name}", "kind": "simulation", "license": "项目生成的示范数据", "attribution": "由 HYHQ 小时模拟生成器生成；非真实监测。"})


def validate_parameters(code, parameters):
    if not isinstance(parameters, dict):
        raise ValidationError("场景参数必须为对象。")
    allowed = set(SCENARIOS[code][1])
    if set(parameters) - allowed:
        raise ValidationError("场景含未支持的参数，请使用已定义的生成器参数。")
    if code == "turbidity":
        peak = parameters.get("turbidity_peak", 75)
        if isinstance(peak, bool) or not isinstance(peak, (int, float)) or not math.isfinite(peak) or not 0 <= peak <= 500:
            raise ValidationError("turbidity_peak 必须为 0 至 500 的有限数字。")
    if code == "missing":
        every = parameters.get("missing_every", 7)
        if isinstance(every, bool) or not isinstance(every, int) or not 2 <= every <= 48:
            raise ValidationError("missing_every 必须为 2 至 48 的整数。")


def generate(scenario_code, start, hours, seed=None):
    if scenario_code not in SCENARIOS:
        raise ValidationError("场景仅支持 normal、turbidity、missing。")
    if timezone.is_naive(start) or start.minute or start.second or start.microsecond:
        raise ValidationError("开始时间必须包含时区并对齐整点。")
    if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= 744:
        raise ValidationError("生成小时数必须为 1 至 744。")
    with transaction.atomic():
        lock_policy()
        lock_catalogue()
        result, error = _generate_locked(scenario_code, start, hours, seed)
    if error is not None:
        raise error
    return result


def _generate_locked(scenario_code, start, hours, seed):
    # Read and validate dependencies only after obtaining all catalogue locks.
    ensure_simulation_catalogue()
    scenario = SimulationScenario.objects.get(code=scenario_code)
    validate_parameters(scenario_code, scenario.parameters)
    seed = scenario.seed if seed is None else seed
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2147483647:
        raise ValidationError("seed 必须为 0 至 2147483647 的整数。")
    region = Region.objects.get(slug="demo-campus")
    if not region.is_demo:
        raise ValidationError("生成器只能写入明确标记为示范的区域。")
    stations = list(Station.objects.filter(region=region, is_active=True).select_related("place", "water_body__place").order_by("code"))
    if not stations:
        raise ValidationError("未配置示范监测站，请先运行 seed_demo。")
    point_count = hours * sum(sum(1 for row in METRICS if row[3] == station.kind) for station in stations)
    if point_count > 50000:
        raise ValidationError("单批模拟最多生成 50000 个观测点，请缩短时间范围或减少启用站点。")
    for station in stations:
        station.clean()
    metrics = {metric.code: metric for metric in Metric.objects.filter(code__in=[row[0] for row in METRICS])}
    for code, _, unit, kind, *_ in METRICS:
        if metrics[code].unit != unit or metrics[code].station_kind != kind:
            raise ValidationError(f"指标 {code} 的单位或类型与模拟生成器约定不一致。")
    source = DataSource.objects.get(code=f"demo-{scenario_code}")
    if not source.is_active or source.kind != DataSource.Kind.SIMULATION:
        raise ValidationError("模拟来源必须启用且保持 simulation 类型。")
    start = start.astimezone(datetime_timezone.utc)
    end = start + timedelta(hours=hours)
    signature = {"start": start.isoformat(), "hours": hours, "seed": seed, "scenario": scenario_code, "scenario_version": scenario.version, "parameters": scenario.parameters, "generator": GENERATOR_VERSION, "stations": [(str(s.id), s.code, s.kind) for s in stations], "metrics": [(str(metrics[row[0]].id), row[0], metrics[row[0]].unit, metrics[row[0]].min_value, metrics[row[0]].max_value) for row in METRICS]}
    key = digest(signature)
    error = None
    result = None
    with transaction.atomic():
        run, _ = SimulationRun.objects.get_or_create(key=key, defaults={"scenario": scenario, "source": source, "start": start, "end": end, "seed": seed, "generator_version": GENERATOR_VERSION, "parameters": signature})
        started = time.monotonic()
        try:
            with transaction.atomic():
                run = SimulationRun.objects.select_for_update().get(pk=run.pk)
                if run.status == "succeeded":
                    return (run, False), None
                rows = []
                for hour in range(hours):
                    observed_at = start + timedelta(hours=hour)
                    cycle = math.sin((observed_at.hour - 8) / 24 * 2 * math.pi)
                    for station in stations:
                        for code, _, _, kind, _, _, mean, amplitude, noise in METRICS:
                            if station.kind != kind:
                                continue
                            metric = metrics[code]
                            rng = random.Random(digest([seed, scenario.version, GENERATOR_VERSION, station.code, code, observed_at.isoformat()]))
                            value = mean + amplitude * cycle + rng.uniform(-noise, noise)
                            if scenario_code == "turbidity" and code == "turbidity":
                                peak = scenario.parameters.get("turbidity_peak", 75)
                                value += peak * math.exp(-((observed_at.hour - 14) / 2) ** 2)
                            missing = scenario_code == "missing" and int(observed_at.timestamp() // 3600) % scenario.parameters.get("missing_every", 7) == 0
                            if metric.min_value is not None:
                                value = max(metric.min_value, value)
                            if metric.max_value is not None:
                                value = min(metric.max_value, value)
                            row = Observation(station=station, metric=metric, value=None if missing else round(value, 3), observed_at=observed_at, source=source, quality_status="missing" if missing else "valid", simulation_run=run, dedupe_key=observation_key(station, metric, source, observed_at, run))
                            row.clean()
                            rows.append(row)
                Observation.objects.bulk_create(rows, batch_size=500)
                run.status = "succeeded"
                run.counts = len(rows)
                run.elapsed_ms = int((time.monotonic() - started) * 1000)
                run.completed_at = timezone.now()
                run.error_code = ""
                run.save()
            result = (run, True)
        except Exception as exc:
            SimulationRun.objects.filter(pk=run.pk).update(status="failed", error_code=type(exc).__name__[:80], elapsed_ms=int((time.monotonic() - started) * 1000), completed_at=timezone.now())
            error = exc
    return result, error

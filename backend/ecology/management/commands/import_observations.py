import csv
import math
from pathlib import Path
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ecology.models import DataSource, Metric, Observation, SimulationRun, Station
from ecology.simulation import observation_key

REQUIRED = {"station_code", "metric_code", "value", "unit", "observed_at", "source_code"}
OPTIONAL = {"quality_status", "simulation_run_id"}


class Command(BaseCommand):
    help = "校验整份 UTF-8 CSV 后原子导入；拒绝单位转换、NaN/Inf、错误关联与冲突重复值。"

    def add_arguments(self, parser):
        parser.add_argument("csv_file")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["csv_file"])
        try:
            if path.stat().st_size > 10 * 1024 * 1024:
                raise CommandError("CSV 不得超过 10 MB。")
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                headers = reader.fieldnames or []
                if len(headers) != len(set(headers)) or not REQUIRED.issubset(headers) or set(headers) - REQUIRED - OPTIONAL:
                    raise CommandError("CSV 列不符合契约：必需 station_code,metric_code,value,unit,observed_at,source_code；可选 quality_status,simulation_run_id。")
                stations = {item.code: item for item in Station.objects.select_related("region", "place", "water_body__place")}
                metrics = {item.code: item for item in Metric.objects.all()}
                sources = {item.code: item for item in DataSource.objects.all()}
                runs = {str(item.pk): item for item in SimulationRun.objects.select_related("source")}
                rows = {}
                for line, data in enumerate(reader, 2):
                    if line > 10001:
                        raise CommandError("一次最多导入 10000 条记录。")
                    try:
                        row = self.parse_row(data, stations, metrics, sources, runs)
                        duplicate = rows.get(row.dedupe_key)
                        if duplicate and (duplicate.value, duplicate.quality_status) != (row.value, row.quality_status):
                            raise ValueError("同一观测在 CSV 内有冲突值。")
                        rows[row.dedupe_key] = row
                    except (ValueError, TypeError, KeyError, ValidationError) as exc:
                        raise CommandError(f"第 {line} 行校验失败：{exc}") from exc
            if not rows:
                raise CommandError("CSV 没有观测记录。")
            with transaction.atomic():
                # Chunk key lookups for compatibility with SQLite's parameter limits.
                existing = {}
                keys = list(rows)
                for offset in range(0, len(keys), 500):
                    existing.update({item.dedupe_key: item for item in Observation.objects.filter(dedupe_key__in=keys[offset:offset + 500])})
                for key, old in existing.items():
                    row = rows[key]
                    if (old.value, old.quality_status) != (row.value, row.quality_status):
                        raise CommandError("已有观测值与导入值冲突；整批未写入，请通过新来源或新批次保留修订。")
                pending = [row for key, row in rows.items() if key not in existing]
                if not options["dry_run"]:
                    Observation.objects.bulk_create(pending, batch_size=500)
            self.stdout.write(self.style.SUCCESS(f"{'校验通过，预计新增' if options['dry_run'] else '已导入'} {len(pending)} 条；跳过相同观测 {len(existing)} 条。"))
        except (OSError, UnicodeError, csv.Error) as exc:
            raise CommandError(f"无法读取 CSV：{type(exc).__name__}") from exc

    @staticmethod
    def parse_row(data, stations, metrics, sources, runs):
        if None in data or any(value is None for value in data.values()):
            raise ValueError("CSV 列数不一致。")
        data = {key: value.strip() for key, value in data.items()}
        station = stations[data["station_code"]]
        metric = metrics[data["metric_code"]]
        source = sources[data["source_code"]]
        station.clean()
        if not source.is_active or not station.is_active:
            raise ValueError("来源和监测站必须启用。")
        if data["unit"] != metric.unit:
            raise ValueError(f"单位必须严格为 {metric.unit}，导入不自动换算。")
        observed_at = parse_datetime(data["observed_at"])
        if not observed_at or timezone.is_naive(observed_at):
            raise ValueError("observed_at 必须是含时区的 ISO 时间。")
        value = float(data["value"]) if data["value"] else None
        if value is not None and not math.isfinite(value):
            raise ValueError("不接受 NaN 或 Infinity。")
        quality = data.get("quality_status") or ("missing" if value is None else "valid")
        if quality not in Observation.Quality.values:
            raise ValueError("无效的质量状态。")
        run_value = data.get("simulation_run_id")
        run = runs[str(UUID(run_value))] if run_value else None
        if run and run.status != "succeeded":
            raise ValueError("模拟导入只允许关联成功批次。")
        row = Observation(station=station, metric=metric, value=value, observed_at=observed_at, source=source, quality_status=quality, simulation_run=run, dedupe_key=observation_key(station, metric, source, observed_at, run))
        row.clean()
        return row

"""Fail-closed, preview-first deletion of old internally generated demonstration batches."""
from collections import defaultdict
from datetime import timedelta
import hashlib
import json

from django.core import signing
from django.db import transaction
from django.utils import timezone

from common.audit import audit
from .models import (DataSource, MapLayout, Metric, Observation, Place, Region, SimulationCleanupPreview,
                     SimulationRetentionPolicy, SimulationRun, SimulationScenario, Station, WaterBody)

PREVIEW_SECONDS = 900
MAX_RUNS = 5000
MAX_OBSERVATIONS = 250000
SALT = "ecology.simulation-cleanup.v1"
REASONS = {
    "active": "运行中或未知状态，禁止清理",
    "recent": "仍处于保留期（观测终点、创建或完成时间）",
    "latest": "每来源/场景保留的最新成功批次",
    "latest_observation": "含本来源/场景最新时间范围的成功批次",
    "latest_station": "监测站当前最新的成功模拟批次",
    "unsafe_source": "不是项目生成的模拟来源",
    "unsafe_scope": "观测来源、站点、指标或时间范围关联不一致",
    "count_mismatch": "批次记录数量与实际观测数量不一致",
}


class MaintenanceError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def lock_policy():
    """Caller must hold transaction.atomic; generator takes the same lock first."""
    SimulationRetentionPolicy.objects.get_or_create(pk=1)
    return SimulationRetentionPolicy.objects.select_for_update().get(pk=1)


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def lock_catalogue():
    """Lock generation/deletion dependencies in the same fixed order."""
    return [list(model.objects.select_for_update().order_by("pk").values())
            for model in (DataSource, SimulationScenario, Region, MapLayout, Place, WaterBody, Station, Metric)]


def _locked_state(policy, now):
    # Admin edits cannot change the deletion scope after validation; run and
    # observation row locks also cover direct writers.
    parent_state = lock_catalogue()
    runs = list(SimulationRun.objects.select_for_update().order_by("pk")[:MAX_RUNS + 1])
    if len(runs) > MAX_RUNS:
        raise MaintenanceError("too_large", "批次超过安全预览上限，请先分库归档；本次未清理。")
    fields = ["id", "simulation_run_id", "source_id", "source__kind", "observed_at", "updated_at", "value", "quality_status",
              "station_id", "station__kind", "station__region_id", "station__region__is_demo", "station__place__region_id",
              "station__water_body__place__region_id", "metric_id", "metric__code", "metric__station_kind", "metric__unit"]
    # select_for_update cannot lock nullable outer joins on PostgreSQL; lock the
    # actual observation rows, while joined parents were locked above.
    observations = list(Observation.objects.select_for_update(of=("self",)).filter(simulation_run__isnull=False)
                        .order_by("pk").values(*fields)[:MAX_OBSERVATIONS + 1])
    if len(observations) > MAX_OBSERVATIONS:
        raise MaintenanceError("too_large", "观测超过安全预览上限，请先分库归档；本次未清理。")
    sources = {str(row["id"]): row for row in parent_state[0]}
    scenarios = {str(row["id"]): row for row in parent_state[1]}
    by_run = defaultdict(list)
    for row in observations:
        by_run[str(row["simulation_run_id"])].append(row)
    successful = defaultdict(list)
    for run in runs:
        if run.status == "succeeded":
            successful[(run.source_id, run.scenario_id)].append(run)
    latest_ids = set()
    latest_range_ids = set()
    for group in successful.values():
        latest_ids.update(run.pk for run in sorted(group, key=lambda r: (r.created_at, str(r.pk)), reverse=True)[:policy.keep_successful])
        latest_end = max(run.end for run in group)
        latest_range_ids.update(run.pk for run in group if run.end == latest_end)
    # A station can be temporarily absent from newer runs. Preserve its actual
    # latest successful public batch even when it is older than the group top N.
    station_latest = {}
    for run in sorted(runs, key=lambda r: (r.created_at, str(r.pk)), reverse=True):
        if run.status != "succeeded":
            continue
        for row in by_run[str(run.pk)]:
            if row["source_id"] == run.source_id and row["source__kind"] == "simulation":
                station_latest.setdefault((run.source_id, run.scenario_id, row["station_id"]), run.pk)
    latest_station_ids = set(station_latest.values())
    cutoff = now - timedelta(days=policy.retain_days)
    candidates, protected = [], []
    for run in runs:
        rows = by_run[str(run.pk)]
        source = sources[str(run.source_id)]
        scenario = scenarios[str(run.scenario_id)]
        reasons = []
        signature = run.parameters if isinstance(run.parameters, dict) else {}
        if (source["kind"] != "simulation" or source["code"] != f"demo-{scenario['code']}"
                or run.generator_version != "hourly-v1" or signature.get("generator") != "hourly-v1"):
            reasons.append("unsafe_source")
        if run.status not in ("succeeded", "failed"):
            reasons.append("active")
        if any(value is not None and value >= cutoff for value in (run.end, run.created_at, run.completed_at)):
            reasons.append("recent")
        if run.pk in latest_ids:
            reasons.append("latest")
        if run.pk in latest_range_ids:
            reasons.append("latest_observation")
        if run.pk in latest_station_ids:
            reasons.append("latest_station")
        if run.counts != len(rows):
            reasons.append("count_mismatch")
        try:
            station_ids = {str(item[0]) for item in signature.get("stations", [])}
            metric_ids = {str(item[0]) for item in signature.get("metrics", [])}
        except (TypeError, IndexError):
            station_ids, metric_ids = set(), set()
        if any(row["source_id"] != run.source_id or row["source__kind"] != "simulation"
               or not row["station__region__is_demo"]
               or str(row["station_id"]) not in station_ids or str(row["metric_id"]) not in metric_ids
               or row["station__kind"] != row["metric__station_kind"]
               or row["station__place__region_id"] not in (None, row["station__region_id"])
               or row["station__water_body__place__region_id"] not in (None, row["station__region_id"])
               or not run.start <= row["observed_at"] < run.end for row in rows):
            reasons.append("unsafe_scope")
        item = {"id": str(run.pk), "key": run.key, "scenario": scenario["code"], "source": source["code"],
                "status": run.status, "start": run.start, "end": run.end, "created_at": run.created_at,
                "actual_count": len(rows), "declared_count": run.counts,
                "reasons": reasons, "protection": [REASONS[reason] for reason in reasons]}
        (protected if reasons else candidates).append(item)
    policy_data = {"retain_days": policy.retain_days, "keep_successful": policy.keep_successful}
    fingerprint = _hash({"parents": parent_state, "policy": policy_data, "runs": [
        {field.attname: getattr(run, field.attname) for field in SimulationRun._meta.fields} for run in runs],
        "observations": observations})
    return {"policy": policy_data, "cutoff": cutoff, "candidates": candidates, "protected": protected,
            "batch_count": len(candidates), "observation_count": sum(row["actual_count"] for row in candidates),
            "fingerprint": fingerprint}


def _actor_id(actor):
    return str(actor.pk) if actor is not None and getattr(actor, "is_authenticated", False) else "command"


@transaction.atomic
def create_preview(actor=None):
    policy = lock_policy()
    now = timezone.now()
    state = _locked_state(policy, now)
    preview = SimulationCleanupPreview.objects.create(
        actor=actor if _actor_id(actor) != "command" else None, fingerprint=state["fingerprint"],
        policy=state["policy"], candidate_ids=[row["id"] for row in state["candidates"]],
        observation_count=state["observation_count"], expires_at=now + timedelta(seconds=PREVIEW_SECONDS))
    token = signing.dumps({"preview": str(preview.pk), "actor": _actor_id(actor)}, salt=SALT)
    audit("simulation.cleanup.preview", actor=actor, target_id=preview.pk, status="ready", count=state["observation_count"], source="simulation")
    return {**state, "token": token, "expires_at": preview.expires_at}


def execute_preview(token, actor=None):
    try:
        payload = signing.loads(token, salt=SALT, max_age=PREVIEW_SECONDS)
    except (signing.BadSignature, TypeError, ValueError):
        raise MaintenanceError("invalid_preview", "清理预览已过期或无效，请重新预览。")
    if payload.get("actor") != _actor_id(actor):
        raise MaintenanceError("wrong_actor", "此清理预览不属于当前管理员。")
    with transaction.atomic():
        policy = lock_policy()
        try:
            preview = SimulationCleanupPreview.objects.select_for_update().get(pk=payload["preview"])
        except (SimulationCleanupPreview.DoesNotExist, KeyError, ValueError):
            raise MaintenanceError("invalid_preview", "清理预览不存在，请重新预览。")
        if preview.consumed_at or preview.expires_at <= timezone.now():
            raise MaintenanceError("invalid_preview", "清理预览已执行或过期，请重新预览。")
        # Use the original cutoff. Time passing never silently adds candidates.
        state = _locked_state(policy, preview.expires_at - timedelta(seconds=PREVIEW_SECONDS))
        ids = [row["id"] for row in state["candidates"]]
        if (state["fingerprint"] != preview.fingerprint or state["policy"] != preview.policy
                or ids != preview.candidate_ids or state["observation_count"] != preview.observation_count):
            raise MaintenanceError("stale_preview", "批次、观测或保留策略已变化，请重新预览后执行。")
        rows = Observation.objects.filter(simulation_run_id__in=ids)
        count = rows.count()
        if count != preview.observation_count:
            raise MaintenanceError("stale_preview", "观测数量已变化，请重新预览。")
        rows.delete()
        SimulationRun.objects.filter(pk__in=ids).delete()
        preview.consumed_at = timezone.now()
        preview.save(update_fields=["consumed_at"])
        audit("simulation.cleanup.execute", actor=actor, target_id=preview.pk, status="succeeded", count=count, source="simulation")
        return {"batch_count": len(ids), "observation_count": count}

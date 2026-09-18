"""河道评估推理工作进程：消费 AssessmentJob → YOLO 检测 → 规则评估 → 落库。

镜像 recognition/worker.py 的状态机：queued → running → succeeded/failed。
但检测+评估管道独立于花卉识别；同进程内运行 ONNX 推理（dev/test 可用，
Linux 生产环境建议改用 recognition/isolation.run_child 子进程隔离）。
"""
import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from common.models import TaskLog
from .models import AssessmentJob, RuleSet
from . import detection as _detection
from . import rules as _rules


ERROR_MESSAGES = {
    "MODEL_NOT_CONFIGURED": "河道评估模型暂未启用，请稍后重试",
    "INFERENCE_TIMEOUT": "评估已超时，请换一张图片重试",
    "ASSET_EXPIRED": "图片已过期或被删除，请重新上传",
    "IMAGE_UNAVAILABLE": "图片已过期或无法读取，请重新上传",
    "MODEL_CHECKSUM_MISMATCH": "模型文件校验失败，请联系管理员",
    "MODEL_CONFIG_MISMATCH": "模型配置校验失败，请联系管理员",
    "INFERENCE_FAILED": "评估暂不可用，请重试或联系管理员",
}


def _try_lock():
    """获取单机评估执行锁；锁被占用时返回 None。"""
    @contextmanager
    def lock():
        path = Path(settings.RECOGNITION_LOCK_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield None
            else:
                yield fd
        finally:
            os.close(fd)
    return lock()


def _recover_stale():
    now = timezone.now()
    timeout_s = getattr(settings, "RECOGNITION_RUN_TIMEOUT_SECONDS", 30)
    count = AssessmentJob.objects.filter(
        status="running",
        started_at__lt=now - timedelta(seconds=timeout_s)
    ).update(status="failed", error_code="WORKER_TIMEOUT",
             message="处理已超时，请重新提交图片", finished_at=now)
    count += AssessmentJob.objects.filter(status="running").update(
        status="failed", error_code="WORKER_INTERRUPTED",
        message="处理进程已中断，请重新提交图片", finished_at=now)
    count += AssessmentJob.objects.filter(
        status="queued",
        created_at__lt=now - timedelta(seconds=getattr(settings, "RECOGNITION_QUEUE_TIMEOUT_SECONDS", 60))
    ).update(status="failed", error_code="QUEUE_TIMEOUT",
             message="排队已超时，请重新提交图片", finished_at=now)
    if count:
        TaskLog.objects.create(task="assessment.recovery", status="succeeded", count=count)
    return count


def recover_stale_jobs():
    with _try_lock() as lock_fd:
        return 0 if lock_fd is None else _recover_stale()


def _claim():
    with transaction.atomic():
        queryset = AssessmentJob.objects.filter(status="queued").order_by("created_at")
        queryset = (queryset.select_for_update(skip_locked=True)
                    if connection.features.has_select_for_update_skip_locked
                    else queryset.select_for_update())
        job = queryset.first()
        if job is None:
            return None
        from recognition.models import ModelVersion
        model = ModelVersion.objects.filter(enabled=True).first()
        job.status = "running"
        job.started_at = timezone.now()
        if model:
            job.model_version = model
            try:
                from recognition.registry import snapshot_for
                job.model_snapshot = snapshot_for(model)
            except Exception:
                job.model_snapshot = {"invalid": True}
        # ????????? RuleSet???????? active RuleSet?
        # rule_version ?? API ??????assess ? rule_version ???
        if not job.rule_set_id:
            active_rule = RuleSet.objects.filter(is_active=True).first()
            if active_rule:
                job.rule_set = active_rule
                if not job.rule_version:
                    job.rule_version = active_rule.version
        job.save(update_fields=["status", "started_at", "model_version",
                                "model_snapshot", "rule_set", "rule_version"])
        return job


def _build_detection_payload(job, boxes, image_width, image_height):
    """把检测框 + 模型标签 + 原图尺寸 → assess 入参（含 eval_category + area_ratio）。"""
    labels = (job.model_snapshot or {}).get("labels", [])
    label_map = {int(l["id"]): l for l in labels} if labels else {}
    img_area = max(1, image_width * image_height)
    detections = []
    for b in boxes:
        cls_id = int(b["class_id"])
        label = label_map.get(cls_id, {})
        eval_cat = label.get("eval_category") or label.get("name") or "floating_debris"
        box_w = max(0, b["x2"] - b["x1"])
        box_h = max(0, b["y2"] - b["y1"])
        detections.append({
            "eval_category": eval_cat,
            "conf": float(b["conf"]),
            "area_ratio": round((box_w * box_h) / img_area, 6),
            "x1": b["x1"], "y1": b["y1"], "x2": b["x2"], "y2": b["y2"],
            "class_id": cls_id,
            "label": label.get("name", ""),
        })
    return detections


def _finish(job, started, *, detections=None, score=None, grade="", causes=None,
            error_code=""):
    duration = int((time.monotonic() - started) * 1000)
    status = "failed" if error_code else "succeeded"
    rule_set_id = job.rule_set_id
    rule_version = job.rule_version
    with transaction.atomic():
        changed = AssessmentJob.objects.filter(pk=job.pk, status="running").update(
            status=status,
            detections=[] if detections is None else detections,
            score=score if score is not None and not error_code else None,
            grade=grade if not error_code else "",
            causes=[] if causes is None else causes,
            error_code=error_code,
            message=ERROR_MESSAGES.get(error_code, "评估暂不可用，请重试或联系管理员") if error_code else "",
            finished_at=timezone.now(), duration_ms=duration)
        if changed:
            TaskLog.objects.create(
                task="assessment", status=status, error_code=error_code,
                count=1, duration_ms=duration)


def process_one():
    """消费一个 AssessmentJob：claim → detect → assess → persist。"""
    with _try_lock() as lock_fd:
        if lock_fd is None:
            return False
        _recover_stale()
        job = _claim()
        if job is None:
            return False
        started = time.monotonic()
        try:
            snapshot = job.model_snapshot
            if not snapshot or snapshot.get("invalid"):
                raise RuntimeError("MODEL_NOT_CONFIGURED")
            asset = job.asset
            now = timezone.now()
            if (asset is None or not asset.original
                or asset.original_expires_at <= now
                or (asset.expires_at and asset.expires_at <= now)
                or job.expires_at <= now):
                raise RuntimeError("ASSET_EXPIRED")
            result = _detection.detect(snapshot, asset.original.path,
                                        settings.RECOGNITION_MODEL_ROOT,
                                        settings.MEDIA_ROOT)
            detections = _build_detection_payload(
                job, result["boxes"], result["image_width"], result["image_height"])
            assessment = _rules.assess(detections, rule_version=job.rule_version or "v1")
            _finish(job, started,
                    detections=detections,
                    score=assessment["score"],
                    grade=assessment["grade"],
                    causes=assessment["causes"])
        except RuntimeError as exc:
            code = str(exc) or "INFERENCE_FAILED"
            if not any(k in code for k in ("MODEL_", "ASSET_", "IMAGE_", "INFERENCE_")):
                code = "INFERENCE_FAILED"
            _finish(job, started, error_code=code)
        except Exception:
            _finish(job, started, error_code="INFERENCE_FAILED")
        return True

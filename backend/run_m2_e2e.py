#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""m2 框架端到端验收（Windows 桥）：v5 检测 + ecology-v1 生态等级。

流程：3 张 water-eval 代表图 → Asset(purpose=recognition) → AssessmentJob(ecology-v1 快照)
      → process_one()（含 v5 ONNX 推理 + 生态等级评估）→ 输出 score/grade/causes。

Windows 适配（m2 代码零改动）：
  1) fcntl mock（isolation/worker 的 flock no-op）
  2) isolation.run_detection 同步直调（子进程隔离是 Linux 部署特性）
用法：cd backend && $env:HYHQ_USE_SQLITE="1"; .venv\\Scripts\\python.exe run_m2_e2e.py
"""
import copy
import os
import shutil
import sys
import types
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 1) fcntl mock
fcntl = types.ModuleType("fcntl")
fcntl.flock = lambda fd, op: None
fcntl.LOCK_EX = 2
fcntl.LOCK_UN = 8
fcntl.LOCK_NB = 4
sys.modules["fcntl"] = fcntl

# 2) isolation.run_detection -> 同步直调
import assessments.isolation as _iso

_BACKEND_PARENT = str(Path(__file__).resolve().parent.parent)


def _sync_run_detection(snapshot, image_path, model_root, media_root, timeout, lock_fd, *, validate_only=False):
    if _BACKEND_PARENT not in sys.path:
        sys.path.insert(0, _BACKEND_PARENT)
    from assessments.detector import validate_model, infer
    if validate_only:
        validate_model(snapshot, model_root)
        return {"validated": True}
    return infer(snapshot, image_path, model_root, media_root)


_iso.run_detection = _sync_run_detection

import django

django.setup()

from django.conf import settings
from django.core.files import File
from django.utils import timezone
from PIL import Image
from accounts.models import User
from assets.models import Asset
from assessments.models import AssessmentJob, RuleSet
from assessments.worker import process_one

WATER_EVAL = Path(r"D:\WeChatProjects\HYHQ\inference\data\splits\water-eval\images")
SAMPLES = [
    ("W_test_IMG_0090_JPG.rf.7c2bb34a2a1aff56429fd30d218eac0e.jpg", "泡沫+塑料"),
    ("W_valid_IMG_0091_JPG.rf.e7c296cd844f87aa347a3f1f48af9145.jpg", "密集瓶堆"),
    ("W_valid_IMG_20220919_164138_4_jpg.rf.95e0e82c7cb1129e8e48780b15fee729.jpg", "混合"),
]

user, _ = User.objects.get_or_create(username="e2e-m2-user", defaults={"is_active": True})
rule = RuleSet.objects.get(version="ecology-v1")
media_originals = Path(settings.MEDIA_ROOT) / "originals"
media_originals.mkdir(parents=True, exist_ok=True)

results = []
for filename, tag in SAMPLES:
    src = WATER_EVAL / filename
    dst = media_originals / f"m2e2e_{filename}"
    shutil.copy2(src, dst)
    now = timezone.now()
    expiry = now + timedelta(days=settings.RECORD_RETENTION_DAYS)
    with Image.open(src) as im:
        width, height = im.size
    asset = Asset.objects.create(owner=user, purpose="recognition", width=width, height=height,
                                 byte_size=dst.stat().st_size,
                                 original=File(open(dst, "rb"), name=f"originals/m2e2e_{filename}"),
                                 original_expires_at=expiry, expires_at=expiry)
    job = AssessmentJob.objects.create(owner=user, asset=asset, rule_set=rule,
                                       rule_snapshot=copy.deepcopy(rule.definition),
                                       rule_version=rule.version, expires_at=expiry)
    done = process_one()
    job.refresh_from_db()
    results.append((tag, job, done))

print("\n=== m2 框架端到端（v5 + ecology-v1）===")
for tag, job, done in results:
    print(f"\n[{tag}]")
    print(f"  status={job.status} model={job.model_version.version if job.model_version else None} "
          f"rule={job.rule_version} dur={job.duration_ms}ms")
    print(f"  score={job.score} grade={job.grade}")
    print(f"  causes={job.causes}")
    print(f"  detections={len(job.detections)} categories=" +
          ",".join(sorted({d.get('eval_category', '?') for d in job.detections})))
print(f"\n[ok] 3 图全链路完成（process_one 处理数={sum(1 for *_, d in results if d)}）")

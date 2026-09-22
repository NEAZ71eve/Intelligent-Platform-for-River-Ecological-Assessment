#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""河道生态评估冒烟验收命令：单张图片 → Asset → AssessmentJob → worker 全链路。

用法（仓库根目录，Linux/服务器端）：
    scripts/manage.sh smoke_assessment --image /absolute/path/to/image.jpg
    scripts/manage.sh smoke_assessment --image /absolute/path/to/image.jpg --once --expected-grade 良

--once 只消费本任务；不传则 process_one 可能继续消费队列中其他任务（建议传 --once）。
Windows 本地无 fcntl 时请改用 backend/e2e_v5_acceptance.py（已内置兼容 mock）。
"""
from datetime import timedelta

# Windows 本地无 fcntl（Unix 模块）：注入无操作实现保证命令跨平台可用；
# Linux 已有真实 fcntl，不覆盖。
import sys
import types
if "fcntl" not in sys.modules:
    sys.modules["fcntl"] = types.SimpleNamespace(
        LOCK_EX=1, LOCK_NB=2,
        flock=lambda *a, **k: None,
    )

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from PIL import Image

from accounts.models import User
from assets.models import Asset
from ecology.assessment_worker import process_one
from ecology.models import AssessmentJob

TEST_USERNAME = "smoke_acceptance"


class Command(BaseCommand):
    help = "河道生态评估端到端冒烟验收：建任务→推理→规则→落库并输出评分/等级。"

    def add_arguments(self, parser):
        parser.add_argument("--image", required=True, help="待评估图片绝对路径")
        parser.add_argument("--once", action="store_true", help="仅消费本任务即退出")
        parser.add_argument("--expected-grade", default="", help="预期等级（优/良/中/差），不符时退出码 2")

    def handle(self, *args, **options):
        from pathlib import Path
        img = Path(options["image"]).resolve(strict=True)
        if img.stat().st_size > 6 * 1024 * 1024:
            raise CommandError("图片超过 6MB 上限")
        with Image.open(img) as im:
            im.verify()
            with Image.open(img) as im2:
                w, h = im2.size

        user, _ = User.objects.get_or_create(username=TEST_USERNAME)
        now = timezone.now()
        asset = Asset.objects.create(
            owner=user, purpose="recognition",
            width=w, height=h, byte_size=img.stat().st_size,
            original_expires_at=now + timedelta(hours=1),
            expires_at=now + timedelta(hours=1),
        )
        with img.open("rb") as src:
            asset.original.save(f"smoke_{img.stem[:48]}.jpg", src, save=True)
        job = AssessmentJob.objects.create(
            owner=user, asset=asset, status="queued",
            expires_at=now + timedelta(hours=1))

        processed = process_one()
        job.refresh_from_db()
        self.stdout.write(f"processed={processed} status={job.status}")
        if job.status != "succeeded":
            raise CommandError(f"任务失败：{job.error_code or '?'} {job.message}")
        cats = {}
        for d in job.detections or []:
            cats[d.get("eval_category")] = cats.get(d.get("eval_category"), 0) + 1
        self.stdout.write(f"model={job.model_version.version if job.model_version else None} "
                          f"rule={job.rule_version or 'v1'} duration={job.duration_ms}ms")
        self.stdout.write(f"score={job.score} grade={job.grade} detections={len(job.detections or [])} "
                          f"categories={cats} causes={job.causes}")
        if options["expected_grade"] and job.grade != options["expected_grade"]:
            raise CommandError(f"等级不符：期望 {options['expected_grade']}，实际 {job.grade}")
        self.stdout.write(self.style.SUCCESS("SMOKE OK"))

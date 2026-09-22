#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Windows 下登记/验证 v5 检测模型（m2 assessments 本地验证桥）。
m2 的 isolation.py 为 Linux 部署假设：fcntl.flock 进程锁 + 子进程隔离（pass_fds/
resource/SIGALRM 均 Windows 不支持）。本桥只做三件最小适配，m2 代码零改动：
  1) sys.modules 注入 fcntl mock（flock no-op + LOCK_EX/LOCK_NB）
  2) 将 isolation.run_detection 替换为同步直调 detector.validate_model/infer
     （隔离层是生产安全措施，本地验证不测隔离本身；Linux 上原实现自然工作）
用法：cd backend && .venv\\Scripts\\python.exe run_register_v5.py [--activate]
"""
import os
import sys
import types

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
from pathlib import Path

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

from django.core.management import execute_from_command_line

if __name__ == "__main__":
    args = ["manage.py", "register_detector",
            "../inference/artifacts/river-eco-yolov8n-v5.manifest.json"]
    if "--activate" in sys.argv:
        args.append("--activate")
    execute_from_command_line(args)

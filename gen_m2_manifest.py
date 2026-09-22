#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 v5 manifest 改造为 m2 assessments 契约版（去 fine 键 + 补 supported_class_ids），
并用 m2 的 validate_config 就地校验。产物覆盖 integrate-m2 分支的 artifacts 副本。"""
import json
import sys
from pathlib import Path

SRC = Path(r"D:\WeChatProjects\HYHQ\inference\artifacts\river-eco-yolov8n-v5.manifest.json")
DST = SRC  # integrate-m2 工作目录副本
# m2 校验逻辑（纯 stdlib，无 django 依赖）
sys.path.insert(0, r"D:\WeChatProjects\HYHQ\backend")
from assessments.artifacts import CONFIG_FIELDS, validate_config, config_digest

m = json.loads(SRC.read_text(encoding="utf-8"))
# 1) labels：去 fine，仅 id/name/eval_category
m["labels"] = [{"id": i, "name": l["name"], "eval_category": l["eval_category"]}
               for i, l in enumerate(m["labels"])]
# 2) preprocessing：补 supported_class_ids（10 个 floating_debris 类 0-9）
m["preprocessing"]["supported_class_ids"] = list(range(10))
# 3) 校验 m2 契约
config = {
    "name": m["model_name"], "version": m["model_version"],
    "artifact": m["artifact"], "checksum": m["sha256"],
    "labels": m["labels"], "preprocessing": m["preprocessing"],
    "threshold": m["threshold"], "scope": m["scope"],
    "license": m["license"], "source": m["source_url"], "evaluation": m["evaluation"],
}
digest = validate_config(config)
print(f"[ok] m2 契约校验通过 config_digest={digest[:16]}...")
print(f"[ok] labels={len(m['labels'])} supported_class_ids={m['preprocessing']['supported_class_ids']}")
DST.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[ok] 已写入 {DST}（{DST.stat().st_size} bytes）")

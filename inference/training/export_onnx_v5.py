#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""导出 v5（unified-v4 数据训练，水域 held-out 协议）→ ONNX + manifest。沿用 export_onnx.py 的格式。"""
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from training.class_mapping import load_mapping
from training.export_onnx import DISPLAY

ARTIFACTS = _ROOT / "artifacts"
RUNS = _ROOT / "runs"


def main():
    run = RUNS / "river-eco-v5"
    best_pt = run / "weights" / "best.pt"
    if not best_pt.exists():
        raise SystemExit(f"未找到 {best_pt}")
    print(f"[export] {best_pt}")
    from ultralytics import YOLO
    model = YOLO(str(best_pt))
    out = model.export(format="onnx", imgsz=640, opset=12, simplify=True, dynamic=False)
    onnx_src = Path(out)
    print(f"[export] ONNX: {onnx_src}")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    artifact_name = "river-eco-yolov8n-v5.onnx"
    dest = ARTIFACTS / artifact_name
    shutil.copy2(onnx_src, dest)
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()

    evaluation = {"report": "miniprogram-2/docs/HYHQ_河道检测模型迭代报告_v3_v4_v5.md"}
    metrics = run / "results.csv"
    if metrics.exists():
        rows = list(csv.DictReader(metrics.open(encoding="utf-8")))
        if rows:
            last = rows[-1]
            evaluation["final_epoch"] = {k.strip(): float(v) for k, v in last.items()
                                         if v not in ("", None)}

    mapping = load_mapping()
    labels = []
    for i, fine in enumerate(mapping["fine_labels"].keys()):
        labels.append({
            "id": i, "name": DISPLAY.get(fine, fine),
            "fine": fine,
            "eval_category": mapping["fine_labels"][fine]["eval"],
        })

    manifest = {
        "model_name": "river-eco-yolov8n",
        "model_version": "v5",
        "task": "detection",
        "artifact": artifact_name,
        "sha256": sha,
        "labels": labels,
        "class_mapping_version": mapping["version"],
        "preprocessing": {
            "resize_size": 640, "letterbox": True, "pad_value": 114,
            "interpolation": "bilinear", "scale": [0.0, 1.0],
        },
        "imgsz": 640,
        "threshold": 0.5,
        "scope": "河道生态评估检测 v5（unified-v4：marine-debris640 仅 train 子集入训练，"
                 "marine valid/test 174 图划为水域 held-out 评估集；剔除 TACO 污染漂移；"
                 "+synth_cp 合成）：覆盖 10/15 细类，水华黑臭/岸带 5 细类零样本未训练；"
                 "水域 held-out mAP50=0.7325（bottle 0.627/foam_board 0.802/plastic 0.811）；"
                 "仅作识别参考，非官方水质评价。",
        "license": "IWHR CC BY 4.0; iSOOD CC BY 4.0; marine-debris640; Ultralytics YOLOv8n AGPL-3.0",
        "source_url": "https://github.com/NEAZ71eve/Intelligent-Platform-for-River-Ecological-Assessment",
        "evaluation": evaluation,
    }
    manifest_path = ARTIFACTS / "river-eco-yolov8n-v5.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print(f"[ok] {dest.name} ({dest.stat().st_size} bytes)")
    print(f"[ok] {manifest_path}")
    print(f"[ok] sha256={sha}")


if __name__ == "__main__":
    main()

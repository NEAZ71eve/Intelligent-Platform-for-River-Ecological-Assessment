#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""导出 v4（unified-v3 数据训练）→ ONNX + manifest。沿用 export_onnx.py 的格式。"""
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
    run = RUNS / "river-eco-v4"
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
    artifact_name = "river-eco-yolov8n-v4.onnx"
    dest = ARTIFACTS / artifact_name
    shutil.copy2(onnx_src, dest)
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()

    evaluation = {"report": "inference/runs/eval-v4-stage1/report_v3_vs_v4.md"}
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
        "model_version": "v4",
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
        "scope": "河道生态评估检测 v4（unified-v3：+marine-debris640 水域域 +synth_cp 合成，"
                 "剔除标注污染源）：覆盖 10/15 细类，水华黑臭/岸带 5 细类零样本未训练；"
                 "仅作识别参考，非官方水质评价。",
        "license": "IWHR CC BY 4.0; iSOOD CC BY 4.0; marine-debris640; Ultralytics YOLOv8n AGPL-3.0",
        "source_url": "https://github.com/NEAZ71eve/Intelligent-Platform-for-River-Ecological-Assessment",
        "evaluation": evaluation,
    }
    manifest_path = ARTIFACTS / "river-eco-yolov8n-v4.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print(f"[ok] {dest.name} ({dest.stat().st_size} bytes)")
    print(f"[ok] {manifest_path}")
    print(f"[ok] sha256={sha}")


if __name__ == "__main__":
    main()

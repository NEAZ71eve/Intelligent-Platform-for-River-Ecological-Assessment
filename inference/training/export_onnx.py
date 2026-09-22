"""导出训练好的 YOLOv8n → ONNX 并生成检测 manifest（Task 6）。

运行（训练完成后）：cd inference && python training/export_onnx.py
产出：
  - inference/artifacts/river-eco-yolov8n-v1.onnx
  - inference/artifacts/river-eco-yolov8n-v1.manifest.json
注：manifest 的 labels 为 15 细类（index=class_id，与 class_mapping.yaml v1 冻结一致），
    每项含 eval_category 供评估聚合。后端登记需 validate_config 检测分支（另行扩展）。
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from training.class_mapping import load_mapping

ARTIFACTS = _ROOT / "artifacts"
RUNS = _ROOT / "runs"

# 细类中文显示名（label.name 用中文，eval 用细类英文键）
DISPLAY = {
    "bottle": "塑料瓶罐", "foam_board": "泡沫板材", "water_plant": "水生植物",
    "algae_mass": "藻类聚集", "plastic": "塑料垃圾", "paper": "纸制品",
    "glass": "玻璃制品", "metal": "金属制品", "fabric": "织物纤维",
    "misc_debris": "其他漂浮物", "sewage_color": "异常水色", "foam_pollution": "泡沫污染",
    "outfall": "排污口", "bank_garbage": "岸带垃圾", "bank_encroach": "岸带侵占",
}


def find_best_run():
    """找最新的 river-eco-v3* run 目录（训练重跑会带 -N 后缀）。"""
    candidates = sorted(RUNS.glob("river-eco-v3*"), key=lambda p: p.stat().st_mtime)
    for run in reversed(candidates):
        best = run / "weights" / "best.pt"
        if best.exists():
            return run, best
    raise SystemExit("未找到 runs/river-eco-v3*/weights/best.pt —— 请先运行 train_yolo.py")


def main():
    run, best_pt = find_best_run()
    print(f"[export] {best_pt}")
    from ultralytics import YOLO
    model = YOLO(str(best_pt))
    out = model.export(format="onnx", imgsz=640, opset=12, simplify=True, dynamic=False)
    onnx_src = Path(out)
    print(f"[export] ONNX: {onnx_src}")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    artifact_name = "river-eco-yolov8n-v3.onnx"
    dest = ARTIFACTS / artifact_name
    shutil.copy2(onnx_src, dest)
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()

    # 评估指标（训练产出）
    evaluation = {"report": "inference/reports/yolo-v1-report.md"}
    metrics = run / "results.csv"
    if metrics.exists():
        import csv
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
        "model_version": "v3",
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
        "scope": "河道生态评估检测 v2（unified-v2 多类训练）：覆盖 10/15 细类，"
                 "水华黑臭/岸带 5 细类零样本未训练；仅作识别参考，非官方水质评价。",
        "license": "IWHR CC BY 4.0; iSOOD CC BY 4.0; Ultralytics YOLOv8n AGPL-3.0",
        "source_url": "https://github.com/NEAZ71eve/Intelligent-Platform-for-River-Ecological-Assessment",
        "evaluation": evaluation,
    }
    manifest_path = ARTIFACTS / "river-eco-yolov8n-v3.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print(f"[ok] {dest.name} ({dest.stat().st_size} bytes)")
    print(f"[ok] {manifest_path}")
    print(f"[ok] sha256={sha}")


if __name__ == "__main__":
    main()

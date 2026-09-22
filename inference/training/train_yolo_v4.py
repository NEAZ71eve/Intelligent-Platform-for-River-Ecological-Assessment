"""YOLOv8n 训练 v4（河道生态评估 · 弱类补强迭代）。

数据：data/splits/unified-v3/dataset.yaml
  = unified-v2 五源（冻结划分，val/test 与 v2 完全一致）
  + MARINE（marine-debris640 水面域，bottle/foam_board 主补强，仅入 train）
  + SYNTH（Copy-Paste 合成 600 图，仅入 train）
超参：与 v3 完全一致（yolov8n.pt / 640 / batch16 / 100 轮 / seed42），
保证 v3→v4 差异全部来自数据补强，可归因。

运行：cd inference && python training/train_yolo_v4.py
产出：runs/river-eco-v4/
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ultralytics import YOLO


def main():
    model = YOLO("yolov8n.pt")
    model.train(
        data=str(_ROOT / "data" / "splits" / "unified-v3" / "dataset.yaml"),
        epochs=100, imgsz=640, batch=16,
        project=str(_ROOT / "runs"), name="river-eco-v4",
        seed=42, deterministic=True,
        patience=20,
        workers=4,   # Windows 兼容
    )


if __name__ == "__main__":
    main()

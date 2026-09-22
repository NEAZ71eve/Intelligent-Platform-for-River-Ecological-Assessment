"""YOLOv8n 训练 v5（河道生态评估 · 水域域协议修复迭代）。

数据：data/splits/unified-v4/dataset.yaml
  = unified-v2 五源（冻结划分，val/test 与 v2 完全一致）
  + MARINE 仅 train 子集 3600 图（valid/test 175 图划归 water-eval，见 eval_water.py）
  + SYNTH（Copy-Paste 合成 600 图，仅入 train）
与 v4 的唯一差异：marine valid/test 不再入 train → v5 与 v3 在 water-eval 同等可比。
超参：与 v3/v4 完全一致（yolov8n.pt / 640 / batch16 / 100 轮 / seed42）。

运行：cd inference && python training/train_yolo_v5.py
产出：runs/river-eco-v5/
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
        data=str(_ROOT / "data" / "splits" / "unified-v4" / "dataset.yaml"),
        epochs=100, imgsz=640, batch=16,
        project=str(_ROOT / "runs"), name="river-eco-v5",
        seed=42, deterministic=True,
        patience=20,
        workers=4,   # Windows 兼容
    )


if __name__ == "__main__":
    main()

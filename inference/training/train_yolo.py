"""YOLOv8n 训练（河道生态评估 v1）。

数据：data/splits/unified-v1/dataset.yaml（Task 4 产出，15 细类 id 与
class_mapping.yaml v1 冻结一致；当前仅 IWHR floater→misc_debris 有样本，
其余细类等 YRDG/FloW/TUDELFT/WATER-DET 数据到位后重训补充）。

运行：cd inference && python training/train_yolo.py
产出：runs/river-eco-v1/（results.csv、weights/best.pt 等）
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ultralytics import YOLO


def main():
    model = YOLO("yolov8n.pt")  # COCO 预训练权重（首次运行自动下载）
    model.train(
        data=str(_ROOT / "data" / "splits" / "unified-v1" / "dataset.yaml"),
        epochs=100, imgsz=640, batch=16,
        project=str(_ROOT / "runs"), name="river-eco-v1",
        seed=42, deterministic=True,   # 可重放
        patience=20,
        cache="disk",
        workers=0,  # Windows 多进程 DataLoader 易崩，改主进程加载
    )


if __name__ == "__main__":
    main()

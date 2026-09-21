"""YOLOv8n 训练（河道生态评估 v2 · 多类）。

数据：data/splits/unified-v2/dataset.yaml（5 源预处理产出，15 细类 id 与
class_mapping.yaml v1 冻结一致；覆盖 10/15 细类，5 个硬缺口类为 0 样本）。

运行：cd inference && python training/train_yolo.py
产出：runs/river-eco-v2/（results.csv、weights/best.pt 等）
选择：只看验证集选 checkpoint；test 一次性评估（门禁 4，见 TRAINING_WIKI.md §8）。
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
        data=str(_ROOT / "data" / "splits" / "unified-v2" / "dataset.yaml"),
        epochs=100, imgsz=640, batch=16,
        project=str(_ROOT / "runs"), name="river-eco-v3",
        seed=42, deterministic=True,   # 可重放
        patience=20,
        cache="disk",
        workers=4,  # Windows DataLoader：8 workers 验证阶段崩溃(DataLoader worker exited)，降至 4
    )


if __name__ == "__main__":
    main()

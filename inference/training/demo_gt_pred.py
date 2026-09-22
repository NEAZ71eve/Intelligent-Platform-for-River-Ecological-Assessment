#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GT vs Pred 叠加对比：5 张水域代表图。蓝框=GT 标注，绿框=v5 预测（conf=0.25）。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import cv2
from ultralytics import YOLO

WATER = _ROOT / "data" / "splits" / "water-eval"
OUT = _ROOT / "runs" / "demo-v5-water" / "gt_pred"
OUT.mkdir(parents=True, exist_ok=True)

DISPLAY = {
    "bottle": "瓶", "foam_board": "泡沫板", "water_plant": "水草", "algae_mass": "藻类团",
    "plastic": "塑料", "paper": "纸", "glass": "玻璃", "metal": "金属", "fabric": "织物",
    "misc_debris": "其他", "sewage_color": "黑臭水色", "foam_pollution": "泡沫污染",
    "outfall": "排污口", "bank_garbage": "岸带垃圾", "bank_encroach": "岸线侵占",
}

PICKS = [
    "W_valid_IMG_0091_JPG.rf.e7c296cd844f87aa347a3f1f48af9145.jpg",
    "W_test_IMG_0090_JPG.rf.7c2bb34a2a1aff56429fd30d218eac0e.jpg",
    "W_valid_IMG_20220919_164138_4_jpg.rf.95e0e82c7cb1129e8e48780b15fee729.jpg",
    "W_valid_marine-debris--57-_JPG.rf.a7f58af11a33f6555192286e513eeea7.jpg",
    "W_test_IMG_0088_JPG.rf.660f5f8dbf7d13400b2b63eaf6c251be.jpg",
]

model = YOLO(str(_ROOT / "runs" / "river-eco-v5" / "weights" / "best.pt"))

for fn in PICKS:
    img = cv2.imread(str(WATER / "images" / fn))
    if img is None:
        print("[skip]", fn); continue
    H, W = img.shape[:2]
    # GT 蓝框
    txt = WATER / "labels" / (fn[:-4] + ".txt")
    for line in txt.read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) >= 5:
            x, y, w, h = map(float, p[1:5])
            x1 = int((x - w / 2) * W); y1 = int((y - h / 2) * H)
            x2 = int((x + w / 2) * W); y2 = int((y + h / 2) * H)
            cv2.rectangle(img, (x1, y1), (x2, y2), (255, 128, 0), 2)  # 橙=GT
    # Pred 绿框
    r = model.predict(source=str(WATER / "images" / fn), conf=0.25, imgsz=640, verbose=False)[0]
    for xyxy, cid in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist()):
        x1, y1, x2, y2 = map(int, xyxy)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 200, 0), 2)
        label = DISPLAY.get(r.names[int(cid)], "?")
        cv2.putText(img, label, (x1, max(0, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 200, 0), 1, cv2.LINE_AA)
    out = OUT / fn
    cv2.imwrite(str(out), img)
    print(f"[ok] {fn[:36]}  ({W}x{H})")
print(f"产出目录: {OUT}")

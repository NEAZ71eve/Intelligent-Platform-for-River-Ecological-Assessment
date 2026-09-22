#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""水域域 held-out 评估（marine-debris640 valid+test，175 图）。

背景（report_v3_vs_v4.md §7/§8）：unified-v3 把 marine 全部 3774 图放入 train，
导致没有 held-out 水域测试集，v4 的水域提升只能靠 eval-v1/v2 间接佐证。
本轮（v5，unified-v4）把 marine valid+test 划为独立 water-eval：
  - v3：从未见过任何 marine 数据 → 诚实的水域泛化基线
  - v4：见过 marine valid/test（训练污染）→ 结果仅作训练拟合参考
  - v5：marine 只放 train 子集 → 与 v3 同等诚意的对比

用法：cd inference && python training/eval_water.py --weights runs/river-eco-v3/weights/best.pt ...
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from training.class_mapping import load_mapping

MARINE = Path(r"D:\HYHQ_data\.runtime\marine-debris640_jsd")
OUT = _ROOT / "data" / "splits" / "water-eval"
MARINE_CID_MAP = {0: "metal", 1: "foam_board", 2: "bottle", 3: "plastic", 4: "misc_debris"}


def build():
    mapping = load_mapping()
    fine_order = list(mapping["fine_labels"].keys())
    fine_id = {n: i for i, n in enumerate(fine_order)}
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "images").mkdir(parents=True)
    (OUT / "labels").mkdir(parents=True)
    n = 0
    inst = {}
    for sub in ("valid", "test"):
        for img in sorted((MARINE / sub / "images").glob("*.jpg")):
            txt = MARINE / sub / "labels" / f"{img.stem}.txt"
            if not txt.exists():
                continue
            lines = []
            for l in txt.read_text(encoding="utf-8").splitlines():
                p = l.split()
                if len(p) >= 5:
                    fine = MARINE_CID_MAP[int(p[0])]
                    lines.append(f"{fine_id[fine]} {p[1]} {p[2]} {p[3]} {p[4]}")
                    inst[fine] = inst.get(fine, 0) + 1
            if not lines:
                continue
            stem = f"W_{sub}_{img.stem}"
            dst_img = OUT / "images" / f"{stem}.jpg"
            try:
                os.link(img, dst_img)
            except OSError:
                shutil.copy2(img, dst_img)
            (OUT / "labels" / f"{stem}.txt").write_text("\n".join(lines) + "\n",
                                                        encoding="utf-8")
            n += 1
    (OUT / "dataset.yaml").write_text(
        f"path: {OUT.resolve()}\ntrain: images\nval: images\n"
        f"names:\n" + "".join(f"  {i}: {nm}\n" for i, nm in enumerate(fine_order)),
        encoding="utf-8")
    print(f"[ok] water-eval 构建: {n} 图；实例分布: {inst}")
    return n


def evaluate(weights: str):
    from ultralytics import YOLO
    model = YOLO(weights)
    m = model.val(data=str(OUT / "dataset.yaml"), imgsz=640, conf=0.25, iou=0.7,
                  max_det=300, verbose=False, plots=False)
    names = m.names
    ap_idx = list(m.box.ap_class_index)
    tag = Path(weights).parts[-3]
    print(f"\n=== {tag} @ water-eval（marine valid+test，175 图） ===")
    print(f"overall: P={m.box.mp:.4f} R={m.box.mr:.4f} "
          f"mAP50={m.box.map50:.4f} mAP50-95={m.box.map:.4f}")
    rows = [(names[int(cid)], m.box.p[pos], m.box.r[pos], m.box.ap50[pos])
            for pos, cid in enumerate(ap_idx)]
    for nm, p, r, ap in sorted(rows, key=lambda x: -x[3]):
        print(f"  {nm:<12} P={p:.3f} R={r:.3f} mAP50={ap:.3f}")
    return m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", nargs="+", required=True)
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    if args.rebuild or not (OUT / "dataset.yaml").exists():
        build()
    for w in args.weights:
        evaluate(w)

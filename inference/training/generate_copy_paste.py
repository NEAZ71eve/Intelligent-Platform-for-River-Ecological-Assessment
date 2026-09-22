#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Copy-Paste 离线合成：弱类（bottle/foam_board）实例粘贴到水面背景，扩充小目标样本。

依据 eval-v3-stage1 诊断：
  - bottle/foam_board test 召回 0.25/0.11，GT 框稀少（155/81 全部来自 TACO）
  - 小/微小目标召回崩盘（tiny 桶 0.70，paper tiny 0.23）
  - TACO 源域错配（陆地垃圾照 R=0.238）

方案：从 unified-v2 **train 划分**中取 bottle/foam_board GT 裁剪实例，
粘贴到 train 划分的 IWHR/YRDG 水面背景上（合成图与实例均不接触 val/test，
保证冻结评估协议不泄漏）。产出合成图池，由 prepare_unified_v3.py 纳入 train。

运行：cd inference && python training/generate_copy_paste.py
产出：data/synth_cp/（SYNT_*.jpg + SYNT_*.txt）
"""
import sys
import random
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PIL import Image

from training.class_mapping import load_mapping

SPLITS_JSON = _ROOT / "data" / "splits" / "unified-v2" / "splits.json"
OUT_DIR = _ROOT / "data" / "synth_cp"
N_SYNTH = 600           # 合成图数量
PASTE_MIN, PASTE_MAX = 3, 8   # 每图粘贴实例数
TARGET_AREA = (0.0008, 0.02)  # 粘贴目标相对面积（覆盖 tiny~medium 桶）
WEAK_CLASSES = {0: "bottle", 1: "foam_board"}  # class id → 名（class_mapping 顺序）
BG_SOURCES = {"IWHR", "YRDG"}
SEED = 42

FINE_ORDER = list(load_mapping()["fine_labels"].keys())
FINE_ID = {n: i for i, n in enumerate(FINE_ORDER)}


def iou_aabb(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def main():
    import json
    splits = json.loads(SPLITS_JSON.read_text(encoding="utf-8"))
    train = [r for r in splits["records"] if r["split"] == "train"]

    # 实例池：train 中含弱类框的记录
    inst_pool = []   # (img_path, cls_id, cx, cy, w, h)
    bg_pool = []     # (img_path, boxes)
    for r in train:
        boxes = r["boxes"]
        weak = [b for b in boxes if b["fine"] in ("bottle", "foam_board")]
        if weak:
            for b in weak:
                inst_pool.append((r["image"],
                                  {"bottle": 0, "foam_board": 1}[b["fine"]],
                                  b["cx"], b["cy"], b["w"], b["h"]))
        if r["source"] in BG_SOURCES:
            bg_pool.append((r["image"], boxes))
    print(f"[ok] 弱类实例 {len(inst_pool)} 个（train 划分）")
    print(f"[ok] 水面背景 {len(bg_pool)} 张（IWHR+YRDG train）")
    if not inst_pool or not bg_pool:
        print("[skip] 实例或背景为空")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # 清理旧产物（幂等重建）
    for f in OUT_DIR.glob("SYNT_*"):
        f.unlink()

    rng = random.Random(SEED)
    n_made, used_instances = 0, 0
    for i in range(N_SYNTH):
        bg_path, bg_boxes = rng.choice(bg_pool)
        try:
            bg = Image.open(bg_path).convert("RGB")
        except Exception:
            continue
        W, H = bg.size
        # 已有框（绝对像素 [x1,y1,x2,y2]）
        existing = [(max(0, (b["cx"] - b["w"] / 2) * W), max(0, (b["cy"] - b["h"] / 2) * H),
                     min(W, (b["cx"] + b["w"] / 2) * W), min(H, (b["cy"] + b["h"] / 2) * H))
                    for b in bg_boxes]
        new_labels = [(b["fine"], b["cx"], b["cy"], b["w"], b["h"])
                      for b in bg_boxes]
        n_paste = rng.randint(PASTE_MIN, PASTE_MAX)
        for _ in range(n_paste):
            src_path, cls_id, cx, cy, w, h = rng.choice(inst_pool)
            try:
                src = Image.open(src_path).convert("RGB")
            except Exception:
                continue
            sw, sh = src.size
            x1 = int(max(0, (cx - w / 2) * sw - w * sw * 0.04))
            y1 = int(max(0, (cy - h / 2) * sh - h * sh * 0.04))
            x2 = int(min(sw, (cx + w / 2) * sw + w * sw * 0.04))
            y2 = int(min(sh, (cy + h / 2) * sh + h * sh * 0.04))
            if x2 - x1 < 8 or y2 - y1 < 8:
                continue
            crop = src.crop((x1, y1, x2, y2))
            # 目标尺寸：随机落在 tiny~medium 桶
            area_ratio = rng.uniform(*TARGET_AREA)
            aspect = (y2 - y1) / max(1, x2 - x1)
            tw = (area_ratio * W * H) ** 0.5
            th = tw * aspect
            if tw < 6 or th < 6 or tw > W * 0.5 or th > H * 0.5:
                continue
            crop = crop.resize((int(tw), int(th)), Image.LANCZOS)
            # 位置：偏水面（y 在 30%~95%），尝试 10 次避开重埋已有框
            for _try in range(10):
                px = rng.randint(0, max(0, W - int(tw)))
                py = rng.randint(int(H * 0.30), max(int(H * 0.30), H - int(th)))
                box = (px, py, px + tw, py + th)
                if all(iou_aabb(box, e) < 0.3 for e in existing):
                    break
            else:
                continue
            bg.paste(crop, (px, py))
            existing.append(box)
            new_labels.append((("bottle" if cls_id == 0 else "foam_board"),
                               (px + tw / 2) / W, (py + th / 2) / H,
                               tw / W, th / H))
            used_instances += 1
        if len(new_labels) <= len(bg_boxes):
            continue  # 一个都没贴上
        stem = f"SYNT_{i:04d}"
        bg.save(OUT_DIR / f"{stem}.jpg", quality=92)
        with open(OUT_DIR / f"{stem}.txt", "w", encoding="utf-8") as f:
            for fine, cx, cy, w, h in new_labels:
                f.write(f"{FINE_ID[fine]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
        n_made += 1
        if (i + 1) % 100 == 0:
            print(f"[prog] {i + 1}/{N_SYNTH} 产出 {n_made}")
    print(f"[done] 合成图 {n_made} 张，粘贴实例 {used_instances} 个 → {OUT_DIR}")


if __name__ == "__main__":
    main()

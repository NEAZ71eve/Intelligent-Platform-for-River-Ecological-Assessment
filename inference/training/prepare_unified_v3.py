#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""unified-v3 构建：v2 五源 + marine-debris640 + Copy-Paste 合成 → 弱类补强。

依据 eval-v3-stage1 阶段性测试诊断（2026-09-21）：
  - bottle mAP50=0.221 / foam_board=0.095（GT 全来自 TACO，域错配 R=0.238）
  - marine-debris640（水面域，bottle 500 片 / foam 149 片）→ 主补强
  - synth_cp（Copy-Paste 合成 600 图 / 3241 实例）→ 小目标补强
  - supplement_bottle_foam 剔除（auto_label 类别 id 错误，疑似 v3 自标注污染）

冻结协议（保证 v3/v4 可比）：
  - v2 已有图（按 sha 匹配）沿用其 train/val/test 划分
  - 全部新增数据只进 train；val/test 与 unified-v2 完全一致（构建后校验）

类别映射（marine data.yaml: can/foam/plastic bottle/plastic/unknow）：
  can→metal, foam→foam_board, plastic bottle→bottle, plastic→plastic, unknow→misc_debris

运行：cd inference && python training/prepare_unified_v3.py
产出：data/splits/unified-v3/
"""
import sys
import os
import json
import random
import shutil
import hashlib
from pathlib import Path
from collections import Counter

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from training.class_mapping import load_mapping
from training.audit_datasets import _dhash
from training.prepare_unified_v2 import (
    scan_iwhr, scan_yolo, scan_taco, parse_yolo_txt,
    RUNTIME, CANSURF_CID_MAP, ISOOD_CID_MAP, YRDG_CID_MAP, IMAGE_EXTS,
)

V2_DIR = _ROOT / "data" / "splits" / "unified-v2"
OUT_DIR = _ROOT / "data" / "splits" / "unified-v3"
MARINE_DIR = RUNTIME / "marine-debris640_jsd"
SYNTH_DIR = _ROOT / "data" / "synth_cp"
MARINE_CID_MAP = {0: "metal", 1: "foam_board", 2: "bottle",
                  3: "plastic", 4: "misc_debris"}
SEED = 42


def scan_marine(src: Path):
    """marine-debris640（YOLO 布局 {train,valid,test}/{images,labels}）。
    返回 (img, boxes, subset) —— subset 用于输出文件名唯一化。"""
    recs = []
    for sub in ("train", "valid", "test"):
        img_root = src / sub / "images"
        lbl_root = src / sub / "labels"
        if not img_root.exists():
            continue
        for img in sorted(img_root.glob("*")):
            if img.suffix.lower() not in IMAGE_EXTS:
                continue
            txt = lbl_root / f"{img.stem}.txt"
            if not txt.exists():
                continue
            boxes = parse_yolo_txt(txt, MARINE_CID_MAP)
            if boxes:
                recs.append((str(img), boxes, sub))
    return recs


def scan_synth(src: Path):
    """synth_cp：SYNT_*.jpg + SYNT_*.txt（细类 id 已按 class_mapping 写好）。"""
    mapping = load_mapping()
    fine_order = list(mapping["fine_labels"].keys())
    recs = []
    for img in sorted(src.glob("SYNT_*.jpg")):
        txt = src / f"{img.stem}.txt"
        if not txt.exists():
            continue
        boxes = []
        for line in txt.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) >= 5:
                boxes.append((fine_order[int(p[0])], float(p[1]),
                              float(p[2]), float(p[3]), float(p[4])))
        if boxes:
            recs.append((str(img), boxes))
    return recs


def _link_or_copy(src: Path, dst: Path):
    """优先硬链接（同卷零空间开销），失败回退拷贝。v3 复用 v2 大部分图，避免磁盘翻倍。"""
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def build():
    mapping = load_mapping()
    fine_order = list(mapping["fine_labels"].keys())
    fine_id = {name: i for i, name in enumerate(fine_order)}

    # v2 冻结划分（sha → split）
    v2 = json.loads((V2_DIR / "splits.json").read_text(encoding="utf-8"))
    v2_sha_split = {r["sha"]: r["split"] for r in v2["records"]}
    v2_sha_set = set(v2_sha_split)
    print(f"[ok] unified-v2 冻结清单: {len(v2_sha_set)} 图")

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    # ---- 各源扫描（v2 五源沿用原适配器）----
    all_records = []  # (img, boxes, source, is_new)
    iwhr = RUNTIME / "IWHR_AI_Lable_Floater_V1"
    cans = RUNTIME / "CANSURF"
    iso = RUNTIME / "iSOOD"
    taco = RUNTIME / "TACO_git"
    yrdg = RUNTIME / "YRDG"

    if iwhr.exists():
        recs = scan_iwhr(iwhr)
        all_records += [(r[0], r[1], "IWHR", None) for r in recs]
        print(f"[ok] IWHR: {len(recs)}")
    if cans.exists():
        recs = scan_yolo(cans / "CANSURF", CANSURF_CID_MAP,
                         layout="split_outer", splits=["train", "val"])
        all_records += [(r[0], r[1], "CANSURF", None) for r in recs]
        print(f"[ok] CANSURF: {len(recs)}")
    if iso.exists():
        recs = scan_yolo(iso, ISOOD_CID_MAP)
        all_records += [(r[0], r[1], "iSOOD", None) for r in recs]
        print(f"[ok] iSOOD: {len(recs)}")
    if taco.exists():
        recs = scan_taco(taco)
        all_records += [(r[0], r[1], "TACO", None) for r in recs]
        print(f"[ok] TACO: {len(recs)}（已下载部分）")
    if yrdg.exists():
        recs = scan_yolo(yrdg, YRDG_CID_MAP,
                         layout="split_inner", splits=["train", "val", "test"])
        all_records += [(r[0], r[1], "YRDG", None) for r in recs]
        print(f"[ok] YRDG: {len(recs)}")

    n_v2src = len(all_records)

    if MARINE_DIR.exists():
        for img, boxes, sub in scan_marine(MARINE_DIR):
            all_records.append((img, boxes, "MARINE", sub))
        print(f"[ok] MARINE: {len([r for r in all_records if r[2] == 'MARINE'])}")
    else:
        print("[warn] marine-debris640 未就绪，跳过")
    if SYNTH_DIR.exists():
        recs = scan_synth(SYNTH_DIR)
        all_records += [(r[0], r[1], "SYNTH", None) for r in recs]
        print(f"[ok] SYNTH: {len(recs)}")

    print(f"[info] 原始记录: {len(all_records)}（v2 源 {n_v2src} + 新源 {len(all_records) - n_v2src}）")

    # ---- 去重 + 分配 ----
    seen = set()
    manifest = []
    n_new_in_v2, n_reused, n_dropped = 0, 0, 0
    for img, boxes, source, subset in all_records:
        p = Path(img)
        try:
            sha = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            dh = _dhash(p)
        except Exception as e:
            print(f"[warn] 读取失败 {img}: {e}")
            continue
        key = (dh, sha)
        if key in seen:
            n_dropped += 1
            continue
        seen.add(key)
        if sha in v2_sha_set:
            split = v2_sha_split[sha]      # 冻结沿用
            n_reused += 1
        else:
            split = "train"                # 新数据只进 train
            n_new_in_v2 += 1
        manifest.append({"image_src": str(p), "boxes": boxes, "source": source,
                         "subset": subset, "sha": sha, "dhash": dh, "split": split})

    print(f"[info] 去重 {n_dropped}；沿用 v2 划分 {n_reused}，新增进 train {n_new_in_v2}")

    # ---- 落盘 ----
    for sub in ("images", "labels"):
        for split in ("train", "val", "test"):
            (OUT_DIR / sub / split).mkdir(parents=True, exist_ok=True)

    out_records = []
    for r in manifest:
        img_src = Path(r["image_src"])
        split = r["split"]
        if r["source"] == "TACO":
            taco_data = RUNTIME / "TACO_git" / "data"
            rel = img_src.relative_to(taco_data).with_suffix("")
            stem = "TACO_" + rel.as_posix().replace("/", "_")
        elif r["source"] == "MARINE":
            stem = f"MARINE_{r['subset']}_{img_src.stem}"
        elif r["source"] == "SYNTH":
            stem = img_src.stem
        else:
            stem = f"{r['source']}_{img_src.stem}"
        img_dst = OUT_DIR / "images" / split / f"{stem}{img_src.suffix}"
        _link_or_copy(img_src, img_dst)
        label_dst = OUT_DIR / "labels" / split / f"{stem}.txt"
        with open(label_dst, "w", encoding="utf-8") as f:
            for fine, cx, cy, w, h in r["boxes"]:
                f.write(f"{fine_id[fine]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
        out_records.append({"image": str(img_dst), "label": str(label_dst),
                            "source": r["source"], "sha": r["sha"],
                            "split": split,
                            "boxes": [{"fine": fn, "cx": c, "cy": y, "w": w, "h": h}
                                      for fn, c, y, w, h in r["boxes"]]})

    # ---- 校验冻结协议：val/test 与 v2 完全一致 ----
    v2_val_test = {r["sha"] for r in v2["records"] if r["split"] != "train"}
    new_val_test = {r["sha"] for r in out_records if r["split"] != "train"}
    assert v2_val_test == new_val_test, \
        f"冻结协议被破坏！v2 val/test {len(v2_val_test)} vs v3 {len(new_val_test)}"
    print(f"[ok] 冻结校验通过：val/test {len(new_val_test)} 图与 v2 一致")

    dataset_yaml = OUT_DIR / "dataset.yaml"
    dataset_yaml.write_text(
        f"path: {OUT_DIR.resolve()}\n"
        f"train: images/train\nval: images/val\ntest: images/test\n"
        f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(fine_order)),
        encoding="utf-8")

    counts = {s: sum(1 for r in out_records if r["split"] == s)
              for s in ("train", "val", "test")}
    splits_json = {
        "seed": SEED, "version": 3,
        "notes": "v2 五源冻结划分 + MARINE/SYNTH 新增仅入 train；"
                 "supplement_bottle_foam 剔除（标注污染）",
        "counts": {**counts, "unique": len(out_records),
                   "raw": len(all_records)},
        "fine_labels": fine_order, "records": out_records,
    }
    (OUT_DIR / "splits.json").write_text(
        json.dumps(splits_json, ensure_ascii=False, indent=2), encoding="utf-8")

    src_cnt = Counter(r["source"] for r in out_records)
    fine_cnt = Counter(b["fine"] for r in out_records for b in r["boxes"])
    print(f"\n[ok] 划分: {counts}")
    print(f"[ok] 各源: {dict(src_cnt)}")
    print(f"[ok] 框总数: {sum(fine_cnt.values())}")
    print("[ok] 细类分布:")
    for fine in fine_order:
        print(f"      {fine}: {fine_cnt.get(fine, 0)}")
    print(f"[ok] 产出: {OUT_DIR}")


if __name__ == "__main__":
    build()

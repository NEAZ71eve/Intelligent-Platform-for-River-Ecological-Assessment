#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""多源训练前预处理：IWHR / CANSURF / iSOOD / TACO / YRDG → 统一 15 细类 YOLO 数据集。

数据源（D0 决策门后实际到位，2026-09-19）：
  - IWHR_AI_Lable_Floater_V1: VOC XML（Annotations/ + JPEGImages/），floater → misc_debris
  - CANSURF: YOLO 单类 debris → metal（水面金属罐专项）
  - iSOOD: YOLO 单类（cid=0）→ outfall（排污口检测）
  - TACO: COCO annotations.json + Flickr 图片（batch_N/），60 类 → 细类映射表
  - YRDG: YOLO 7 类（自带 train/val/test），映射到细类

流程：多源适配 → dHash+SHA 去重 → 固定种子(42)划分 → 统一 YOLO 输出。
产出：<out>/images|labels/{train,val,test}/ + dataset.yaml + splits.json
运行：python training/prepare_unified_v2.py
"""
import sys
import json
import random
import shutil
import hashlib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import xml.etree.ElementTree as ET
from training.class_mapping import load_mapping
from training.audit_datasets import _dhash

# ---------------- 路径配置（数据操作统一在 D 盘） ----------------
RUNTIME = Path(r"D:\HYHQ_data\.runtime")
OUT_DIR = Path(r"D:\WeChatProjects\HYHQ\inference\data\splits\unified-v2")
SEED = 42
RATIOS = (0.70, 0.15, 0.15)
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

# ---------------- 各源类别 → 细类 映射 ----------------
# CANSURF / iSOOD（YOLO cid 固定）
CANSURF_CID_MAP = {0: "metal"}          # data.yaml: names=['debris']
ISOOD_CID_MAP = {0: "outfall"}          # 单类排污口
# YRDG（data.yaml: plastic/paper/glass/metal/fabricfiber/nature/others）
YRDG_CID_MAP = {0: "plastic", 1: "paper", 2: "glass", 3: "metal",
                4: "fabric", 5: "water_plant", 6: "misc_debris"}
# TACO COCO 60 类 → 细类
TACO_CAT_MAP = {
    "bottle": ["Clear plastic bottle", "Other plastic bottle"],
    "plastic": ["Other plastic", "Plastic film", "Other plastic container",
                "Other plastic cup", "Plastic straw", "Plastic utensils",
                "Plastic lid", "Plastic bottle cap", "Single-use carrier bag",
                "Polypropylene bag", "Squeezable tube", "Tupperware",
                "Disposable plastic cup", "Disposable food container",
                "Spread tub", "Six pack rings", "Other plastic wrapper",
                "Crisp packet", "Garbage bag", "Plastified paper bag",
                "Plastic glooves"],
    "paper": ["Corrugated carton", "Other carton", "Egg carton", "Meal carton",
              "Pizza box", "Paper bag", "Paper cup", "Paper straw",
              "Magazine paper", "Normal paper", "Wrapping paper",
              "Toilet tube", "Drink carton", "Tissues", "Cigarette",
              "Carded blister pack"],
    "glass": ["Broken glass", "Glass bottle", "Glass cup", "Glass jar"],
    "metal": ["Drink can", "Food Can", "Metal bottle cap", "Metal lid",
              "Aluminium foil", "Aluminium blister pack", "Scrap metal",
              "Pop tab", "Aerosol"],
    "foam_board": ["Styrofoam piece", "Foam cup", "Foam food container"],
    "fabric": ["Rope & strings", "Shoe"],
    "misc_debris": ["Food waste", "Battery", "Unlabeled litter"],
}
TACO_NAME_TO_FINE = {}
for fine, names in TACO_CAT_MAP.items():
    for n in names:
        TACO_NAME_TO_FINE[n] = fine


def parse_yolo_txt(txt_path, cid_map):
    """YOLO txt → [(fine, cx, cy, w, h)]，cid 通过 cid_map 映射。"""
    out = []
    for line in txt_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cid = int(parts[0])
        fine = cid_map.get(cid)
        if fine is None:
            print(f"[warn] 未知 cid {cid} in {txt_path}")
            continue
        out.append((fine, float(parts[1]), float(parts[2]),
                    float(parts[3]), float(parts[4])))
    return out


def parse_voc_xml(xml_path):
    """VOC XML → [(raw_label, cx, cy, w, h)]。"""
    root = ET.parse(xml_path).getroot()
    w = int(root.find("size/width").text)
    h = int(root.find("size/height").text)
    out = []
    for obj in root.findall("object"):
        name = obj.find("name").text
        bb = obj.find("bndbox")
        x1, y1 = float(bb.find("xmin").text), float(bb.find("ymin").text)
        x2, y2 = float(bb.find("xmax").text), float(bb.find("ymax").text)
        out.append((name, (x1 + x2) / 2 / w, (y1 + y2) / 2 / h,
                    (x2 - x1) / w, (y2 - y1) / h))
    return out


def scan_iwhr(src: Path):
    """VOC 结构：JPEGImages/*.jpg + Annotations/*.xml。floater→misc_debris。"""
    recs = []
    img_dir = src / "JPEGImages"
    ann_dir = src / "Annotations"
    if not img_dir.exists():
        return recs
    for img in sorted(img_dir.rglob("*")):
        if img.suffix.lower() not in IMAGE_EXTS:
            continue
        xml = ann_dir / f"{img.stem}.xml"
        if not xml.exists():
            continue
        boxes = [(("misc_debris" if name == "floater" else name),
                  cx, cy, w, h) for name, cx, cy, w, h in parse_voc_xml(xml)]
        recs.append((str(img), boxes))
    return recs


def scan_yolo(src: Path, cid_map, layout="flat", splits=None):
    """YOLO 结构扫描，支持三种布局：
    - layout="flat":       src/{images,labels}/**（iSOOD）
    - layout="split_outer": src/{split}/{images,labels}/**（CANSURF，splits=[train,val]）
    - layout="split_inner": src/{images,labels}/{split}/**（YRDG，splits=[train,val,test]）
    """
    recs = []
    if layout == "flat":
        pairs = [(src / "images", src / "labels")]
    else:
        pairs = [(src / sub / "images", src / sub / "labels") if layout == "split_outer"
                 else (src / "images" / sub, src / "labels" / sub)
                 for sub in (splits or [])]
    for img_root, lbl_root in pairs:
        if not img_root.exists():
            continue
        for img in sorted(img_root.rglob("*")):
            if img.suffix.lower() not in IMAGE_EXTS:
                continue
            txt = lbl_root / f"{img.stem}.txt"
            if not txt.exists():
                continue
            boxes = parse_yolo_txt(txt, cid_map)
            if boxes:
                recs.append((str(img), boxes))
    return recs


def scan_taco(src: Path):
    """COCO annotations.json + 已下载图片（batch_N/）。图片缺失自动跳过。"""
    ann_path = src / "data" / "annotations.json"
    if not ann_path.exists():
        print("[skip] TACO annotations.json 缺失")
        return []
    ann = json.loads(ann_path.read_text(encoding="utf-8"))
    cat_id2fine = {}
    for c in ann["categories"]:
        fine = TACO_NAME_TO_FINE.get(c["name"])
        if fine:
            cat_id2fine[c["id"]] = fine
    img_id2info = {im["id"]: im for im in ann["images"]}
    img_id2boxes = {}
    for a in ann["annotations"]:
        iid = a["image_id"]
        fine = cat_id2fine.get(a["category_id"])
        if not fine:
            continue
        x, y, w, h = a["bbox"]
        img_w, img_h = img_id2info[iid]["width"], img_id2info[iid]["height"]
        cx, cy = (x + w / 2) / img_w, (y + h / 2) / img_h
        nw, nh = w / img_w, h / img_h
        img_id2boxes.setdefault(iid, []).append((fine, cx, cy, nw, nh))
    recs = []
    for iid, info in img_id2info.items():
        boxes = img_id2boxes.get(iid)
        if not boxes:
            continue
        img = src / "data" / info["file_name"]
        if not img.exists():
            continue  # TACO 下载未完成时跳过缺失图，重跑即全量
        recs.append((str(img), boxes))
    return recs


def build():
    mapping = load_mapping()
    fine_order = list(mapping["fine_labels"].keys())
    fine_id = {name: i for i, name in enumerate(fine_order)}

    # 输出目录整体重建，避免上次运行的旧划分残留污染训练
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    # 各源扫描
    all_records = []
    iwhr = RUNTIME / "IWHR_AI_Lable_Floater_V1"
    cans = RUNTIME / "CANSURF"
    iso = RUNTIME / "iSOOD"
    taco = RUNTIME / "TACO_git"
    yrdg = RUNTIME / "YRDG"

    if iwhr.exists():
        recs = scan_iwhr(iwhr)
        all_records += [(r[0], r[1], "IWHR") for r in recs]
        print(f"[ok] IWHR: {len(recs)} 图")
    if cans.exists():
        recs = scan_yolo(cans / "CANSURF", CANSURF_CID_MAP,
                         layout="split_outer", splits=["train", "val"])
        all_records += [(r[0], r[1], "CANSURF") for r in recs]
        print(f"[ok] CANSURF: {len(recs)} 图")
    if iso.exists():
        recs = scan_yolo(iso, ISOOD_CID_MAP)
        all_records += [(r[0], r[1], "iSOOD") for r in recs]
        print(f"[ok] iSOOD: {len(recs)} 图")
    if taco.exists():
        recs = scan_taco(taco)
        all_records += [(r[0], r[1], "TACO") for r in recs]
        print(f"[ok] TACO: {len(recs)} 图（已下载部分）")
    if yrdg.exists():
        recs = scan_yolo(yrdg, YRDG_CID_MAP,
                         layout="split_inner", splits=["train", "val", "test"])
        all_records += [(r[0], r[1], "YRDG") for r in recs]
        print(f"[ok] YRDG: {len(recs)} 图")

    print(f"[info] 原始记录总数: {len(all_records)}")

    # 去重（sha + dhash）
    seen = set()
    unique = []
    for img, boxes, source in all_records:
        p = Path(img)
        try:
            sha = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            dh = _dhash(p)
        except Exception as e:
            print(f"[warn] 读取失败 {img}: {e}")
            continue
        key = (dh, sha)
        if key in seen:
            continue
        seen.add(key)
        unique.append({"image": str(p), "boxes": boxes, "source": source,
                       "sha": sha, "dhash": dh})
    print(f"[info] 去重后: {len(unique)} 图")

    # 固定种子划分
    rng = random.Random(SEED)
    recs = sorted(unique, key=lambda r: r["image"])
    rng.shuffle(recs)
    n = len(recs)
    a, b = int(n * RATIOS[0]), int(n * (RATIOS[0] + RATIOS[1]))
    split_of = {}
    for r in recs[:a]:
        split_of[r["image"]] = "train"
    for r in recs[a:b]:
        split_of[r["image"]] = "val"
    for r in recs[b:]:
        split_of[r["image"]] = "test"

    for sub in ("images", "labels"):
        for split in ("train", "val", "test"):
            (OUT_DIR / sub / split).mkdir(parents=True, exist_ok=True)

    manifest = []
    for r in unique:
        split = split_of[r["image"]]
        img_src = Path(r["image"])
        if r["source"] == "TACO":
            # TACO 图片在 batch_N/ 下，不同 batch 编号重复 → 用相对路径保证唯一
            rel = img_src.relative_to(taco / "data").with_suffix("")
            stem = "TACO_" + rel.as_posix().replace("/", "_")
        else:
            stem = f"{r['source']}_{img_src.stem}"
        img_dst = OUT_DIR / "images" / split / f"{stem}{img_src.suffix}"
        if not img_dst.exists():
            shutil.copy2(img_src, img_dst)
        label_dst = OUT_DIR / "labels" / split / f"{stem}.txt"
        with open(label_dst, "w", encoding="utf-8") as f:
            for fine, cx, cy, w, h in r["boxes"]:
                f.write(f"{fine_id[fine]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
        manifest.append({"image": str(img_dst), "label": str(label_dst),
                         "source": r["source"], "sha": r["sha"], "split": split,
                         "boxes": [{"fine": fn, "cx": c, "cy": y, "w": w, "h": h}
                                   for fn, c, y, w, h in r["boxes"]]})

    dataset_yaml = OUT_DIR / "dataset.yaml"
    dataset_yaml.write_text(
        f"path: {OUT_DIR.resolve()}\n"
        f"train: images/train\nval: images/val\ntest: images/test\n"
        f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(fine_order)),
        encoding="utf-8")

    splits_json = {
        "seed": SEED, "version": 2,
        "counts": {"train": sum(1 for m in manifest if m["split"] == "train"),
                   "val": sum(1 for m in manifest if m["split"] == "val"),
                   "test": sum(1 for m in manifest if m["split"] == "test"),
                   "unique": len(unique), "raw": len(all_records)},
        "fine_labels": fine_order, "records": manifest,
    }
    (OUT_DIR / "splits.json").write_text(
        json.dumps(splits_json, ensure_ascii=False, indent=2), encoding="utf-8")

    # 汇总统计
    from collections import Counter
    src_cnt = Counter(m["source"] for m in manifest)
    fine_cnt = Counter(b["fine"] for m in manifest for b in m["boxes"])
    box_total = sum(len(m["boxes"]) for m in manifest)
    print(f"\n[ok] 划分: {splits_json['counts']}")
    print(f"[ok] 各源: {dict(src_cnt)}")
    print(f"[ok] 框总数: {box_total}")
    print("[ok] 细类分布:")
    for fine in fine_order:
        print(f"      {fine}: {fine_cnt.get(fine, 0)}")
    print(f"[ok] 产出: {OUT_DIR}")


if __name__ == "__main__":
    build()

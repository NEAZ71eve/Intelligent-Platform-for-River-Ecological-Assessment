"""各源标注转换为统一细类 YOLO 格式，dHash 分组去重，固定种子划分并冻结清单。

数据源（D0 决策门后）：IWHR_AI_Lable_Floater_V1（主力）、YRDG、FloW-Img、TUDELFT、
WATER-DET（待获取）。各源原始标签 → 细类的归一化在 SOURCES_LABEL_MAP 中维护，
细类 → 评估大类的映射见 class_mapping.yaml。

运行：python training/build_dataset.py
产出：data/splits/unified-v1/{images,labels}/{train,val,test}/ + dataset.yaml + splits.json
"""
import sys
from pathlib import Path

# 兼容直接 `python training/build_dataset.py` 运行：把 inference/ 加入 sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import hashlib, json, random, shutil, xml.etree.ElementTree as ET
from training.class_mapping import load_mapping
from training.audit_datasets import _dhash

# 各源原始标签 → 细类（Task 3 fine_labels）
# 键值以 Task 2 审计到的实际标签为准；当前为依据论文/README 的初版，数据到位后修正
SOURCES_LABEL_MAP = {
    "IWHR_AI_Lable_Floater_V1": {
        "bottle": "bottle", "foam": "foam_board", "foam_board": "foam_board",
        "water_plant": "water_plant", "watergrass": "water_plant",
        "algae": "algae_mass", "algae_mass": "algae_mass",
        "plastic": "plastic", "paper": "paper", "glass": "glass",
        "metal": "metal", "fabric": "fabric",
    },
    "YRDG": {
        "bottle": "bottle", "plastic": "plastic", "paper": "paper",
        "glass": "glass", "metal": "metal", "fabric": "fabric", "trash": "misc_debris",
    },
    "FloW-Img": {"bottle": "bottle"},
    "TUDELFT": {
        "plastic": "plastic", "bottle": "bottle", "bag": "plastic",
        "misc": "misc_debris", "trash": "misc_debris",
    },
    "WATER-DET": {
        "Sewage": "sewage_color", "sewage": "sewage_color",
        "Foam Pollution": "foam_pollution", "foam_pollution": "foam_pollution",
        "Garbage": "bank_garbage", "bank_garbage": "bank_garbage",
        "Outfall": "outfall", "outfall": "outfall",
        "Bank Encroachment": "bank_encroach", "bank_encroach": "bank_encroach",
    },
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def convert_voc_annotation(xml_path: Path) -> list:
    """VOC XML → YOLO 归一化 [(label, cx, cy, w, h), ...]。"""
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


def split_records(records: list, seed: int = 42,
                  ratios=(0.7, 0.15, 0.15)) -> tuple:
    """固定种子划分（train/val/test），可重放。"""
    rng = random.Random(seed)
    recs = sorted(records)
    rng.shuffle(recs)
    n = len(recs)
    a, b = int(n * ratios[0]), int(n * (ratios[0] + ratios[1]))
    return recs[:a], recs[a:b], recs[b:]


def _fine_label_order(mapping: dict) -> list:
    """class_mapping.yaml 中 fine_labels 的有序列表（index 即 class_id）。"""
    return list(mapping["fine_labels"].keys())


def _normalize_source_label(source: str, raw: str) -> str:
    """源原始标签 → 细类；未知返回 misc_debris 并打印警告。"""
    table = SOURCES_LABEL_MAP.get(source, {})
    if raw in table:
        return table[raw]
    for k, v in table.items():
        if k.lower() == raw.lower():
            return v
    print(f"[warn] 未知源标签 {source!r}/{raw!r} → misc_debris")
    return "misc_debris"


def build_unified(runtime_dir: Path, out_dir: Path, seed: int = 42) -> dict:
    """扫描 .runtime/<SOURCE>/ → 统一 YOLO 数据集 + 冻结划分清单。

    每源目录约定：images/ + labels/（VOC XML 或 YOLO txt 任一）。
    产出：out_dir/{images,labels}/{train,val,test}/ + dataset.yaml + splits.json
    """
    mapping = load_mapping()
    fine_order = _fine_label_order(mapping)
    fine_id = {name: i for i, name in enumerate(fine_order)}

    records = []
    for src_dir in sorted(runtime_dir.glob("*/")):
        source = src_dir.name
        if source not in SOURCES_LABEL_MAP:
            print(f"[skip] 未知源目录 {source}")
            continue
        if (src_dir / "images").exists():
            imgs = [p for p in (src_dir / "images").rglob("*")
                    if p.suffix.lower() in IMAGE_EXTS]
        else:
            imgs = [p for p in src_dir.rglob("*")
                    if p.suffix.lower() in IMAGE_EXTS and "labels" not in p.parts]
        for img in imgs:
            stem = img.stem
            label_xml = src_dir / "labels" / f"{stem}.xml"
            label_txt = src_dir / "labels" / f"{stem}.txt"
            boxes = []
            if label_xml.exists():
                for raw, cx, cy, w, h in convert_voc_annotation(label_xml):
                    fine = _normalize_source_label(source, raw)
                    boxes.append((fine, cx, cy, w, h))
            elif label_txt.exists():
                for line in label_txt.read_text(encoding="utf-8").splitlines():
                    parts = line.split()
                    if len(parts) < 5:
                        continue
                    cid, cx, cy, w, h = parts[:5]
                    if cid.isdigit():
                        fine = fine_order[int(cid)] if int(cid) < len(fine_order) else "misc_debris"
                    else:
                        fine = _normalize_source_label(source, cid)
                    boxes.append((fine, float(cx), float(cy), float(w), float(h)))
            if not boxes:
                continue
            sha = hashlib.sha256(img.read_bytes()).hexdigest()[:16]
            dh = _dhash(img)
            records.append({"source": source, "image": str(img), "sha": sha,
                            "dhash": dh, "boxes": boxes})

    seen, unique = set(), []
    for r in records:
        key = (r["dhash"], r["sha"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    tr, va, te = split_records([r["image"] for r in unique], seed=seed)
    split_of = {}
    for img in tr: split_of[img] = "train"
    for img in va: split_of[img] = "val"
    for img in te: split_of[img] = "test"

    for sub in ("images", "labels"):
        for split in ("train", "val", "test"):
            (out_dir / sub / split).mkdir(parents=True, exist_ok=True)

    manifest_records = []
    for r in unique:
        split = split_of[r["image"]]
        img_src = Path(r["image"])
        img_dst = out_dir / "images" / split / f"{r['source']}_{img_src.stem}{img_src.suffix}"
        if not img_dst.exists():
            shutil.copy2(img_src, img_dst)
        label_dst = out_dir / "labels" / split / f"{r['source']}_{img_src.stem}.txt"
        with open(label_dst, "w", encoding="utf-8") as f:
            for fine, cx, cy, w, h in r["boxes"]:
                f.write(f"{fine_id[fine]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
        manifest_records.append({"image": str(img_dst), "label": str(label_dst),
                                 "source": r["source"], "sha": r["sha"],
                                 "split": split, "boxes": [
                                     {"fine": fine, "cx": cx, "cy": cy, "w": w, "h": h}
                                     for fine, cx, cy, w, h in r["boxes"]]})

    dataset_yaml = out_dir / "dataset.yaml"
    dataset_yaml.write_text(
        f"path: {out_dir.resolve()}\n"
        f"train: images/train\nval: images/val\ntest: images/test\n"
        f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(fine_order)),
        encoding="utf-8")

    splits_json = {"seed": seed, "counts": {"train": len(tr), "val": len(va), "test": len(te),
                                           "unique": len(unique), "raw": len(records)},
                   "fine_labels": fine_order, "records": manifest_records}
    (out_dir / "splits.json").write_text(json.dumps(splits_json, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return splits_json


if __name__ == "__main__":
    runtime = Path(__file__).parent.parent / ".runtime"
    out = Path(__file__).parent.parent / "data" / "splits" / "unified-v1"
    if not runtime.exists() or not any(runtime.iterdir()):
        print(f"[skip] {runtime} 不存在或为空——数据集下载后运行：python training/build_dataset.py")
        sys.exit(0)
    report = build_unified(runtime, out)
    print(f"[ok] 划分完成：{report['counts']}")
    print(f"[ok] 产出目录：{out}")

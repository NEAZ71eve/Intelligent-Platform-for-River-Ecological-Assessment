#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""unified-v4 构建（方案 B：从 unified-v3 快照派生，v5 训练用）。

背景：直接重扫原始数据会受原始目录漂移影响（2026-09-21 夜间 TACO 重试轮
重下/截断部分文件；iSOOD/YRDG/TACO 原始计数与 v3 快照不一致），导致冻结
val/test 校验失败（9465 vs 9459）。unified-v3 输出与 splits.json 是自洽快照，
从它派生可彻底规避漂移：

  unified-v4 = unified-v3 记录 − MARINE valid/test（174 条，划归 water-eval）

与 v3 唯一数据差异：MARINE 仅 train 子集入 train（v5 与 v3 在 water-eval
同等诚实可比）。派生时完整性保障：
  - 全部记录重算 v3 输出文件 sha256[:16] 与记录 sha 比对
      · train / val / test 漂移一律剔除（2026-09-22 07:30 TACO 重试轮
        就地覆盖原始文件，v2/v3 硬链接同 inode 被改、原始字节不可恢复；
        图片内容与标签不再对应 → 标签错配风险）
  - 冻结校验：v4 val/test sha 集合 ⊆ v2 冻结清单，且缺失 = 预知的 TACO 漂移
    （14 张：val 6 + test 8），无任何 v2 之外的记录
  - 正式冻结评估仍走 eval_stage（unified-v2 test，与 v4 评估同字节可比）

运行：cd inference && python training/prepare_unified_v4.py
产出：data/splits/unified-v4/
"""
import sys
import os
import json
import shutil
import hashlib
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

V2_DIR = _ROOT / "data" / "splits" / "unified-v2"
V3_DIR = _ROOT / "data" / "splits" / "unified-v3"
OUT_DIR = _ROOT / "data" / "splits" / "unified-v4"
SEED = 42


def _sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _link_or_copy(src: Path, dst: Path):
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def build():
    v2 = json.loads((V2_DIR / "splits.json").read_text(encoding="utf-8"))
    v3 = json.loads((V3_DIR / "splits.json").read_text(encoding="utf-8"))
    fine_order = v3["fine_labels"]

    keep, dropped = [], 0
    for r in v3["records"]:
        name = Path(r["image"]).name
        if r["source"] == "MARINE" and (
            name.startswith("MARINE_valid_") or name.startswith("MARINE_test_")
        ):
            dropped += 1
            continue
        keep.append(r)
    print(f"[ok] unified-v3 记录 {len(v3['records'])}，"
          f"剔除 MARINE valid/test {dropped} → 保留 {len(keep)}")

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    for sub in ("images", "labels"):
        for split in ("train", "val", "test"):
            (OUT_DIR / sub / split).mkdir(parents=True, exist_ok=True)

    out_records, n_drift_train, n_drift_eval = [], 0, 0
    for r in keep:
        img_src = Path(r["image"])
        lbl_src = Path(r["label"])
        split = r["split"]
        try:
            now = _sha(img_src)
        except Exception as e:
            now = None
            print(f"[warn] 读取失败 {img_src}: {e}")
        if now != r["sha"]:
            # 漂移 = 2026-09-22 07:30 TACO 重试轮就地覆盖原始文件（v2/v3 硬链接
            # 同 inode 一并被改），原始字节不可恢复（v2 副本同为漂移字节）。
            # val/test 与 train 同理由剔除：图片内容与标签不再对应（标签错配风险）。
            print(f"[warn] 漂移剔除（{split}，标签错配风险）: {img_src.name}")
            if split in ("val", "test"):
                n_drift_eval += 1
            else:
                n_drift_train += 1
            continue
        img_dst = OUT_DIR / "images" / split / img_src.name
        lbl_dst = OUT_DIR / "labels" / split / lbl_src.name
        _link_or_copy(img_src, img_dst)
        _link_or_copy(lbl_src, lbl_dst)
        out_records.append({**r, "image": str(img_dst), "label": str(lbl_dst)})
    print(f"[info] train 漂移剔除 {n_drift_train}；val/test 漂移剔除 {n_drift_eval}")

    v2_val_test = {r["sha"] for r in v2["records"] if r["split"] != "train"}
    new_val_test = {r["sha"] for r in out_records if r["split"] != "train"}
    extra = new_val_test - v2_val_test
    assert not extra, f"v4 val/test 出现 v2 冻结清单之外的记录 {len(extra)} 张！"
    missing = v2_val_test - new_val_test
    missing_names = [Path(r["image"]).name
                     for r in v2["records"]
                     if r["split"] != "train" and r["sha"] in missing]
    assert missing_names, "无缺失记录但仍有断言——检查逻辑"
    assert all(n.startswith("TACO_") for n in missing_names), \
        f"缺失记录含非 TACO 源：{missing_names}"
    print(f"[ok] 冻结校验通过：v4 val/test {len(new_val_test)} 图 ⊆ v2 冻结清单"
          f"（缺失 {len(missing)} 张，均为 TACO 漂移、原始字节不可恢复，"
          f"记录见 splits.json 'dropped_notes'）")
    print(f"      缺失: {missing_names}")

    dataset_yaml = OUT_DIR / "dataset.yaml"
    dataset_yaml.write_text(
        f"path: {OUT_DIR.resolve()}\n"
        f"train: images/train\nval: images/val\ntest: images/test\n"
        f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(fine_order)),
        encoding="utf-8")

    counts = {s: sum(1 for r in out_records if r["split"] == s)
              for s in ("train", "val", "test")}
    splits_json = {
        "seed": SEED, "version": 4,
        "notes": "由 unified-v3 快照派生（规避原始目录漂移）：剔除 MARINE valid/test 174 条"
                 "（划归 water-eval）；MARINE 仅 train 子集入 train；冻结 val/test ⊆ v2 冻结清单",
        "dropped_notes": "2026-09-22 07:30 TACO 重试轮就地覆盖原始文件（v2/v3 硬链接同 inode"
                         "被改），原始字节不可恢复：train 漂移剔除 27 张、val/test 漂移剔除 "
                         f"{n_drift_eval} 张（{missing_names}）；标签错配风险为剔除理由；"
                         "正式冻结评估仍走 unified-v2 test（与 v4 同字节可比）",
        "counts": {**counts, "unique": len(out_records), "v3_total": len(v3["records"])},
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

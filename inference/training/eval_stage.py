#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""阶段性测试（stage test）：v3 模型对 unified-v2 test 冻结划分 + eval-v1/v2 泛化集。

产出（runs/eval-v3-stage1/）：
  1. metrics_test.json   — ultralytics 标准逐类 P/R/mAP50/mAP50-95（test 4733 图）
  2. diag_test.json      — 自定义诊断：混淆对（GT→Pred 错配）、按 GT 面积分桶召回、
                           按数据源分层 P/R、逐类 FP 构成
  3. eval_external.json  — eval-v1/v2（43 图，无 GT）场景级检出率定性评估
  4. report.md           — 汇总报告（人读）

运行：cd inference && python training/eval_stage.py
"""
import sys
import json
from pathlib import Path
from collections import defaultdict, Counter

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ultralytics import YOLO

# ---------------- 配置（可用 --weights PATH --tag NAME 覆盖） ----------------
_args = sys.argv[1:]
WEIGHTS = _ROOT / "runs" / "river-eco-v3" / "weights" / "best.pt"
OUT_DIR = _ROOT / "runs" / "eval-v3-stage1"
MODEL_TITLE = "v3"
i = 0
while i < len(_args):
    if _args[i] == "--weights" and i + 1 < len(_args):
        WEIGHTS = Path(_args[i + 1]); i += 2
    elif _args[i] == "--tag" and i + 1 < len(_args):
        MODEL_TITLE = _args[i + 1]
        OUT_DIR = _ROOT / "runs" / f"eval-{MODEL_TITLE}-stage1"
        i += 2
    else:
        i += 1
DATASET_YAML = _ROOT / "data" / "splits" / "unified-v2" / "dataset.yaml"
SPLITS_JSON = _ROOT / "data" / "splits" / "unified-v2" / "splits.json"
EVAL_DIRS = [Path(r"D:\HYHQ_data\eval-v1"), Path(r"D:\HYHQ_data\eval-v2")]
CONF = 0.25          # 标准评估阈值
IOU_MATCH = 0.50     # TP 匹配阈值（诊断用）
# GT 相对面积分桶（占整图比例）：tiny <0.1%，small 0.1–1%，medium 1–8%，large >8%
AREA_BUCKETS = [("tiny<0.1%", 0.0, 0.001), ("small0.1-1%", 0.001, 0.01),
                ("medium1-8%", 0.01, 0.08), ("large>8%", 0.08, 1.0)]


def area_bucket(rel_area: float) -> str:
    for name, lo, hi in AREA_BUCKETS:
        if lo <= rel_area < hi:
            return name
    return AREA_BUCKETS[-1][0]


def iou_xywhn(a, b) -> float:
    """两个 (cx,cy,w,h) 归一化框的 IoU。"""
    ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2
    ax2, ay2 = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2
    bx2, by2 = b[0] + b[2] / 2, b[1] + b[3] / 2
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def run_standard_val(model) -> dict:
    """ultralytics 标准评估：test 划分逐类指标。"""
    metrics = model.val(data=str(DATASET_YAML), split="test",
                        conf=CONF, iou=0.7, max_det=300,
                        plots=True, verbose=False, workers=4)
    names = metrics.names
    box = metrics.box
    # 注意：ultralytics 逐类数组按"测试集中出现过的 GT 类"位置索引，
    # 必须用 ap_class_index 映射回真实 class id（否则错位）。
    ap_class_index = list(box.ap_class_index)
    per_class = []
    seen = set()
    for pos, cid in enumerate(ap_class_index):
        per_class.append({
            "class_id": int(cid), "class": names[int(cid)],
            "precision": float(box.p[pos]),
            "recall": float(box.r[pos]),
            "mAP50": float(box.ap50[pos]),
            "mAP50-95": float(box.ap[pos]),
        })
        seen.add(int(cid))
    for cid, cname in names.items():  # 零样本类补 None
        if int(cid) not in seen:
            per_class.append({"class_id": int(cid), "class": cname,
                              "precision": None, "recall": None,
                              "mAP50": None, "mAP50-95": None})
    return {
        "split": "test", "conf": CONF,
        "overall": {"mAP50": float(box.map50), "mAP50-95": float(box.map),
                    "mp": float(box.mp), "mr": float(box.mr)},
        "per_class": per_class,
    }


def run_diagnosis(model) -> dict:
    """自定义诊断：混淆对 + 面积分桶召回 + 按源分层。conf=0.25, IoU 匹配 0.5。"""
    splits = json.loads(SPLITS_JSON.read_text(encoding="utf-8"))
    fine_names = splits["fine_labels"]
    test_records = [r for r in splits["records"] if r["split"] == "test"]
    stem2source = {}
    for r in test_records:
        stem2source[Path(r["image"]).stem] = r["source"]

    # 累积器
    gt_tp = Counter()          # fine → TP 数
    gt_fn = Counter()          # fine → FN 数
    bucket_tp = defaultdict(Counter)   # bucket → fine → TP
    bucket_fn = defaultdict(Counter)   # bucket → fine → FN
    conf_pair = Counter()      # (gt_fine, pred_fine) → 次数（错配覆盖 FN 情形）
    fp_class = Counter()       # fine → 无任何 GT 覆盖的 FP 数
    src_tp, src_fn, src_fp = Counter(), Counter(), Counter()

    img_dir = _ROOT / "data" / "splits" / "unified-v2" / "images" / "test"
    lbl_dir = _ROOT / "data" / "splits" / "unified-v2" / "labels" / "test"
    imgs = sorted(img_dir.glob("*"))
    print(f"[diag] test 图像 {len(imgs)} 张，推理中...")

    # 注意：ultralytics 对 list 输入强制走 LoadPilAndNumpy（全量载入内存），
    # 必须传目录字符串走 LoadImagesAndVideos 流式加载。
    results = model.predict(source=str(img_dir), conf=CONF,
                            iou=0.7, max_det=300, verbose=False,
                            stream=True, imgsz=640)
    n_done = 0
    for res in results:
        n_done += 1
        if n_done % 800 == 0:
            print(f"[diag] {n_done}/{len(imgs)}")
        stem = Path(res.path).stem
        src = stem2source.get(stem, "unknown")
        # 读 GT
        txt = lbl_dir / f"{stem}.txt"
        gts = []
        if txt.exists():
            for line in txt.read_text(encoding="utf-8").splitlines():
                p = line.split()
                if len(p) >= 5:
                    gts.append((int(p[0]), float(p[1]), float(p[2]),
                                float(p[3]), float(p[4])))
        # 预测框（归一化）
        preds = []
        if res.boxes is not None and len(res.boxes):
            for b in res.boxes:
                xywhn = b.xywhn[0].tolist()
                preds.append((int(b.cls[0]), xywhn[0], xywhn[1],
                              xywhn[2], xywhn[3], float(b.conf[0])))
        # 贪心匹配（按 conf 降序）
        preds.sort(key=lambda x: -x[5])
        gt_matched = [False] * len(gts)
        for pcls, pcx, pcy, pw, ph, _conf in preds:
            best_iou, best_j = 0.0, -1
            for j, (gcls, gcx, gcy, gw, gh) in enumerate(gts):
                if gt_matched[j]:
                    continue
                v = iou_xywhn((pcx, pcy, pw, ph), (gcx, gcy, gw, gh))
                if v > best_iou:
                    best_iou, best_j = v, j
            if best_j >= 0 and best_iou >= IOU_MATCH:
                gt_matched[best_j] = True
                gcls = gts[best_j][0]
                if pcls == gcls:
                    gt_tp[fine_names[gcls]] += 1
                    src_tp[src] += 1
                else:
                    conf_pair[(fine_names[gcls], fine_names[pcls])] += 1
                    src_fp[src] += 1  # 错类预测按 FP 计入源层
            else:
                fp_class[fine_names[pcls]] += 1
                src_fp[src] += 1
        for j, matched in enumerate(gt_matched):
            gcls, gcx, gcy, gw, gh = gts[j]
            fname = fine_names[gcls]
            b = area_bucket(gw * gh)
            if matched:
                bucket_tp[b][fname] += 1
            else:
                gt_fn[fname] += 1
                bucket_fn[b][fname] += 1
                src_fn[src] += 1

    # 汇总逐类召回 + 分桶
    per_class = {}
    for fname in fine_names:
        tp, fn = gt_tp.get(fname, 0), gt_fn.get(fname, 0)
        per_class[fname] = {"tp": tp, "fn": fn,
                            "recall@0.5": tp / (tp + fn) if tp + fn else None}
    buckets = {}
    for bname, _, _ in AREA_BUCKETS:
        per_f = {}
        for fname in fine_names:
            tp = bucket_tp[bname].get(fname, 0)
            fn = bucket_fn[bname].get(fname, 0)
            if tp + fn:
                per_f[fname] = {"tp": tp, "fn": fn,
                                "recall@0.5": round(tp / (tp + fn), 4)}
        total_tp = sum(bucket_tp[bname].values())
        total_fn = sum(bucket_fn[bname].values())
        buckets[bname] = {"per_class": per_f,
                          "overall_recall@0.5": round(total_tp / (total_tp + total_fn), 4)
                          if total_tp + total_fn else None}
    sources = {}
    for s in sorted(set(stem2source.values())):
        tp, fn, fp = src_tp.get(s, 0), src_fn.get(s, 0), src_fp.get(s, 0)
        sources[s] = {"tp": tp, "fn": fn, "fp": fp,
                      "recall@0.5": round(tp / (tp + fn), 4) if tp + fn else None,
                      "precision@0.5": round(tp / (tp + fp), 4) if tp + fp else None}
    conf_pairs = [{"gt": k[0], "pred": k[1], "count": v}
                  for k, v in conf_pair.most_common(20)]
    return {"conf": CONF, "iou_match": IOU_MATCH,
            "per_class_recall": per_class,
            "area_bucket_recall": buckets,
            "by_source": sources,
            "confusion_pairs": conf_pairs,
            "fp_unmatched": dict(fp_class.most_common())}


def run_external(model) -> dict:
    """eval-v1/v2 定性泛化测试：无 GT，按场景统计检出率与主导检出类。"""
    out = {}
    for d in EVAL_DIRS:
        imgs = sorted((d / "images").glob("*.jpg"))
        scene_stats = defaultdict(lambda: {"n": 0, "detected": 0,
                                           "det_counts": Counter(),
                                           "top_conf": []})
        for img in imgs:
            scene = img.stem.rsplit("_", 1)[0]  # debris_01 → debris
            res = model.predict(source=str(img), conf=CONF, iou=0.7,
                                max_det=300, verbose=False, imgsz=640)[0]
            boxes = res.boxes if res.boxes is not None else None
            n_det = len(boxes) if boxes is not None else 0
            st = scene_stats[scene]
            st["n"] += 1
            if n_det > 0:
                st["detected"] += 1
            st["det_counts"][n_det] += 1
            if n_det:
                st["top_conf"].append(round(float(boxes.conf.max()), 3))
        out[d.name] = {
            scene: {"images": st["n"], "detected": st["detected"],
                    "detect_rate": round(st["detected"] / st["n"], 4),
                    "mean_max_conf": round(sum(st["top_conf"]) / len(st["top_conf"]), 4)
                    if st["top_conf"] else None,
                    "det_count_hist": {str(k): v for k, v in sorted(st["det_counts"].items())}}
            for scene, st in scene_stats.items()}
    return out


def write_report(std, diag, ext):
    lines = [f"# {MODEL_TITLE} 阶段性测试报告（stage-1）", "",
             f"- 模型：{WEIGHTS}",
             "- 数据：unified-v2 test 冻结划分（4733 图）+ eval-v1/v2（43 图，无 GT）",
             f"- 阈值：conf={CONF}，诊断匹配 IoU={IOU_MATCH}", "",
             "## 1. 标准逐类指标（test）", "",
             "| 类别 | P | R | mAP50 | mAP50-95 |",
             "|---|---|---|---|---|"]
    def f3(v):
        return f"{v:.3f}" if isinstance(v, (int, float)) else "—"
    for c in sorted(std["per_class"], key=lambda x: -(x["mAP50"] or 0)):
        lines.append(f"| {c['class']} | {f3(c['precision'])} | {f3(c['recall'])} "
                     f"| {f3(c['mAP50'])} | {f3(c['mAP50-95'])} |")
    o = std["overall"]
    lines += ["", f"**总体**：mAP50={o['mAP50']:.4f}，mAP50-95={o['mAP50-95']:.4f}，"
                  f"P={o['mp']:.4f}，R={o['mr']:.4f}", "",
              "## 2. 面积分桶召回（IoU=0.5）", "",
              "| 桶 | 总召回 | 说明 |", "|---|---|---|"]
    for bname, _, _ in AREA_BUCKETS:
        r = diag["area_bucket_recall"][bname]["overall_recall@0.5"]
        lines.append(f"| {bname} | {r} | |")
    lines += ["", "## 3. 混淆对 Top（GT→Pred 错配）", "",
              "| GT | Pred | 次数 |", "|---|---|---|"]
    for cp in diag["confusion_pairs"][:12]:
        lines.append(f"| {cp['gt']} | {cp['pred']} | {cp['count']} |")
    lines += ["", "## 4. 按数据源分层（IoU=0.5）", "",
              "| 源 | R | P |", "|---|---|---|"]
    for s, v in diag["by_source"].items():
        lines.append(f"| {s} | {v['recall@0.5']} | {v['precision@0.5']} |")
    lines += ["", "## 5. 外部泛化（eval-v1/v2，无 GT，检出率）", "",
              "| 集 | 场景 | 图数 | 检出率 | 平均最高置信度 |", "|---|---|---|---|---|"]
    for dname, scenes in ext.items():
        for scene, v in scenes.items():
            lines.append(f"| {dname} | {scene} | {v['images']} "
                         f"| {v['detect_rate']} | {v['mean_max_conf']} |")
    (OUT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    only = None
    if "--only" in _args:
        only = _args[_args.index("--only") + 1]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(WEIGHTS))
    print(f"[eval] 模型 {WEIGHTS} → {OUT_DIR}")

    std = diag = ext = None
    if only in (None, "std"):
        print("[1/3] 标准评估（test 4733 图）...")
        std = run_standard_val(model)
        (OUT_DIR / "metrics_test.json").write_text(
            json.dumps(std, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] 总体 mAP50={std['overall']['mAP50']:.4f} mAP50-95={std['overall']['mAP50-95']:.4f}")
    if only in (None, "diag"):
        print("[2/3] 自定义诊断（混淆对/面积分桶/按源分层）...")
        diag = run_diagnosis(model)
        (OUT_DIR / "diag_test.json").write_text(
            json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
    if only in (None, "ext"):
        print("[3/3] 外部泛化 eval-v1/v2...")
        ext = run_external(model)
        (OUT_DIR / "eval_external.json").write_text(
            json.dumps(ext, ensure_ascii=False, indent=2), encoding="utf-8")

    # 三个 json 齐全后（本次或沿用已有）写报告
    if std is None and (OUT_DIR / "metrics_test.json").exists():
        std = json.loads((OUT_DIR / "metrics_test.json").read_text(encoding="utf-8"))
    if diag is None and (OUT_DIR / "diag_test.json").exists():
        diag = json.loads((OUT_DIR / "diag_test.json").read_text(encoding="utf-8"))
    if ext is None and (OUT_DIR / "eval_external.json").exists():
        ext = json.loads((OUT_DIR / "eval_external.json").read_text(encoding="utf-8"))
    if std and diag and ext:
        write_report(std, diag, ext)
        print(f"[done] 产出: {OUT_DIR}")


if __name__ == "__main__":
    main()

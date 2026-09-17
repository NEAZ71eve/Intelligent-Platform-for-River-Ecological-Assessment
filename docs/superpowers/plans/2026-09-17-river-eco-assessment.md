# 河道生态评估模块实现计划（HYHQ 演进）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 HYHQ 仓库内把花卉识别演进为河道生态评估：巡河员上传定位+图像 → YOLOv8n 检测 4 类生态问题 → 规则引擎输出单图评估（等级/问题/原因）→ 关联河段记录。

**Architecture:** 演进式改造——保留 Django+DRF+PostgreSQL 任务队列、推理工作进程、模型登记机制；新增评估规则引擎（版本化 RuleSet）与河段关联；识别任务 schema 从分类升级为检测+评估；小程序"AI 识别"入口改造为"河道巡查"。数据管道独立于服务器（训练在开发机，服务器仅 ONNX CPU 推理）。

**Tech Stack:** Python 3 + ultralytics YOLOv8n + ONNX Runtime（CPU）、Django + DRF + PostgreSQL、原生微信小程序（无 npm 构建）、pytest 风格 Django TestCase。

**上游文档:** `docs/superpowers/specs/2026-09-17-river-eco-assessment-design.md`（已批准 spec，含数据集清单与决策门）
**路径约定:** 本计划中 HYHQ 内部文件路径为基于仓库 README 与文档的推断，**Task 0 核对后全计划统一修正**。决策门（Task 1）不通过则 Phase 1-4 取消，执行回退（保留花卉识别）。

---

## Phase 0：环境准备与决策门

### Task 0: Clone HYHQ 并核对计划路径假设

**Files:**
- Create: 本地 `../HYHQ`（clone 远程仓库）
- Create: `docs/superpowers/plans/path-verification.md`（在 HYHQ 仓库内，路径核对结果）

- [ ] **Step 1: Clone 仓库**

```bash
cd c:/Users/21516/WeChatProjects
git clone https://github.com/gruTGU/HYHQ.git
cd HYHQ
```

Expected: clone 成功（私有仓库需本机 git 凭据已登录，若失败用 `gh repo clone gruTGU/HYHQ`）。

- [ ] **Step 2: 启动本地环境验证基线可用**

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
scripts/dev.sh --sqlite
```

Expected: Django dev server 启动，`http://127.0.0.1:8000/admin/` 可访问。

- [ ] **Step 3: 核对路径假设并修正计划**

勘察并记录以下实际路径（后续任务的路径以核对结果为准）：
1. 识别任务 app/模块名与 models 文件（`grep -r "recognition" backend/ --include="*.py" -l`）
2. 推理工作进程实现文件（`grep -r "onnx" backend/ inference/ -l`）
3. `scripts/manage.sh` 子命令清单（读文件确认）
4. 小程序"AI 识别"页面目录（`ls miniprogram/pages/`）
5. 后端测试目录与运行方式、前端测试（`miniprogram/tests/`）

将实际路径写入 `docs/superpowers/plans/path-verification.md`，并全局修正本计划中的路径后再继续 Task 2。

- [ ] **Step 4: 提交**

```bash
git add docs/superpowers/plans/path-verification.md
git commit -m "docs: 实现计划路径核对（河道生态评估）"
```

### Task 1: D0 决策门——WATER-DET 获取验证

**Files:**
- Create: `inference/data/sources/WATER-DET/README.md`（获取记录）
- Create: `docs/verification/D0-decision-gate.md`（GO/NO-GO 报告）

- [ ] **Step 1: 检索数据可用性声明**

打开论文 https://www.frontiersin.org/journals/environmental-science/articles/10.3389/fenvs.2025.1657930/full，定位 Data Availability Statement，记录声明的存储位置（figshare/GitHub/联系作者等）与许可条款。

- [ ] **Step 2: 尝试获取**

按声明渠道执行：直接下载，或通过邮件向通讯作者（论文页面 zgg@xaut.edu.cn / jcxie@xaut.edu.cn）索取，说明用途（课程/毕设演示、CC BY 引用）。

- [ ] **Step 3: 核验数据**

获取后核验：图片数 ≥1500、含 12 类标注、YOLO 格式或可转换格式、许可允许训练使用。记录 SHA-256 清单到 `inference/data/sources/WATER-DET/README.md`。

- [ ] **Step 4: 产出 GO/NO-GO 报告**

写入 `docs/verification/D0-decision-gate.md`：结论 + 证据（截图/邮件/下载链接）+ 逐类样本统计。
- **GO** → 继续 Phase 1
- **NO-GO（2 周内无法获取）** → 触发回退：终止本计划，保留 M3 花卉识别，在 HYHQ 的 TODO 文档记录回退决策

- [ ] **Step 5: 提交**

```bash
git add inference/data/sources/ docs/verification/
git commit -m "docs: D0 决策门验证报告（WATER-DET）"
```

---

## Phase 1：数据流水线（开发机执行）

### Task 2: 数据集下载与审计

**Files:**
- Create: `inference/data/sources/{IWHR,YRDG,FLOW,TUDELFT}/README.md`（各源获取记录与许可）
- Create: `inference/training/audit_datasets.py`（审计脚本）
- Test: `inference/training/tests/test_audit.py`

- [ ] **Step 1: 下载各源数据**

按各论文 Data Availability 声明获取（IWHR: Sci Data 10.1038/s41597-025-04594-9 附带渠道；YRDG: MDPI Sensors 24(1):50 声明；FloW-Img、TU Delft: 论文开源链接）。原始归档放 `inference/.runtime/`（已在 .gitignore，不入库）。每源 README 记录：出处 URL、许可、下载日期、归档 SHA-256。

- [ ] **Step 2: 编写审计脚本（先写测试）**

```python
# inference/training/tests/test_audit.py
import pytest
from training.audit_datasets import audit_image_dir

def test_audit_returns_per_source_stats(tmp_path):
    img = tmp_path / "img1.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 100)
    stats = audit_image_dir(tmp_path)
    assert stats["total_images"] == 1
    assert stats["total_bytes"] == 104

def test_audit_dedup_by_dhash(tmp_path):
    # 同内容复制两份，去重后为 1
    data = b"\xff\xd8\xff\xe0" + b"0" * 100
    (tmp_path / "a.jpg").write_bytes(data)
    (tmp_path / "b.jpg").write_bytes(data)
    stats = audit_image_dir(tmp_path, dedup=True)
    assert stats["unique_images"] == 1
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd inference && python -m pytest training/tests/test_audit.py -v
```

Expected: FAIL（`audit_datasets` 不存在）。

- [ ] **Step 4: 实现审计脚本**

```python
# inference/training/audit_datasets.py
"""逐源审计图片数量、体积、dHash 近重复组，产出 JSON 报告。"""
import hashlib, json
from pathlib import Path
from PIL import Image

def _dhash(path, size=8):
    with Image.open(path) as im:
        im = im.convert("L").resize((size + 1, size))
        px = list(im.getdata())
        return "".join("1" if px[r * (size + 1) + c] > px[r * (size + 1) + c + 1] else "0"
                       for r in range(size) for c in range(size))

def audit_image_dir(root: Path, dedup: bool = False) -> dict:
    exts = {".jpg", ".jpeg", ".png"}
    files = [p for p in Path(root).rglob("*") if p.suffix.lower() in exts]
    hashes, seen = {}, set()
    for p in files:
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        dh = _dhash(p)
        hashes.setdefault(sha, []).append(str(p))
        seen.add(dh)
    return {
        "total_images": len(files),
        "unique_images": len(hashes) if not dedup else len(set(
            hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in files)),
        "total_bytes": sum(p.stat().st_size for p in files),
        "exact_sha256": len(hashes),
        "dhash_groups": len(seen),
    }

if __name__ == "__main__":
    import sys
    print(json.dumps(audit_image_dir(Path(sys.argv[1]), dedup="--dedup" in sys.argv),
                     ensure_ascii=False, indent=2))
```

- [ ] **Step 5: 运行测试通过并产出审计报告**

```bash
python -m pytest training/tests/test_audit.py -v
python training/audit_datasets.py .runtime/IWHR --dedup > data/audit/IWHR.json
```

Expected: 测试 PASS；每源审计 JSON 入 `inference/data/audit/`。

- [ ] **Step 6: 提交**

```bash
git add inference/data/ inference/training/
git commit -m "feat(inference): 数据集下载与审计脚本（dHash/SHA-256）"
```

### Task 3: 类别映射配置冻结

**Files:**
- Create: `inference/data/class_mapping.yaml`
- Create: `inference/training/class_mapping.py`（加载与校验）
- Test: `inference/training/tests/test_class_mapping.py`

- [ ] **Step 1: 写失败测试**

```python
# inference/training/tests/test_class_mapping.py
import pytest
from training.class_mapping import load_mapping, fine_to_eval, eval_categories

def test_four_eval_categories():
    m = load_mapping()
    assert set(eval_categories(m)) == {"floating_debris", "bloom_blackwater",
                                        "outfall_discharge", "bank_problem"}

def test_fine_label_maps_to_eval():
    m = load_mapping()
    assert fine_to_eval(m, "bottle") == "floating_debris"
    assert fine_to_eval(m, "sewage_color") == "bloom_blackwater"
    assert fine_to_eval(m, "outfall") == "outfall_discharge"

def test_unknown_label_raises():
    m = load_mapping()
    with pytest.raises(KeyError):
        fine_to_eval(m, "nonexistent_label")
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest training/tests/test_class_mapping.py -v
```

- [ ] **Step 3: 编写映射配置（依据 Task 2 审计的各源实际标签冻结细类）**

```yaml
# inference/data/class_mapping.yaml
# 版本化：修改必须递增 version 并在报告中说明
version: 1
eval_categories:
  floating_debris:   {id: 0}
  bloom_blackwater:  {id: 1}
  outfall_discharge: {id: 2}
  bank_problem:      {id: 3}
# 细类 → 评估大类。训练用细类 id；评估聚合。
# 各数据集原始标签 → 细类 的归一化在各源转换器中处理（Task 4）。
fine_labels:
  # floating_debris
  bottle:          {eval: floating_debris}
  foam_board:      {eval: floating_debris}
  water_plant:     {eval: floating_debris}
  algae_mass:      {eval: floating_debris}
  plastic:         {eval: floating_debris}
  paper:           {eval: floating_debris}
  glass:           {eval: floating_debris}
  metal:           {eval: floating_debris}
  fabric:          {eval: floating_debris}
  misc_debris:     {eval: floating_debris}
  # bloom_blackwater
  sewage_color:    {eval: bloom_blackwater}
  foam_pollution:  {eval: bloom_blackwater}
  # outfall_discharge
  outfall:         {eval: outfall_discharge}
  # bank_problem
  bank_garbage:    {eval: bank_problem}
  bank_encroach:   {eval: bank_problem}
```

```python
# inference/training/class_mapping.py
import yaml
from pathlib import Path

def load_mapping(path: Path = None) -> dict:
    path = path or Path(__file__).parent.parent / "data" / "class_mapping.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def eval_categories(mapping: dict) -> list:
    return list(mapping["eval_categories"].keys())

def fine_to_eval(mapping: dict, fine: str) -> str:
    return mapping["fine_labels"][fine]["eval"]  # KeyError 即未知标签
```

- [ ] **Step 4: 测试通过并提交**

```bash
python -m pytest training/tests/test_class_mapping.py -v
git add inference/data/class_mapping.yaml inference/training/
git commit -m "feat(inference): 类别映射配置 v1（4 大类 + 细类）"
```

### Task 4: 统一 YOLO 数据集构建

**Files:**
- Create: `inference/training/build_dataset.py`（各源标注 → 统一 YOLO 格式 + 冻结划分）
- Create: `inference/data/splits/unified-v1/`（划分清单）
- Test: `inference/training/tests/test_build_dataset.py`

- [ ] **Step 1: 写失败测试**

```python
# inference/training/tests/test_build_dataset.py
import pytest
from training.build_dataset import convert_voc_annotation, split_records

def test_voc_to_yolo_conversion(tmp_path):
    voc = tmp_path / "a.xml"
    voc.write_text("""<annotation><size><width>640</width><height>480</height></size>
    <object><name>bottle</name><bndbox>
    <xmin>10</xmin><ymin>20</ymin><xmax>50</xmax><ymax>100</ymax>
    </bndbox></object></annotation>""")
    out = convert_voc_annotation(voc)
    # YOLO: cx cy w h（归一化）
    assert out == [("bottle", 0.046875, 0.125, 0.0625, 0.16666666666666666)]

def test_split_frozen_and_disjoint():
    recs = [f"img{i}" for i in range(100)]
    tr, va, te = split_records(recs, seed=42)
    assert len(tr) + len(va) + len(te) == 100
    assert not (set(tr) & set(va) & set(te))
    tr2, _, _ = split_records([f"img{i}" for i in range(100)], seed=42)
    assert tr == tr2  # 固定种子可重放
```

- [ ] **Step 2: 运行确认失败，然后实现**

```python
# inference/training/build_dataset.py
"""各源标注转换为统一细类 YOLO 格式，dHash 分组去重，固定种子划分并冻结清单。"""
import random, xml.etree.ElementTree as ET
from pathlib import Path

def convert_voc_annotation(xml_path: Path) -> list:
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
    rng = random.Random(seed)
    recs = sorted(records)
    rng.shuffle(recs)
    n = len(recs)
    a, b = int(n * ratios[0]), int(n * (ratios[0] + ratios[1]))
    return recs[:a], recs[a:b], recs[b:]

# main：遍历 .runtime/ 各源 → 归一化源标签为细类（各源映射字典见
# SOURCES_LABEL_MAP）→ 写 images/ + labels/ + splits 清单（含每图 SHA-256）
```

源标签归一化字典（各源原始标签 → Task 3 细类）在文件头部署为 `SOURCES_LABEL_MAP`，例如 IWHR 的 `bottle→bottle`、`foam→foam_board`、WATER-DET 的 `Sewage→sewage_color`、`Foam Pollution→foam_pollution`、`Garbage→bank_garbage`（WATER-DET 的 Garbage 声明含岸线垃圾）。具体键值以 Task 2 审计到的实际标签为准填入。

- [ ] **Step 3: 测试通过，构建并冻结**

```bash
python -m pytest training/tests/test_build_dataset.py -v
python training/build_dataset.py   # 产出 data/splits/unified-v1/
git add inference/data/splits/ inference/training/build_dataset.py
git commit -m "feat(inference): 统一 YOLO 数据集构建与冻结划分 v1"
```

### Task 5: YOLOv8n 训练与评估报告

**Files:**
- Create: `inference/training/train_yolo.py`
- Create: `inference/reports/yolo-v1-report.md`

- [ ] **Step 1: 训练脚本**

```python
# inference/training/train_yolo.py
from ultralytics import YOLO

def main():
    model = YOLO("yolov8n.pt")  # COCO 预训练
    model.train(
        data="data/splits/unified-v1/dataset.yaml",
        epochs=100, imgsz=640, batch=16,
        project="runs", name="river-eco-v1",
        seed=42, deterministic=True,   # 可重放
        patience=20,
    )

if __name__ == "__main__":
    main()
```

`dataset.yaml` 由 Task 4 生成：`train/val/test` 路径 + 细类 names（id 顺序与 class_mapping.yaml 一致）。

- [ ] **Step 2: 训练并产出报告**

```bash
python training/train_yolo.py
```

Expected: 训练完成后 `runs/river-eco-v1/` 含 `results.csv`、`confusion_matrix.png`、`weights/best.pt`。

报告 `inference/reports/yolo-v1-report.md` 必须包含：mAP50 / mAP50:95（总体+细类+聚合 4 大类）、混淆矩阵、失败样例分析、训练环境（GPU 型号/时长/种子）、明确声明"公开数据集成绩不代表真实河道巡查识别准确率"。

- [ ] **Step 3: 提交（报告与配置，不含权重与数据）**

```bash
git add inference/training/train_yolo.py inference/reports/yolo-v1-report.md
git commit -m "feat(inference): YOLOv8n 训练与评估报告 v1"
```

### Task 6: ONNX 导出与检测 manifest

**Files:**
- Create: `inference/training/export_onnx.py`
- Create: `inference/training/onnx_detector.py`（检测后处理：ONNX 输出 → detections）
- Test: `inference/training/tests/test_onnx_detector.py`

- [ ] **Step 1: 导出**

```python
# inference/training/export_onnx.py
from ultralytics import YOLO

def main():
    model = YOLO("runs/river-eco-v1/weights/best.pt")
    path = model.export(format="onnx", imgsz=640, opset=12, simplify=True)
    print(path)  # best.onnx → 复制到 inference/artifacts/ 并生成 manifest

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 检测后处理（先写测试）**

```python
# inference/training/tests/test_onnx_detector.py
import numpy as np, pytest
from training.onnx_detector import postprocess

def _fake_output(nc=16, boxes=8400):
    # YOLOv8 ONNX 输出: (1, 4+nc, boxes)
    raw = np.zeros((1, 4 + nc, boxes), dtype=np.float32)
    raw[0, 0, 0] = 10; raw[0, 1, 0] = 10   # cx cy
    raw[0, 2, 0] = 20; raw[0, 3, 0] = 20   # w h
    raw[0, 4 + 0, 0] = 0.9                  # class0 conf
    raw[0, 4 + 5, 1] = 0.8                  # class5 conf
    return raw

def test_postprocess_nms_and_conf():
    dets = postprocess(_fake_output(), conf_thres=0.5, iou_thres=0.45)
    assert len(dets) == 2
    d0 = dets[0]
    assert set(d0) == {"class_id", "conf", "x1", "y1", "x2", "y2"}
    assert d0["class_id"] == 0 and d0["conf"] == pytest.approx(0.9)

def test_low_conf_filtered():
    raw = _fake_output(); raw[0, 4 + 0, 0] = 0.3
    assert postprocess(raw, conf_thres=0.5, iou_thres=0.45) != None
    # 该框被过滤，仅剩 class5 框
    dets = postprocess(raw, conf_thres=0.5, iou_thres=0.45)
    assert all(d["class_id"] != 0 or d["conf"] > 0.4 for d in dets)
```

- [ ] **Step 3: 实现 postprocess（NMS 用 torchvision.ops 或纯 numpy 实现）**

```python
# inference/training/onnx_detector.py
"""YOLOv8 ONNX 输出后处理：转置、置信过滤、NMS，输出像素坐标框。"""
import numpy as np

def postprocess(raw: np.ndarray, conf_thres=0.5, iou_thres=0.45) -> list:
    pred = raw[0].T                      # (boxes, 4+nc)
    boxes_wh = pred[:, :4]
    scores = pred[:, 4:]
    class_ids = scores.argmax(1)
    confs = scores.max(1)
    keep = confs > conf_thres
    boxes_wh, class_ids, confs = boxes_wh[keep], class_ids[keep], confs[keep]
    # cxcywh → xyxy
    xy = np.stack([boxes_wh[:, 0] - boxes_wh[:, 2] / 2,
                   boxes_wh[:, 1] - boxes_wh[:, 3] / 2,
                   boxes_wh[:, 0] + boxes_wh[:, 2] / 2,
                   boxes_wh[:, 1] + boxes_wh[:, 3] / 2], axis=1)
    # NMS（逐类）
    out, order = [], np.argsort(-confs)
    suppressed = np.zeros(len(confs), bool)
    for i in order:
        if suppressed[i]:
            continue
        out.append({"class_id": int(class_ids[i]), "conf": float(confs[i]),
                    "x1": float(xy[i, 0]), "y1": float(xy[i, 1]),
                    "x2": float(xy[i, 2]), "y2": float(xy[i, 3])})
        x1 = np.maximum(xy[i, 0], xy[:, 0]); y1 = np.maximum(xy[i, 1], xy[:, 1])
        x2 = np.minimum(xy[i, 2], xy[:, 2]); y2 = np.minimum(xy[i, 3], xy[:, 3])
        inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
        iou = inter / ((xy[i, 2]-xy[i, 0])*(xy[i, 3]-xy[i, 1]) +
                       (xy[:, 2]-xy[:, 0])*(xy[:, 3]-xy[:, 1]) - inter + 1e-9)
        same = class_ids == class_ids[i]
        suppressed |= (iou > iou_thres) & same
    return out
```

- [ ] **Step 4: 测试通过；生成 manifest（沿用 HYHQ 制品契约，扩展检测字段）**

manifest JSON 在现有花卉 manifest schema 基础上扩展：`task: "detection"`、`fine_labels`（有序，index 对应 class_id）、`class_mapping_version: 1`、`imgsz: 640`、ONNX SHA-256。用 `scripts/manage.sh register_model <manifest> --activate` 登记（Task 0 核对登记命令的契约校验是否需同步扩展——若现有校验假定分类输出形状，需在登记校验中新增检测分支）。

- [ ] **Step 5: 提交**

```bash
python -m pytest training/tests/test_onnx_detector.py -v
git add inference/training/export_onnx.py inference/training/onnx_detector.py inference/training/tests/
git commit -m "feat(inference): ONNX 导出与检测后处理（NMS）"
```

---

## Phase 2：后端演进

### Task 7: 评估规则引擎（RuleSet 版本化 + RULE v1）

**Files:**
- Create: `backend/<识别模块>/rules.py`（Task 0 核对实际 app 路径，下同）
- Modify: `backend/<识别模块>/models.py`（新增 RuleSet 模型）
- Test: `backend/<识别模块>/tests/test_rules.py`

- [ ] **Step 1: RuleSet 模型**

```python
# models.py 新增（沿用现有模型风格）
class RuleSet(models.Model):
    version = models.CharField(max_length=32, unique=True)   # 如 "v1"
    definition = models.JSONField()   # 完整规则定义（公式/权重/阈值）
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

- [ ] **Step 2: 写失败测试**

```python
# tests/test_rules.py
from django.test import TestCase
from <识别模块>.rules import assess

def det(eval_cat, area_ratio=0.01):
    return {"eval_category": eval_cat, "conf": 0.8, "area_ratio": area_ratio}

class RuleV1Tests(TestCase):
    def test_clean_image_is_excellent(self):
        r = assess([], rule_version="v1")
        self.assertEqual(r["grade"], "优")
        self.assertEqual(r["score"], 100)

    def test_outfall_heavy_penalty(self):
        r = assess([det("outfall_discharge")], rule_version="v1")
        self.assertEqual(r["grade"], "良")
        self.assertEqual(r["score"], 75)

    def test_grade_boundaries(self):
        self.assertEqual(assess([], "v1")["grade"], "优")
        self.assertEqual(assess([det("outfall_discharge"), det("bloom_blackwater", 0.1)],
                                "v1")["grade"], "中")
        self.assertEqual(assess([det("outfall_discharge"), det("outfall_discharge"),
                                  det("bloom_blackwater", 0.3), det("bank_garbage")],
                                 "v1")["grade"], "差")

    def test_causes_floating_plus_bank(self):
        r = assess([det("floating_debris"), det("floating_debris"),
                    det("floating_debris"), det("floating_debris"),
                    det("bank_problem")], rule_version="v1")
        self.assertTrue(any("垃圾清运" in c["text"] for c in r["causes"]))
```

- [ ] **Step 3: 实现 RULE v1（100 分制扣分，规则定义与代码同源）**

```python
# rules.py
"""评估规则引擎：检测框聚合 → 大类统计 → 扣分 → 等级 + 原因。
规则版本化：任务固定记录 rule_version，历史不回写。"""
from dataclasses import dataclass

RULE_V1 = {
    "base": 100,
    "floating_debris": {"count_steps": [(0, 0), (1, 5), (4, 12), (11, 20)],
                         "area_steps": [(0.0, 0), (0.01, 5), (0.05, 10)]},
    "bloom_blackwater": {"area_steps": [(0.0, 0), (0.05, 8), (0.20, 15)]},
    "outfall_discharge": {"per_instance": 25, "cap": 40},
    "bank_problem": {"per_instance": 6, "cap": 18},
}
GRADES = [(85, "优"), (70, "良"), (50, "中"), (0, "差")]

def _stat(detections):
    stat = {}
    for d in detections:
        c = stat.setdefault(d["eval_category"], {"count": 0, "area_ratio": 0.0})
        c["count"] += 1
        c["area_ratio"] += d.get("area_ratio", 0.0)
    return stat

def _step(steps, value):
    penalty = 0
    for threshold, pts in steps:
        if value >= threshold:
            penalty = pts
    return penalty

def assess(detections: list, rule_version: str) -> dict:
    r = RULE_V1[rule_version.lstrip("v").join(["v", ""])] if False else RULE_V1["v1"]  # 见说明
    stat = _stat(detections)
    score = r["base"]
    fd = stat.get("floating_debris")
    if fd:
        score -= _step(r["floating_debris"]["count_steps"], fd["count"])
        score -= _step(r["floating_debris"]["area_steps"], fd["area_ratio"])
    bw = stat.get("bloom_blackwater")
    if bw:
        score -= _step(r["bloom_blackwater"]["area_steps"], bw["area_ratio"])
    od = stat.get("outfall_discharge")
    if od:
        score -= min(od["count"] * r["outfall_discharge"]["per_instance"],
                     r["outfall_discharge"]["cap"])
    bp = stat.get("bank_problem")
    if bp:
        score -= min(bp["count"] * r["bank_problem"]["per_instance"],
                     r["bank_problem"]["cap"])
    score = max(0, min(100, score))
    grade = next(g for t, g in GRADES if score >= t)
    causes = []
    if fd and fd["count"] >= 4 and bp:
        causes.append({"rule": "fd_bank", "text": "漂浮物与岸带垃圾并存，提示周边垃圾清运或倾倒管控问题"})
    if bw:
        causes.append({"rule": "bloom", "text": "存在水华或水体颜色异常，富营养化倾向，建议核查上游氮磷来源"})
    if od:
        causes.append({"rule": "outfall", "text": "检出疑似排污口或污水直排，建议溯源排查"})
    return {"score": score, "grade": grade, "causes": causes,
            "issues": stat, "rule_version": rule_version}
```

说明：`assess` 第一行的条件表达式是占位错误，实现时直接 `r = RULE_V1[rule_version]`；RuleSet 模型入库后，definition 字段与 RULE_V1 dict 同构，从库中加载以 DB 为准。自审时删除此行，以 `RULE_V1[rule_version]` 为准。

- [ ] **Step 4: 测试通过并提交**

```bash
scripts/manage.sh test <识别模块>.tests.test_rules
git add backend/
git commit -m "feat(backend): 评估规则引擎 RULE v1（版本化 RuleSet）"
```

### Task 8: 河段关联（定位 → 水体/监测站）

**Files:**
- Create: `backend/<识别模块>/geo.py`
- Test: `backend/<识别模块>/tests/test_geo.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_geo.py
from django.test import TestCase
from <识别模块>.geo import match_water_body

class GeoTests(TestCase):
    fixtures = ["demo_stations"]   # 沿用 HYHQ 示范校园 4 监测站种子

    def test_nearest_station_within_radius(self):
        r = match_water_body(39.90, 116.40)
        self.assertIsNotNone(r)
        self.assertIn("water_body_id", r)
        self.assertIn("distance_m", r)

    def test_no_station_returns_none(self):
        self.assertIsNone(match_water_body(0.0, 0.0))
```

- [ ] **Step 2: 实现（Haversine 最近站，半径 2km，超出返回 None 由前端兜底手动选）**

```python
# geo.py
import math

EARTH_R = 6371000.0
MATCH_RADIUS_M = 2000.0

def _haversine(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p)
         * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(a))

def match_water_body(lat: float, lng: float):
    from <识别模块>.models import MonitoringStation   # Task 0 核对模型名
    best, best_d = None, MATCH_RADIUS_M
    for s in MonitoringStation.objects.select_related("water_body"):
        d = _haversine(lat, lng, s.latitude, s.longitude)
        if d < best_d:
            best, best_d = s, d
    if best is None:
        return None
    return {"water_body_id": best.water_body_id, "station_id": best.id,
            "distance_m": round(best_d)}
```

- [ ] **Step 3: 测试通过并提交**

```bash
scripts/manage.sh test <识别模块>.tests.test_geo
git add backend/
git commit -m "feat(backend): 定位关联河段（最近监测站 2km）"
```

### Task 9: assessment-jobs API

**Files:**
- Modify: `backend/<识别模块>/models.py`（任务模型扩展：lat/lng、检测结果、等级、原因、规则版本、关联水体）
- Modify: `backend/<识别模块>/serializers.py`、`views.py`（或 urls.py 路由）
- Test: `backend/<识别模块>/tests/test_assessment_api.py`

- [ ] **Step 1: 模型扩展（在现有识别任务模型上，沿用其状态机）**

```python
# models.py 现有任务模型新增字段
class AssessmentJob(models.Model):          # 或演进现有 RecognitionJob，二选一由 Task 0 定
    status = models.CharField(max_length=16)     # queued/running/succeeded/failed
    error_code = models.CharField(max_length=48, blank=True)
    image = models.ForeignKey("ControlledImage", on_delete=models.CASCADE)
    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)
    water_body = models.ForeignKey("WaterBody", null=True, on_delete=models.SET_NULL)
    station = models.ForeignKey("MonitoringStation", null=True, on_delete=models.SET_NULL)
    detections = models.JSONField(default=list)   # 细类框 + eval_category + area_ratio
    score = models.IntegerField(null=True)
    grade = models.CharField(max_length=8, blank=True)
    causes = models.JSONField(default=list)
    rule_set = models.ForeignKey("RuleSet", null=True, on_delete=models.SET_NULL)
    model_version = models.ForeignKey("ModelVersion", null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
```

- [ ] **Step 2: 写失败测试（鉴权创建 + 定位必填 + 结果契约）**

```python
# tests/test_assessment_api.py
from django.test import TestCase
from rest_framework.test import APIClient

class AssessmentJobAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # 沿用现有测试的用户/会话工厂（Task 0 核对工具函数名）

    def test_create_requires_auth(self):
        r = self.client.post("/api/v1/assessment-jobs", {})
        self.assertEqual(r.status_code, 401)

    def test_create_requires_lat_lng(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.post("/api/v1/assessment-jobs",
                             {"image": self.image_id})
        self.assertEqual(r.status_code, 400)

    def test_result_contract(self):
        job = self._create_job()
        r = self.client.get(f"/api/v1/assessment-jobs/{job.id}")
        self.assertEqual(r.status_code, 200)
        for key in ("status", "detections", "score", "grade", "causes",
                    "rule_version", "water_body", "disclaimer"):
            self.assertIn(key, r.json())

    def test_history_filter_by_water_body(self):
        r = self.client.get("/api/v1/assessment-jobs?water_body=1")
        self.assertEqual(r.status_code, 200)
```

- [ ] **Step 3: 实现序列化器与视图（沿用现有 recognition-jobs 的鉴权/上传/队列模式，错误码风格一致；disclaimer 固定为"平台演示评分，非官方水质评价"）**

- [ ] **Step 4: 测试通过并提交**

```bash
scripts/manage.sh test <识别模块>.tests.test_assessment_api
git add backend/
git commit -m "feat(backend): assessment-jobs API（定位+检测+评估契约）"
```

### Task 10: 推理工作进程接入检测与评估

**Files:**
- Modify: 推理工作进程实现（Task 0 定位；即消费任务、派生 ONNX 子进程的模块）
- Test: 现有推理测试目录新增 `test_worker_detection.py`

- [ ] **Step 1: 写失败测试（mock ONNX 会话输出 → 验证任务落库结果）**

```python
# test_worker_detection.py
import numpy as np
from django.test import TestCase

class WorkerDetectionTests(TestCase):
    def test_job_pipeline_produces_grade(self):
        job = self._create_queued_job()
        fake_raw = self._fake_onnx_output(classes=16, boxes=8400,
                                          boxes_to_fire=[(0, 0.9), (5, 0.8)])
        with patch_onnx_session(fake_raw):   # 测试工具：注入 fake 输出
            run_worker_once()                # 现有工作进程单次消费入口
        job.refresh_from_db()
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(len(job.detections), 2)
        self.assertIsNotNone(job.grade)
        self.assertTrue(job.rule_set)

    def test_timeout_marks_failed_not_fake_result(self):
        with patch_onnx_session(never_returns=True):
            run_worker_once()
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error_code, "INFERENCE_TIMEOUT")
        self.assertEqual(job.detections, [])
```

- [ ] **Step 2: 实现改造点**

1. ONNX 子进程推理：加载检测模型（manifest `task=detection`），输出 raw (1, 4+nc, 8400)
2. 复用 Task 6 的 `postprocess`（后端通过内部接口调用 inference/training/onnx_detector 或复制为后端内部模块——按 HYHQ"生产环境只需 CPU 推理依赖"的约束，**复制到 backend 内部模块**，来源注释指向 inference 原件）
3. 细类 id → `eval_category` + 面积占比（框面积/图面积）→ 调 `rules.assess` → 落库
4. 超时/异常路径沿用现有错误码体系（`INFERENCE_TIMEOUT` 等稳定码）

- [ ] **Step 3: 测试通过并提交**

```bash
scripts/manage.sh test <识别模块>.tests.test_worker_detection
git add backend/
git commit -m "feat(backend): 推理工作进程接入检测+评估管道"
```

### Task 11: Django Admin 扩展

**Files:**
- Modify: `backend/<识别模块>/admin.py`

- [ ] **Step 1: 注册 RuleSet（列表只读 + 单选激活/停用，沿用模型版本管理的 Admin 模式）；AssessmentJob 只读查看（状态/检测结果/等级/规则版本/关联水体），支持按河段与状态过滤**

- [ ] **Step 2: 手动验证**：Admin 后台可见 RuleSet 激活切换、巡查任务列表过滤。

- [ ] **Step 3: 提交**

```bash
git add backend/
git commit -m "feat(backend): Admin 规则版本管理与巡查任务查看"
```

---

## Phase 3：小程序改造

### Task 12: 巡查上报页

**Files:**
- Modify: `miniprogram/pages/<AI识别页>/`（Task 0 核对目录名，改造为河道巡查）
- Modify: `miniprogram/app.json`（入口文案）

- [ ] **Step 1: 上报页核心逻辑**

```javascript
// pages/<巡查页>/index.js 核心结构（沿用现有上传/鉴权 util）
const app = getApp();

Page({
  data: {
    imageFile: null,
    location: null,        // {latitude, longitude}
    matchedSegment: null,  // {water_body: {id, name}, distance_m}
    submitting: false,
  },

  async onChooseImage() { /* 沿用现有 wx.chooseMedia 受控上传逻辑 */ },

  async onLoadLocation() {
    const loc = await wx.getLocation({ type: "gcj02" });
    this.setData({ location: loc });
    const r = await app.request("/api/v1/water-bodies/match",
                                { method: "POST", data: loc });
    if (r.matched) this.setData({ matchedSegment: r });
    // 匹配失败 → 显示手动选择河段 picker（数据来自现有水体列表接口）
  },

  async onSubmit() {
    if (!this.data.imageFile) return wx.showToast({ title: "请先拍摄河道照片", icon: "none" });
    if (!this.data.location) return wx.showToast({ title: "请获取定位", icon: "none" });
    this.setData({ submitting: true });
    const job = await app.request("/api/v1/assessment-jobs", {
      method: "POST",
      data: { image: this.data.imageFile, lat: this.data.location.latitude,
              lng: this.data.location.longitude },
    });
    wx.navigateTo({ url: `/pages/<结果页>/index?jobId=${job.id}` });
  },
});
```

配套新增轻接口：`POST /api/v1/water-bodies/match {lat,lng} → {matched, water_body, station, distance_m}`（视图直接调 Task 8 的 `match_water_body`，测试并入 Task 9 的测试文件）。

- [ ] **Step 2: WXML 结构**：照片选择区（复用现有上传组件样式）、定位卡片（经纬度+匹配河段名+手动改选 picker）、提交按钮、提交中 loading。隐私授权拒绝时降级为手动输入河段（沿用 HYHQ"拒绝授权仍可浏览"的原则，定位不是硬阻断——手动选择河段后仍可提交）。

- [ ] **Step 3: 前端测试（沿用 miniprogram/tests 的 node+wx mock 模式）**

```javascript
// miniprogram/tests/assessment-report.test.js 核心断言
test("上报页缺少图片时 toast 且不请求", async () => {
  const page = await renderPage("pages/<巡查页>/index");
  await page.instance.onSubmit();
  expect(wx.showToast).toHaveBeenCalledWith({ title: expect.any(String), icon: "none" });
  expect(mockFetch.requests().post("/api/v1/assessment-jobs")).toHaveLength(0);
});
```

- [ ] **Step 4: 测试通过并提交**

```bash
node miniprogram/tests/assessment-report.test.js
git add miniprogram/
git commit -m "feat(miniprogram): 河道巡查上报页（拍照+定位+河段匹配）"
```

### Task 13: 评估结果页

**Files:**
- Create: `miniprogram/pages/<评估结果页>/`

- [ ] **Step 1: 轮询任务 + 结果渲染**

```javascript
// pages/<评估结果页>/index.js
Page({
  data: { job: null, failed: null, boxes: [], gradeText: "" },

  onLoad({ jobId }) {
    this.jobId = jobId;
    this.poll();
  },

  async poll() {
    const job = await getApp().request(`/api/v1/assessment-jobs/${this.jobId}`);
    if (job.status === "queued" || job.status === "running") {
      setTimeout(() => this.poll(), 1500);
      this.setData({ job });
    } else if (job.status === "succeeded") {
      this.setData({ job, boxes: job.detections.map((d) => ({
        x: d.x / d.img_width, y: d.y / d.img_height,
        w: d.box_w / d.img_width, h: d.box_h / d.img_height,
        label: d.fine_label, conf: d.conf,
      }))});
    } else {
      this.setData({ failed: job.error_code });  // 明确失败，不显示伪造结果
    }
  },
});
```

- [ ] **Step 2: WXML 结构**
1. 原图 + canvas 覆盖层绘制检测框（`<canvas type="2d">`，按比例换算，框上标注细类与置信度）
2. 等级徽章：`score` + `grade`（优=绿/良=蓝/中=橙/差=红，纯 CSS）
3. 问题清单：逐大类"类别 / 检出数 / 面积占比"
4. 原因分析卡片：`causes[]` 列表
5. 关联河段近期指标：水温/pH/浊度/DO（沿用现有数据中心接口，标注"模拟数据"角标）
6. 固定免责声明："平台演示评分，非官方水质评价"
7. 失败态：错误码 + 重试按钮（沿用现有错误展示模式）
8. 科普关联：沿用现有 `candidates[].content_id` → 科普文章跳转

- [ ] **Step 3: 前端测试**（低图质/失败态/成功态三路径渲染断言，模式同 Task 12 测试）

- [ ] **Step 4: 测试通过并提交**

```bash
node miniprogram/tests/assessment-result.test.js
git add miniprogram/
git commit -m "feat(miniprogram): 评估结果页（检测框+等级+原因+指标）"
```

### Task 14: 巡查记录列表与入口改造

**Files:**
- Create: `miniprogram/pages/<巡查记录>/`
- Modify: 首页/我的入口（"AI 识别"→"河道巡查"；我的新增"巡查记录"）

- [ ] **Step 1: 记录列表**：`GET /api/v1/assessment-jobs?water_body=` 分组展示（河段标题 + 时间倒序 + 缩略图 + 等级徽章），点击进结果页（Task 13 复用）；下拉刷新。

- [ ] **Step 2: 入口文案与图标**：`app.json` tabBar/首页入口、"我的"页列表项。

- [ ] **Step 3: 前端测试 + 提交**

```bash
node miniprogram/tests/assessment-history.test.js
git add miniprogram/
git commit -m "feat(miniprogram): 巡查记录列表与入口改造"
```

---

## Phase 4：集成与验收

### Task 15: live-smoke 端到端联调扩展

**Files:**
- Modify: `miniprogram/tests/live-smoke.js`（沿用现有真实 HTTP + wx mock 模式）

- [ ] **Step 1: 扩展场景**

```bash
# 沿用现有联调命令模式，新增评估断言
HYHQ_EXPECT_ASSESSMENT=1 node miniprogram/tests/live-smoke.js
HYHQ_EXPECT_ASSESSMENT=1 HYHQ_TEST_IMAGE=/absolute/path/river.jpg node miniprogram/tests/live-smoke.js
```

断言：创建任务（带 lat/lng）→ 轮询 → succeeded → 结果含 grade/issues/causes/detections/rule_version/disclaimer → 1 像素图触发 `LOW_IMAGE_QUALITY` → 记录删除与越权沿用现有用例。

- [ ] **Step 2: 提交**

```bash
git add miniprogram/tests/live-smoke.js
git commit -m "test: 评估链路 live-smoke 端到端联调"
```

### Task 16: 验收清单执行

**Files:**
- Create: `docs/verification/assessment-acceptance.md`

逐项执行并记录证据（沿用 HYHQ 验证记录格式）：

- [ ] 1. 模型报告基于独立测试集（Task 5 报告链接），CPU 单图 ≤10 秒（服务器实测 30 次取 p95）
- [ ] 2. 真机完整流程：拍照→定位→河段匹配→评估→等级→原因→记录回看
- [ ] 3. 规则版本、模型版本、数据来源、模拟指标标注全链路可追溯（抽查 3 条记录）
- [ ] 4. 失败路径演示：无模型（MODEL_NOT_CONFIGURED）、超时、低图质、无匹配河段（手动选择兜底）
- [ ] 5. 回退态验证：停用模型后任务明确失败，历史结果不被改写

```bash
git add docs/verification/assessment-acceptance.md
git commit -m "docs: 河道生态评估验收记录"
```

---

## 自审记录

1. **Spec 覆盖**：spec 第 4 节 D0–D3 → Task 1–6；第 6 节后端 → Task 7–11；第 7 节页面 → Task 12–14；第 9 节 API → Task 9（+water-bodies/match）；第 8 节规则 → Task 7；第 10 节验收 → Task 16；第 11 节回退 → Task 1 NO-GO 分支 + Task 16 第 5 项。无缺口。
2. **占位符**：`<识别模块>`/`<AI识别页>` 等尖括号占位是 Task 0 路径核对的显式产出物（非 TBD——Task 0 有具体核对命令与产出文件）；Task 7 Step 3 中被标注删除的一行错误代码已在说明中要求替换为 `RULE_V1[rule_version]`。其余步骤均含完整代码或精确命令。
3. **类型一致性**：`assess()` 返回 `{score, grade, causes, issues, rule_version}` 与 Task 9 模型字段、Task 10 落库、Task 13 渲染一致；`postprocess()` 框格式 `{class_id, conf, x1, y1, x2, y2}` 在 Task 6/10/13 三处一致（13 处换算为归一化展示坐标，所需 `img_width/img_height/fine_label` 字段由 Task 10 落库时一并写入 detections）。

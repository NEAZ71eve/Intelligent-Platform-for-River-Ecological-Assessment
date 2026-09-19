# 多源数据预处理报告 v2（unified-v2）

> 日期：2026-09-19 · 状态：✅ 完成 · 脚本：`inference/training/prepare_unified_v2.py`（本次新增）

## 1. 目的

方向 B 训练前预处理：把已落地 D 盘的多源异构数据集统一清洗为 **15 细类 YOLO 格式**，去重、固定划分（seed 42），供重训多类别检测模型（替换仅 misc_debris 单类的 v1 数据集）。

## 2. 输入源（5 源，实测格式）

| 源 | 原始格式 | 原始类别 | → 细类映射 | 图数 | 去重后 |
|---|---|---|---|---|---|
| IWHR | VOC XML | floater | → misc_debris | 3000 | 3000 |
| CANSURF | YOLO 1 类 | debris（水面金属罐）| → metal | 7171 | 7062（109 重复）|
| iSOOD | YOLO 1 类 | cid0（排污口）| → outfall | 10481 | 10433（48 重复）|
| TACO | COCO 60 类 | 按语义映射表 | 8 细类 | 1500 目标 / 400 已下载 | 399（1 截断）|
| YRDG | YOLO 7 类 | plastic/paper/glass/metal/fabricfiber/nature/others | plastic/paper/glass/metal/fabric/water_plant/misc_debris | 10233 | 10202（31 重复）|

- TACO 映射表见脚本 `TACO_CAT_MAP`（60 类 → 8 细类），Flickr 下载完成 1500/1500 后重跑脚本即全量纳入。
- 去重键：SHA256(前16) + dHash，全源跨源去重（共剔除 80 张近似重复）。

## 3. 输出

**位置**：`D:\WeChatProjects\HYHQ\inference\data\splits\unified-v2\`（18.43 GB，不入 git）
- `images/{train,val,test}/` + `labels/{train,val,test}/`（YOLO 格式，文件名 `{源}_{原名}.jpg/.txt`）
- `dataset.yaml`（15 细类 names，id 与 class_mapping fine_labels 顺序一致）
- `splits.json`（seed=42，70/15/15 划分清单 + 逐图记录，可审计可重放）

## 4. 结果统计

**划分**：train 21,767 / val 4,664 / test 4,665（31096 图，86,369 框）

**细类框分布**：

| 细类 | 框数 | 来源 |
|---|---:|---|
| metal | 31,698 | CANSURF 主力 + YRDG + TACO |
| misc_debris | 24,845 | IWHR 主力 + YRDG others |
| outfall | 11,718 | iSOOD |
| plastic | 8,498 | YRDG + TACO |
| paper | 3,906 | YRDG + TACO |
| fabric | 2,783 | YRDG fabricfiber + TACO |
| water_plant | 1,955 | YRDG nature（近似映射）|
| glass | 838 | YRDG + TACO |
| bottle | 78 | TACO |
| foam_board | 50 | TACO |
| **algae_mass** | **0** | 硬缺口，需自采 ≥500 |
| **sewage_color** | **0** | 硬缺口，需自采 ≥300 |
| **foam_pollution** | **0** | 硬缺口，需自采 ≥300 |
| **bank_garbage** | **0** | 硬缺口，需自采 ≥500 |
| **bank_encroach** | **0** | 硬缺口，需自采 ≥500 |

## 5. 关键结论

1. **覆盖提升**：v1 仅 1 细类（misc_debris 23,692 框）→ v2 覆盖 10/15 细类（86,369 框），outfall 从 0 到 11,718 框（iSOOD 落地）。
2. **剩余 5 个零样本细类**：algae_mass / sewage_color / foam_pollution / bank_garbage / bank_encroach——全部属于方向 B 门禁的自采硬缺口，无公开数据，必须启动自采。
3. **TACO 半量**：目前仅 399 图（Flickr 下载中），且 TACO 为陆地场景，存在 domain gap，仅作类别补充；下载完成后重跑脚本自动纳入。
4. **water_plant 为近似映射**（YRDG nature 类含水草/树枝等自然漂浮物），验收时需抽样人工复核。

## 6. 环境/脚本说明

- 运行：`cd D:\WeChatProjects\HYHQ\inference && python training\prepare_unified_v2.py`（anaconda base，Python 3.12 + numpy 1.26.4）
- 幂等：脚本启动时整体重建输出目录（清理上次残留），可安全重跑。
- 修复记录：v2 脚本修 2 个 bug——① YRDG split_inner 布局扫描；② TACO batch_N 跨目录同名覆盖（改用相对路径命名）。

## 7. 下一步（训练前剩余项）

1. TACO 下载完成（1500）后重跑脚本 → 预计 +1100 图
2. 启动 5 个硬缺口细类自采（规范见 docs/硬缺口自采规范.md）
3. 训练入口：`ultralytics` YOLOv8n 载入 `data/splits/unified-v2/dataset.yaml` 训练（待用户确认是否立即开训）

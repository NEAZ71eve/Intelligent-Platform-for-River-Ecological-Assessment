# 河道生态评估 · 训练 Wiki

> 维护：HYHQ inference 模块 · 最后更新：2026-09-20
> 配套文档：`reports/training-direction-v1.md`（方向判定）、`reports/data-preprocessing-v2.md`（数据预处理 v2）、miniprogram-2 `CODE_WIKI.md`（全站状态）

## 1. 目标与现状

**目标（方向 B）**：河道生态评估——四个评估大类检测 + 图像级四档生态等级（good/fair/poor/critical）多任务模型。

**当前状态**：

| 环节 | 状态 |
|---|---|
| 数据 | unified-v2 就绪：31,096 图 / 86,369 框 / **10/15 细类**（18.43 GB，D 盘）|
| 5 个零样本细类 | 硬缺口，自采规范已就绪（docs/硬缺口自采规范.md），未启动 |
| 多类模型训练 | **未开始**（unified-v2 尚未用于训练；下述命令为就绪入口）|
| 基线（v1 单类）| test mAP50=0.884 / mAP50-95=0.630 / P=0.878 / R=0.790（仅 misc_debris）|

> 判定结论（training-direction-v1.md）：v1 的问题不是模型结构/epoch，而是监督信号缺失（14 类零样本 + 无生态等级标签）。**unified-v2 落地后才有资格谈多类训练。**

## 2. 类别体系（冻结 v1）

来源：`data/class_mapping.yaml`（修改必须递增 version 并在报告中说明）

**4 评估大类**（规则引擎评分/等级映射用）：

| id | 大类 | 中文 |
|---|---|---|
| 0 | floating_debris | 水面漂浮物 |
| 1 | bloom_blackwater | 水华/黑臭水体 |
| 2 | outfall_discharge | 排污口/污水直排 |
| 3 | bank_problem | 岸带环境问题 |

**15 训练细类**（保留判别信息，评估时聚合到大类）：

| id | 细类 | 大类 | unified-v2 框数 |
|---|---|---|---|
| 0 | bottle | floating_debris | 78 |
| 1 | foam_board | floating_debris | 50 |
| 2 | water_plant | floating_debris | 1,955 |
| 3 | algae_mass | floating_debris | **0（自采 ≥500）** |
| 4 | plastic | floating_debris | 8,498 |
| 5 | paper | floating_debris | 3,906 |
| 6 | glass | floating_debris | 838 |
| 7 | metal | floating_debris | 31,698 |
| 8 | fabric | floating_debris | 2,783 |
| 9 | misc_debris | floating_debris | 24,845 |
| 10 | sewage_color | bloom_blackwater | **0（自采 ≥300）** |
| 11 | foam_pollution | bloom_blackwater | **0（自采 ≥300）** |
| 12 | outfall | outfall_discharge | 11,718 |
| 13 | bank_garbage | bank_problem | **0（自采 ≥500）** |
| 14 | bank_encroach | bank_problem | **0（自采 ≥500）** |

## 3. 数据（unified-v2）

**位置**：`D:\WeChatProjects\HYHQ\inference\data\splits\unified-v2\`（不入 git，18.43 GB）
- `images/{train,val,test}/` + `labels/{train,val,test}/`（YOLO 格式）
- `dataset.yaml`（15 细类 names，id 与 class_mapping 一致）
- `splits.json`（seed=42，70/15/15，逐图记录可审计）

**来源构成**（5 源，去重后）：

| 源 | 图数 | 贡献类别 | 备注 |
|---|---:|---|---|
| iSOOD | 10,433 | outfall | 排污口黄金数据集 |
| YRDG | 10,202 | plastic/paper/glass/metal/fabric/water_plant/misc_debris | 自带划分，已并入随机划分 |
| CANSURF | 7,062 | metal | 水面金属罐专项 |
| IWHR | 3,000 | misc_debris | 内部交付（唯一不可重得，需备份）|
| TACO | 399 | 8 细类补充 | Flickr 下载中（1500 目标），完成重跑纳入 |

**划分**：train 21,767 / val 4,664 / test 4,665（70/15/15，seed 42）

**注意事项**：
- `water_plant` 来自 YRDG `nature` 类的近似映射（含水草/树枝），验收需抽样复核。
- TACO 为陆地随手拍场景，与水面存在 domain gap，仅作类别补充。
- 自采数据到位后须**按地点分组划分**（门禁 1/5），不得随机拆相邻帧。

## 4. 数据准备（重跑）

```powershell
cd D:\WeChatProjects\HYHQ\inference
C:\Users\21516\anaconda3\python.exe training\prepare_unified_v2.py
```

- 幂等：启动时整体重建输出目录（清理旧划分残留），可安全重跑。
- TACO 下载完成（1500/1500）后重跑即全量纳入。
- 新增自采数据：在脚本中登记新源适配器（映射到 15 细类）后重跑。

## 5. 训练

**环境**：anaconda base（`C:\Users\21516\anaconda3\python.exe`，Python 3.12.7，ultralytics 8.4.154，numpy 1.26.4）

**入口**：`training/train_yolo.py` ⚠️ **当前仍指向 unified-v1，需更新为 unified-v2 后再用**；或直接命令行训练：

```powershell
cd D:\WeChatProjects\HYHQ\inference
C:\Users\21516\anaconda3\python.exe -m ultralytics.engine.train YOLO(
    data='D:/WeChatProjects/HYHQ/inference/data/splits/unified-v2/dataset.yaml',
    model='yolov8n.pt', epochs=100, imgsz=640, batch=16,
    project='D:/WeChatProjects/HYHQ/inference/runs', name='river-eco-v2',
    seed=42, deterministic=True, patience=20, cache='disk', workers=0)
```

**超参基线（沿 v1 经验）**：epochs=100（v1 约 70 轮平台化）、imgsz=640、batch=16、patience=20、seed=42 deterministic（可重放）、workers=0（Windows DataLoader 易崩，主进程加载）。

**多类注意**：15 细类样本极不均衡（78 ~ 31,698 框），需关注 per-class AP，必要时按细类加权采样或分阶段训练；5 个零样本类在补数据前**不得计入指标**（缺类即缺监督信号）。

## 6. 评估

- **模型选择只看验证集**，test 一次性评估后不再反向调参（v1 教训：selection_v1.json 记 test_metrics_seen=false）。
- 检测指标：per-class AP + mAP50/mAP50-95（不只看总体 mAP）；生态等级任务另报 macro-F1、balanced accuracy、每级召回率、四档混淆矩阵。
- 落盘：`runs/river-eco-v2*/`（results.csv、weights/best.pt）；test 评估结果保留在 runs/detect/*。
- 泛化：按地点/时间/设备/天气分层报告（门禁 5）。

## 7. ONNX 导出与登记

```powershell
cd D:\WeChatProjects\HYHQ\inference
C:\Users\21516\anaconda3\python.exe training\export_onnx.py
```

- 产出：`artifacts/river-eco-yolov8n-v1.onnx` + `manifest.json`（imgsz 640 / letterbox / pad 114 / threshold 0.5，labels=15 细类含 eval_category 聚合）。
- ⚠️ 脚本 `find_best_run()` 匹配 `river-eco-v1*`，多类 v2 训练后需同步更新匹配前缀与 artifact 版本号。
- 后端登记流程见 HYHQ `scripts/manage.sh register_model`（校验 SHA-256/标签/图结构，拒绝外部权重）。

## 8. 实验门禁（方向 B 验收，来自 training-direction-v1.md）

1. **数据门禁**：四个大类各有正例，train/val/test 均有样本；测试集包含未见地点。
2. **标签门禁**：每张图有生态等级；双人标注并记录一致性（≥85%），冲突样本复核。
3. **基线门禁**：先跑规则评分基线和单任务分类基线，再比较多任务模型。
4. **指标门禁**：macro-F1、balanced accuracy、每级召回率、四档混淆矩阵；检测报告 per-class AP。
5. **泛化门禁**：按地点、时间、设备和天气分层报告，不满足不能声称可用于真实河道。

## 9. 已知问题与待办

| 项 | 状态 |
|---|---|
| train_yolo.py 指向 unified-v1 | 待更新为 v2 |
| TACO 下载 402/1500 | 独立进程续传中（PID 见下载日志），完成后重跑预处理 |
| 5 硬缺口细类（algae_mass/sewage_color/foam_pollution/bank_garbage/bank_encroach）| 自采规范就绪未启动 |
| water_plant 近似映射 | 需抽样人工复核 |
| IWHR 备份 | 唯一不可重得，网盘/双盘备份方案未拍板 |
| 数据集申请邮件（WATER-DET/Space-hehu/FloW-Img）| 模板就绪，待发送 |
| inference/README.md 花卉遗留 | 待替换为本 wiki 摘要 |

## 10. 速查命令

```powershell
# 环境
C:\Users\21516\anaconda3\python.exe --version   # Python 3.12.7（评估/训练统一用此环境）

# 数据重跑
cd D:\WeChatProjects\HYHQ\inference && C:\Users\21516\anaconda3\python.exe training\prepare_unified_v2.py

# 训练（v2 就绪后）
cd D:\WeChatProjects\HYHQ\inference && C:\Users\21516\anaconda3\python.exe training\train_yolo.py

# ONNX 导出
cd D:\WeChatProjects\HYHQ\inference && C:\Users\21516\anaconda3\python.exe training\export_onnx.py
```

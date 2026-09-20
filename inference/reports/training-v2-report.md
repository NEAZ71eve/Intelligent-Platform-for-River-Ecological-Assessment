# 河道生态评估训练报告 v2（unified-v2 多类）

> 日期：2026-09-20 · 状态：✅ 完成（80/100 epochs 早停）· 模型：YOLOv8n（river-eco-v2-2）

## 1. 训练配置

| 项 | 值 |
|---|---|
| 数据 | unified-v2（31,099 图 / 86,372 框 / 15 细类，其中 10 类有样本）|
| 划分 | train 21,769 / val 4,665 / test 4,665（seed 42）|
| 模型 | YOLOv8n（COCO 预训练）|
| 超参 | epochs=100（80 早停）/ imgsz=640 / batch=16 / patience=20 / seed=42 |
| 环境 | anaconda base（Python 3.12.7 + ultralytics 8.4.154 + RTX 4060 8GB）|
| 耗时 | 约 3.4 小时（144s/epoch；workers=4 修复 Windows DataLoader 崩溃）|
| 运行 | `runs/river-eco-v2-2/` |

## 2. 指标（val 选型 / test 一次性）

| 指标 | val（4,665 图） | test（4,663 图） |
|---|---:|---:|
| mAP50 | 0.758 | **0.767** |
| mAP50-95 | 0.477 | **0.491** |
| Precision | 0.895 | 0.902 |
| Recall | 0.684 | 0.707 |

**test per-class mAP50**：

| 细类 | 实例 | mAP50 | 细类 | 实例 | mAP50 |
|---|---:|---:|---|---:|---:|
| metal | 4,370 | **0.967** | misc_debris | 3,740 | 0.880 |
| fabric | 441 | 0.953 | outfall | 1,777 | 0.881 |
| plastic | 1,219 | 0.903 | glass | 111 | 0.822 |
| paper | 638 | 0.891 | bottle | 8 | 0.365 |
| water_plant | 311 | 0.888 | foam_board | 10 | 0.114 |

- 5 个零样本细类（algae_mass/sewage_color/foam_pollution/bank_garbage/bank_encroach）无实例、不参与指标。
- test 与 val 接近（甚至略高），同源随机划分，无过拟合迹象；**test 一次性评估后未调参**（门禁 4）。

## 3. 独立集泛化抽检（eval-v1，16 图 / 4 场景，网络独立来源）

最终 best.pt 重跑结果（conf=0.25）：

| 场景 | 检出 | 说明 |
|---|---|---|
| 排污口 | **4/4 全部命中**（outfall×5）| iSOOD 数据直接转化为泛化能力 |
| 漂浮物 | 3/4 检出（misc_debris/paper）| 较第 7 epoch 版（1/4）明显改善 |
| 水华 | 2/4 检出零星漂浮物 | 藻类零样本，符合预期 |
| 岸带 | 2/4 检出垃圾（misc_debris/plastic）| 误检修复：bank_01 旧版 3×outfall → 现无错误 outfall |

对比第 7 epoch 版：**误检显著减少**（排污口误判消失）、漂浮物检出率提升、排污口保持稳定。

## 4. ONNX 导出（部署链）

- 产物：`artifacts/river-eco-yolov8n-v2.onnx`（12.3MB）+ `-v2.manifest.json`
- manifest：15 细类（含 eval_category 聚合）、imgsz 640、threshold 0.5、sha256 已记录
- 后端登记：待 `scripts/manage.sh register_model` 校验启用（需 validate_config 检测分支）

## 5. 门禁状态（方向 B）

| 门禁 | 状态 |
|---|---|
| ① 数据：4 大类各有正例 | ❌ 水华黑臭/岸带 2 大类仍零样本（5 细类需自采）|
| ② 标签：生态等级 | ❌ 未标注 |
| ③ 基线：规则/单任务基线 | ❌ 未跑 |
| ④ 指标：per-class AP | ✅ 已按 per-class 报告 |
| ⑤ 泛化：分层报告 | ⚠️ eval-v1 独立集已抽检，地点/时间分层待自采数据 |

**结论**：多类检测器（10/15 细类）达到可用水平，但方向 B 的完整生态评估仍卡在**数据门禁**——水华黑臭与岸带两类必须自采补齐后才具备训练条件。

## 6. 复现

```powershell
cd D:\WeChatProjects\HYHQ\inference
C:\Users\21516\anaconda3\python.exe training\train_yolo.py          # 训练（重跑生成 river-eco-v2-2/3...）
C:\Users\21516\anaconda3\python.exe training\export_onnx.py         # ONNX 导出
# test 评估：
C:\Users\21516\anaconda3\python.exe -c "from ultralytics import YOLO; YOLO(r'runs\river-eco-v2-2\weights\best.pt').val(data=r'data\splits\unified-v2\dataset.yaml', split='test', project='runs', name='val-v2-test')"
```

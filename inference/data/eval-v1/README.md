# eval-v1 独立测试图片集

> 创建：2026-09-20 · 用途：**独立来源泛化测试**（unified-v2 test split 与训练同源，此集补足"未见来源"维度）
> 图片本体：`D:\HYHQ_data\eval-v1\images\`（16 张，**有版权不入 git**，仅清单入库）
> 来源清单：`sources.csv`（每图来源 URL + 标题）

## 构成

| 场景（评估大类） | 图片 | 说明 |
|---|---|---|
| floating_debris | debris_01~04 | 水面塑料/袋/泡沫/垃圾带（含三峡水库新闻实拍）|
| outfall_discharge | outfall_01~04 | 排水管道/闸口/污水直排实拍 |
| bloom_blackwater | bloom_01~04 | 滇池/巢湖蓝藻水华等实拍 |
| bank_problem | bank_01~04 | 河岸垃圾堆放/岸滩污染 |

全部为独立网络来源（新闻/图库实拍），与 IWHR/CANSURF/iSOOD/YRDG/TACO 训练源无交集。

## 推理结果（2026-09-20，river-eco-v2-2 best.pt，约第 7 epoch）

- 输出：`inference/runs/detect/runs/eval-v1-predict/`（16 图 / 21 框）
- 检出：outfall 7（4 张排污口图**全部命中**）、misc_debris 8、metal 5、fabric 1
- 漏检：debris_01/03/04（漂浮物小目标）、bloom_01、bank_02/03（水华/岸带为零样本类，符合预期）
- 误检：bank_01 → 3×outfall（岸带排水设施/轮胎误判为排污口）

## 结论与用途

1. **pipeline 可用**：独立图片 → CPU 推理 → 可视化全链路跑通。
2. **印证数据缺口**：outfall 有 11,718 框训练样本 → 4/4 命中；水华/岸带零样本 → 基本无法检出；漂浮物部分检出（模型仅 7 epochs，最终版待重跑）。
3. **误检案例**（bank_01 outfall）为后续阈值/规则引擎调优提供真实反例。
4. 训练完成后用最终 best.pt 重跑本集，作为泛化抽检报告（门禁 5 的证据之一）。

## 复现

```powershell
cd D:\WeChatProjects\HYHQ\inference
C:\Users\21516\anaconda3\python.exe -c "from ultralytics import YOLO; m=YOLO(r'runs\river-eco-v2-2\weights\best.pt'); m.predict(source=r'D:\HYHQ_data\eval-v1\images', conf=0.25, device='cpu', project='runs', name='eval-v1-predict', save=True)"
```

# eval-v2 独立测试图片集（扩充版）

> 创建：2026-09-21 · 用途：**独立来源泛化抽检**（eval-v1 的扩充，27 张全新图）
> 图片本体：`D:\HYHQ_data\eval-v2\images\`（**有版权不入 git**，仅清单入库）
> 来源清单：`sources.csv`（每图来源 URL + 标题）

## 构成（27 图，与 eval-v1 无重复）

| 场景 | 图数 | 说明 |
|---|---|---|
| floating_debris | debris_05~09（5）| 航拍垃圾带、黑色水面垃圾、岸边堆积 |
| bloom_blackwater | bloom_05~12（8）| **黑臭水体重点补充**：广东黑河/青岛排污口/黄岩公路河/深圳茅洲河/重庆永川等新闻实拍 |
| outfall_discharge | outfall_05~12（8）| 锈蚀管道/航拍直排/污水大管道 |
| bank_problem | bank_05~10（6）| 河岸垃圾堆积/建筑垃圾/滩涂垃圾 |

## 推理结果（2026-09-21，river-eco-v2-2 最终 best.pt，conf=0.25）

- 输出：`inference/runs/detect/runs/eval-v2-predict/`（27 图 / 30 框）
- 检出：**outfall 20**、plastic 6、misc_debris 4

| 场景 | 检出情况 |
|---|---|
| 排污口 | **8/8 全部命中**（outfall×9，延续 eval-v1 的 100%）|
| 黑臭 | 5/8 检出 outfall（黑臭场景普遍伴随排水口；藻类/黑臭本体零样本无法检出）|
| 漂浮物 | 3/5 检出（plastic×4 / misc_debris / outfall）|
| 岸带 | 4/6 检出垃圾类（plastic / misc_debris）；**2 张误检 outfall**（bank_05/bank_10）|

## 结论

1. **outfall 泛化极强**：eval-v1 + eval-v2 合计 16/16 排污口图全部命中，iSOOD 数据价值充分验证。
2. **黑臭场景的间接信号**：黑臭图普遍含排水口/管道，模型检出 outfall 可作为辅助线索，但**直接的黑臭/藻类检测仍需自采数据**（零样本类）。
3. **岸带误检模式确认**：bank_05/bank_10 将岸带物体误判为 outfall——与 eval-v1 的 bank_01 同型，是规则引擎调优的真实反例集。
4. 两轮独立集合计 43 张（eval-v1 16 + eval-v2 27），作为最终泛化抽检证据（门禁 5 的一部分）。

## 复现

```powershell
cd D:\WeChatProjects\HYHQ\inference
C:\Users\21516\anaconda3\python.exe -c "from ultralytics import YOLO; m=YOLO(r'runs\river-eco-v2-2\weights\best.pt'); m.predict(source=r'D:\HYHQ_data\eval-v2\images', conf=0.25, device='cuda:0', project='runs', name='eval-v2-predict', save=True)"
```

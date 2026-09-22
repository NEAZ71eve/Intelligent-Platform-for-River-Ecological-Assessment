# v3 阶段性测试报告（stage-1）

- 模型：runs/river-eco-v3/weights/best.pt
- 数据：unified-v2 test 冻结划分（4733 图）+ eval-v1/v2（43 图，无 GT）
- 阈值：conf=0.25，诊断匹配 IoU=0.5

## 1. 标准逐类指标（test）

| 类别 | P | R | mAP50 | mAP50-95 |
|---|---|---|---|---|
| metal | 0.954 | 0.935 | 0.950 | 0.792 |
| fabric | 0.930 | 0.936 | 0.933 | 0.591 |
| water_plant | 0.869 | 0.866 | 0.894 | 0.407 |
| plastic | 0.879 | 0.860 | 0.851 | 0.500 |
| outfall | 0.867 | 0.826 | 0.831 | 0.648 |
| misc_debris | 0.896 | 0.784 | 0.824 | 0.598 |
| paper | 0.930 | 0.811 | 0.816 | 0.525 |
| glass | 0.874 | 0.736 | 0.738 | 0.314 |
| bottle | 0.676 | 0.250 | 0.221 | 0.178 |
| foam_board | 0.623 | 0.111 | 0.095 | 0.091 |
| algae_mass | — | — | — | — |
| sewage_color | — | — | — | — |
| foam_pollution | — | — | — | — |
| bank_garbage | — | — | — | — |
| bank_encroach | — | — | — | — |

**总体**：mAP50=0.7152，mAP50-95=0.4644，P=0.8497，R=0.7116

## 2. 面积分桶召回（IoU=0.5）

| 桶 | 总召回 | 说明 |
|---|---|---|
| tiny<0.1% | 0.7044 | |
| small0.1-1% | 0.8894 | |
| medium1-8% | 0.9501 | |
| large>8% | 0.935 | |

## 3. 混淆对 Top（GT→Pred 错配）

| GT | Pred | 次数 |
|---|---|---|
| paper | plastic | 29 |
| plastic | metal | 25 |
| metal | plastic | 23 |
| fabric | plastic | 19 |
| plastic | paper | 11 |
| plastic | fabric | 9 |
| metal | paper | 6 |
| misc_debris | metal | 5 |
| foam_board | plastic | 5 |
| glass | metal | 5 |
| bottle | plastic | 4 |
| misc_debris | plastic | 3 |

## 4. 按数据源分层（IoU=0.5）

| 源 | R | P |
|---|---|---|
| CANSURF | 0.9579 | 0.9277 |
| IWHR | 0.8426 | 0.8398 |
| TACO | 0.2381 | 0.303 |
| YRDG | 0.9503 | 0.8541 |
| iSOOD | 0.8487 | 0.7723 |

## 5. 外部泛化（eval-v1/v2，无 GT，检出率）

| 集 | 场景 | 图数 | 检出率 | 平均最高置信度 |
|---|---|---|---|---|
| eval-v1 | bank | 4 | 0.75 | 0.4027 |
| eval-v1 | bloom | 4 | 0.5 | 0.74 |
| eval-v1 | debris | 4 | 0.5 | 0.4 |
| eval-v1 | outfall | 4 | 1.0 | 0.8275 |
| eval-v2 | bank | 6 | 0.5 | 0.5813 |
| eval-v2 | bloom | 8 | 0.75 | 0.5865 |
| eval-v2 | debris | 5 | 0.4 | 0.513 |
| eval-v2 | outfall | 8 | 1.0 | 0.8439 |
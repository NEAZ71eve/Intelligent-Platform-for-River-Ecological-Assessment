# v5 阶段性测试报告（stage-1）

- 模型：runs\river-eco-v5\weights\best.pt
- 数据：unified-v2 test 冻结划分（4733 图）+ eval-v1/v2（43 图，无 GT）
- 阈值：conf=0.25，诊断匹配 IoU=0.5

## 1. 标准逐类指标（test）

| 类别 | P | R | mAP50 | mAP50-95 |
|---|---|---|---|---|
| metal | 0.965 | 0.914 | 0.931 | 0.786 |
| fabric | 0.937 | 0.920 | 0.922 | 0.581 |
| water_plant | 0.871 | 0.826 | 0.840 | 0.389 |
| plastic | 0.888 | 0.844 | 0.837 | 0.486 |
| misc_debris | 0.909 | 0.778 | 0.814 | 0.590 |
| paper | 0.940 | 0.789 | 0.808 | 0.518 |
| outfall | 0.878 | 0.802 | 0.803 | 0.630 |
| glass | 0.887 | 0.721 | 0.703 | 0.292 |
| bottle | 0.433 | 0.188 | 0.185 | 0.170 |
| foam_board | 0.472 | 0.167 | 0.121 | 0.081 |
| algae_mass | — | — | — | — |
| sewage_color | — | — | — | — |
| foam_pollution | — | — | — | — |
| bank_garbage | — | — | — | — |
| bank_encroach | — | — | — | — |

**总体**：mAP50=0.6965，mAP50-95=0.4521，P=0.8178，R=0.6948

## 2. 面积分桶召回（IoU=0.5）

| 桶 | 总召回 | 说明 |
|---|---|---|
| tiny<0.1% | 0.6685 | |
| small0.1-1% | 0.8836 | |
| medium1-8% | 0.9439 | |
| large>8% | 0.9294 | |

## 3. 混淆对 Top（GT→Pred 错配）

| GT | Pred | 次数 |
|---|---|---|
| paper | plastic | 30 |
| metal | plastic | 24 |
| fabric | plastic | 20 |
| plastic | metal | 16 |
| plastic | paper | 14 |
| misc_debris | plastic | 9 |
| plastic | fabric | 7 |
| foam_board | plastic | 5 |
| misc_debris | metal | 5 |
| bottle | plastic | 4 |
| glass | metal | 4 |
| misc_debris | glass | 3 |

## 4. 按数据源分层（IoU=0.5）

| 源 | R | P |
|---|---|---|
| CANSURF | 0.9477 | 0.9388 |
| IWHR | 0.838 | 0.8437 |
| TACO | 0.2292 | 0.3366 |
| YRDG | 0.9401 | 0.8699 |
| iSOOD | 0.8314 | 0.7865 |

## 5. 外部泛化（eval-v1/v2，无 GT，检出率）

| 集 | 场景 | 图数 | 检出率 | 平均最高置信度 |
|---|---|---|---|---|
| eval-v1 | bank | 4 | 0.75 | 0.5443 |
| eval-v1 | bloom | 4 | 0.5 | 0.5945 |
| eval-v1 | debris | 4 | 0.75 | 0.6227 |
| eval-v1 | outfall | 4 | 1.0 | 0.808 |
| eval-v2 | bank | 6 | 0.5 | 0.6133 |
| eval-v2 | bloom | 8 | 0.625 | 0.6118 |
| eval-v2 | debris | 5 | 0.6 | 0.4137 |
| eval-v2 | outfall | 8 | 1.0 | 0.7157 |
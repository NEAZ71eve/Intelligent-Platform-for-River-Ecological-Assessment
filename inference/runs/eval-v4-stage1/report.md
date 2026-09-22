# v4 阶段性测试报告（stage-1）

- 模型：runs\river-eco-v4\weights\best.pt
- 数据：unified-v2 test 冻结划分（4733 图）+ eval-v1/v2（43 图，无 GT）
- 阈值：conf=0.25，诊断匹配 IoU=0.5

## 1. 标准逐类指标（test）

| 类别 | P | R | mAP50 | mAP50-95 |
|---|---|---|---|---|
| fabric | 0.948 | 0.915 | 0.935 | 0.587 |
| metal | 0.969 | 0.913 | 0.932 | 0.785 |
| water_plant | 0.889 | 0.836 | 0.858 | 0.390 |
| plastic | 0.901 | 0.836 | 0.830 | 0.489 |
| paper | 0.953 | 0.807 | 0.812 | 0.524 |
| outfall | 0.866 | 0.792 | 0.808 | 0.629 |
| misc_debris | 0.919 | 0.763 | 0.807 | 0.588 |
| glass | 0.935 | 0.773 | 0.773 | 0.315 |
| bottle | 0.382 | 0.250 | 0.143 | 0.116 |
| foam_board | 0.277 | 0.111 | 0.079 | 0.077 |
| algae_mass | — | — | — | — |
| sewage_color | — | — | — | — |
| foam_pollution | — | — | — | — |
| bank_garbage | — | — | — | — |
| bank_encroach | — | — | — | — |

**总体**：mAP50=0.6976，mAP50-95=0.4501，P=0.8039，R=0.6997

## 2. 面积分桶召回（IoU=0.5）

| 桶 | 总召回 | 说明 |
|---|---|---|
| tiny<0.1% | 0.6606 | |
| small0.1-1% | 0.8788 | |
| medium1-8% | 0.9446 | |
| large>8% | 0.9308 | |

## 3. 混淆对 Top（GT→Pred 错配）

| GT | Pred | 次数 |
|---|---|---|
| paper | plastic | 25 |
| metal | plastic | 23 |
| fabric | plastic | 18 |
| plastic | metal | 16 |
| plastic | paper | 16 |
| plastic | fabric | 8 |
| misc_debris | plastic | 7 |
| bottle | plastic | 4 |
| misc_debris | metal | 4 |
| foam_board | plastic | 3 |
| plastic | outfall | 3 |
| paper | metal | 3 |

## 4. 按数据源分层（IoU=0.5）

| 源 | R | P |
|---|---|---|
| CANSURF | 0.9465 | 0.9385 |
| IWHR | 0.829 | 0.8545 |
| TACO | 0.2267 | 0.3269 |
| YRDG | 0.9401 | 0.8782 |
| iSOOD | 0.835 | 0.7801 |

## 5. 外部泛化（eval-v1/v2，无 GT，检出率）

| 集 | 场景 | 图数 | 检出率 | 平均最高置信度 |
|---|---|---|---|---|
| eval-v1 | bank | 4 | 0.25 | 0.6 |
| eval-v1 | bloom | 4 | 0.25 | 0.79 |
| eval-v1 | debris | 4 | 0.75 | 0.6103 |
| eval-v1 | outfall | 4 | 1.0 | 0.7817 |
| eval-v2 | bank | 6 | 0.6667 | 0.5845 |
| eval-v2 | bloom | 8 | 0.5 | 0.6813 |
| eval-v2 | debris | 5 | 0.6 | 0.5347 |
| eval-v2 | outfall | 8 | 1.0 | 0.7602 |
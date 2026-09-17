# D0 决策门验证报告：WATER-DET 数据集获取

日期：2026-09-17
结论：**有条件 NO-GO（需联系作者，数据非公开下载）**

## 验证对象

WATER-DET 数据集（1,500+ 图 / 12 类河道湖泊环境危害标注）
来源论文：Song X. et al., *Automatic recognition of environmental hazards in river and lake ecosystems using deep learning*, Front. Environ. Sci. 13 (2025). doi:10.3389/fenvs.2025.1657930
通讯作者：Ganggang Zuo (zgg@xaut.edu.cn)、Jiancang Xie (jcxie@xaut.edu.cn)
单位：西安理工大学水利工程学院

## 验证过程

### 1. 论文数据可用性声明（从 XML 版本获取原文）

> "The original contributions presented in the study are included in the article/supplementary material, further inquiries can be directed to the corresponding authors."

### 2. 解读

- 数据集**不是公开可直接下载的**（无 GitHub/figshare/Zenodo 链接）
- 论文 CC BY 许可覆盖文章内容（含图表中的代表性样本图片），但**不覆盖完整数据集**
- 完整数据集需通过邮件联系通讯作者索取

### 3. 12 类样本统计（从论文 Table 1 获取）

| # | 类别 | 样本数 | 映射到评估大类 |
|---|---|---|---|
| 1 | Algae Pollution（藻华） | 150 | bloom_blackwater |
| 2 | Oil Film Pollution（油膜） | 80 | bloom_blackwater |
| 3 | Red Pollution（红色水色） | 150 | bloom_blackwater |
| 4 | Yellow Pollution（黄色水色） | 150 | bloom_blackwater |
| 5 | Foam Pollution（泡沫污染） | 150 | bloom_blackwater |
| 6 | Sewage（黑灰水色） | 150 | bloom_blackwater |
| 7 | Garbage（水面/岸线垃圾） | 150 | bank_problem / floating_debris |
| 8 | Fish（漂浮死鱼） | 80 | floating_debris |
| 9 | Leaves（漂浮落叶） | 80 | floating_debris |
| 10 | Sewage Outlet（排污口） | 150 | outfall_discharge |
| 11 | Sand Yard（沙场） | 150 | bank_problem |
| 12 | Building（岸线建筑侵占） | 150 | bank_problem |

总计：1,590 样本（论文声明 1,500+）

### 4. 不可替代性分析

WATER-DET 是以下 3 个评估大类的**唯一来源**：
- **bloom_blackwater**：藻华/油膜/红水/黄水/泡沫/黑臭水色（6 类共 730 样本）——无其他公开数据集覆盖河道水色异常
- **outfall_discharge**：排污口（150 样本）——无其他公开数据集覆盖河道排污口检测
- **bank_problem**：岸线垃圾/沙场/岸线建筑（3 类共 450 样本，RoLID-11K 仅路侧参考）

仅有 **floating_debris** 类别有充足替代来源（IWHR + YRDG + FloW + TU Delft）。

## 结论与建议

### 结论：有条件 NO-GO

WATER-DET 无法直接下载，需联系作者。在作者确认提供数据前，判定为**有条件 NO-GO**。

### 建议行动

1. **立即邮件联系通讯作者**（zgg@xaut.edu.cn, jcxie@xaut.edu.cn），说明用途（学术/课程项目演示，CC BY 引用）
2. **设 2 周等待期**（2026-09-17 ~ 2026-10-01）
3. **等待期间不阻塞**：可先推进其他 4 个公开数据集（IWHR/YRDG/FloW/TU Delft）的下载与审计（计划 Task 2）
4. **截止日判定**：
   - 作者确认提供 → **GO**，继续完整方案 A
   - 作者未响应或拒绝 → **NO-GO**，触发回退条款：转为花卉识别方案，保留 HYHQ M3 全部能力

### 回退方案（NO-GO 时）

- 保留 M3 五类花卉识别全部能力
- 在 HYHQ TODO 文档记录回退决策与原因
- 若未来 WATER-DET 开放获取，可重新启动本计划

## 证据

- 论文页面：https://www.frontiersin.org/journals/environmental-science/articles/10.3389/fenvs.2025.1657930/full
- XML 版本（含 Data Availability Statement 原文）：https://www.frontiersin.org/journals/environmental-science/articles/10.3389/fenvs.2025.1657930/xml
- 通讯作者邮箱：zgg@xaut.edu.cn, jcxie@xaut.edu.cn

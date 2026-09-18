# HYHQ 河道生态评估 YOLO 训练数据选型 — 4 个已规划数据集可下载性核实报告

> 核实日期：2026-09-18
> 核实方式：逐个访问论文原文 HTML 页面、Zenodo 记录页、GitHub API（含 issues 区）、数据集官方页面，逐字记录 Data Availability 段落原文。
> 核实人：AI 辅助，所有结论均附 URL。

---

## 一、YRDG（Yellow River water-floating garbage Dataset）

| 项目 | 内容 |
|---|---|
| **发布机构** | 兰州理工大学 / 甘肃省水利厅河湖岸线垃圾智能识别与预警技术项目（LZJT20221013） |
| **年份** | 2024（Sensors 24(1):50，2024-01） |
| **论文标题** | APM-YOLOv7 for Small-Target Water-Floating Garbage Detection Based on Multi-Scale Feature Adaptive Weighted Fusion |
| **DOI** | [10.3390/s24010050](https://doi.org/10.3390/s24010050) |
| **论文页面** | https://www.mdpi.com/1424-8220/24/1/50 |

### 1. 下载渠道（实际验证）

论文 Data Availability Statement 原文：

> "The dataset is available at **https://github.com/jingcodejing/YRDG-dataset**, accessed on 8 October 2023. The code is available at https://github.com/jingcodejing/AAM-attention, accessed on 8 October 2023."

**实际核实 GitHub repo 状态**（通过 GitHub API 2026-09-18 查询）：

| 指标 | 值 |
|---|---|
| repo 总大小 | **16 KB** |
| stars / forks | 2 / 0 |
| open issues | 4 |
| 根目录文件 | LICENSE (35 KB)、README.md (28 字节)、`dataset/` 目录、readme2025.txt (57 字节) |
| `dataset/` 目录内容 | **仅 3 个 README 文件，无任何图片或标注文件** |

**GitHub repo 实际不存数据**。真实下载地址在百度网盘，分布在两个文件中：

- `dataset/README-1.md`（旧链接）：`https://pan.baidu.com/s/1gUtPqUkvB6T5e6NeqkPHUA?pwd=mpt6`，提取码 **mpt6**
- `readme2025.txt`（2025 年更新链接）：`https://pan.baidu.com/s/1fBgUxtJEy06EjNF_fAjOTg`，提取码 **yghb**

**Issue 区证据 — 5 个 issue 全部为"链接过期/失效求助"**：

| # | 日期 | 状态 | 标题 |
|---|---|---|---|
| 1 | 2024-07-19 | open | the dataset's share link is unavailable |
| 2 | 2024-12-13 | open | 请问能再分享一下数据集吗? |
| 3 | 2024-12-24 | open | 数据集链接已过期 |
| 4 | 2025-05-15 | open | The dataset link you shared has expired |
| 5 | 2025-10-30 | closed | Could you share this dataset again? The link you shared has expired |

> **核实结论**：作者反复更换百度网盘链接，旧链接持续过期，issue 区长期无人回复。GitHub 仅为说明文件空壳。百度网盘链接在国内可访问但需手动提取、无版本管理、极不稳定。

### 2. 许可协议

- 论文本身：MDPI Sensors 为 **CC BY 4.0**（开放获取）。
- GitHub repo 内 LICENSE 文件：**GNU GPL v3**（35 KB，完整 GPLv3 文本）。
- 注意：GPLv3 是软件 copyleft 许可证，对数据集授权不常见；实际使用数据集时建议以论文 CC BY 4.0 为准。

### 3. 规模

| 指标 | 值 |
|---|---|
| 图像总数 | **3807 张**（已核实，与论文声称一致） |
| 图像尺寸 | 640 × 640 |
| 小目标占比 | 84%（5776 个小目标框，1096 个中大型目标框） |
| 训练 / 验证 / 测试 | 3083 / 343 / 381 |

### 4. 类别清单与标注格式

**7 个类别及各类别标注框数量**（论文 Table 1）：

| # | 类名（YOLO names） | 标注框数 | 示例说明 |
|---|---|---|---|
| 1 | plastic | 1432 | 塑料袋、塑料瓶、泡沫块等 |
| 2 | paper | 909 | 牛奶盒、文件夹等 |
| 3 | glass | 651 | 玻璃罐、酒瓶等 |
| 4 | metal | 466 | 易拉罐、油桶等 |
| 5 | fabric/fiber | 991 | 绳子、布袋、破衣服 |
| 6 | natural | 1772 | 树枝、木屑、藻类、落叶等 |
| 7 | others | 651 | 不可识别物 |

**标注格式**：**YOLO txt 格式**（同时提供 VOC 类名列表）。
- repo 中 `dataset/README-2.md` 给出了标准 YOLO yaml 配置：
  - `nc: 7`
  - `names: ['plastic','paper','glass','metal','fabricfiber','nature','others']`
  - 目录结构：`./dataset/images/train|val|test`
- 同时提供了 VOC 格式的类名列表。

### 5. 覆盖 HYHQ 细类

| HYHQ 细类 | YRDG 对应 | 映射质量 |
|---|---|---|
| floating_debris > plastic | plastic | ✅ 直接对应 |
| floating_debris > paper | paper | ✅ 直接对应 |
| floating_debris > glass | glass | ✅ 直接对应 |
| floating_debris > metal | metal | ✅ 直接对应 |
| floating_debris > fabric | fabric/fiber | ✅ 直接对应 |
| floating_debris > misc_debris | others | ✅ 可映射 |
| floating_debris > water_plant / algae_mass | natural（含藻类、落叶） | ⚠️ 粗粒度混合类，未细分 |
| floating_debris > bottle | （plastic 内含瓶类，未单独分） | ⚠️ 无独立 bottle 类 |
| floating_debris > foam_board | （plastic 描述提及 foam blocks） | ⚠️ 未单独分类 |
| bloom_blackwater / outfall_discharge / bank_problem | — | ❌ 不覆盖 |

### 6. 核实结论

> **⚠️ 声称开放但分发极不稳定 — 百度网盘链接反复过期，GitHub 为空壳说明文件**
>
> 数据本身存在（3807 图、7 类、YOLO 格式），但获取渠道脆弱：5 个 issue 证实链接反复失效，作者回复率极低。建议尽早用当前有效链接（提取码 yghb）下载备份，并自行托管到项目仓库。

---

## 二、FloW-Img

| 项目 | 内容 |
|---|---|
| **发布机构** | ORCA TECH + Mila Lab（Yoshua Bengio）+ 清华大学 + 西北工业大学 |
| **年份** | 2021（ICCV 原始论文）；2025 年 PBM-YOLO 论文引用 |
| **原始论文** | FloW: A Dataset and Benchmark for Floating Waste Detection in Inland Waters, ICCV 2021, pp.10953-10962 |
| **PBM-YOLO 论文** | PBM-YOLO: A Performance Balanced Floating Garbage Detection Model for Water Surface Environments, IET Image Processing (2025) |
| **PBM-YOLO DOI** | [10.1049/ipr2.70248](https://doi.org/10.1049/ipr2.70248) |
| **官方页面** | https://orca-tech.cn/datasets/FloW/FloW-Img |

### 1. 下载渠道（实际验证）

**PBM-YOLO 论文 Data Availability Statement 原文**（逐字）：

> "**The author elects to not share data.**"

> 注意：此声明指 PBM-YOLO 作者自己构建的 Self-dataset 不共享，不影响 FloW-Img 本身的获取。

**FloW-Img 官方页面**（orca-tech.cn，2026-09-18 已访问成功）：

- 页面显示："The FloW-Img sub-dataset contains **2000 images** with more than **5000 labeled** floating wastes. The number of objects in one frame varies from 1 to 17. Among all the labeled floating wastes, the small objects (which occupy less than 32×32 pixels) account for the largest proportion in the dataset."
- 页面另有："we also provide **200 unannotated video sequences** of floating waste."
- 下载按钮 HTML 结构：`<a class="appl-download">Click here to download the FloW-Img.【Download】</a>`
- **点击下载按钮触发 Element UI 弹窗，aria-label="Request for Data"** —— 即**需提交数据申请表单，非开放直链**。
- 页面提供联系邮箱：**datasets@orca-tech.com.cn**

> **核实结论**：FloW-Img 不是公开直链下载。需通过官方页面提交"Request for Data"申请，或邮件联系 datasets@orca-tech.com.cn 获取。申请审批周期未知。

### 2. 许可协议

- 官方页面未在当前可见 HTML 中明确标注许可证类型。
- ICCV 论文本身为会议论文（通常 IEEE/CCF 版权）。
- 数据集使用条款需在申请时确认。
- **建议**：邮件申请时一并确认许可协议（是否允许商用/再分发）。

### 3. 规模

| 指标 | 值 |
|---|---|
| 图像总数 | **2000 张**（已核实） |
| 标注目标总数 | 5000+ 个 |
| 每帧目标数 | 1–17 个 |
| 小目标占比 | <32×32 像素的小目标占比最大（PBM-YOLO 论文称 55%） |
| 附加资源 | 200 个未标注视频序列 |
| 类别数 | **1 类：bottle** |
| 训练/测试/验证 | 7:2:1（PBM-YOLO 论文） |

### 4. 类别清单与标注格式

- **单类：bottle**（水面漂浮塑料瓶）。
- 标注格式：后续引用论文（如 MDPI Mathematics 2022, 10(22):4366）提到"converted into VOC2007 format"，说明原始标注为 **PASCAL VOC XML 格式**。可通过工具转换为 YOLO txt。

### 5. 覆盖 HYHQ 细类

| HYHQ 细类 | FloW-Img 对应 | 映射质量 |
|---|---|---|
| floating_debris > bottle | bottle | ✅ 直接对应，小目标场景丰富 |
| 其余所有细类 | — | ❌ 单类数据集，不覆盖 |

### 6. 核实结论

> **⚠️ 声称开放但需邮件/申请获取 — 非直链下载，许可待确认**
>
> 数据本身真实存在（2000 图、单类 bottle、5000+ 框），小目标场景质量高。但获取需走申请流程，许可协议未公开。对 HYHQ 价值集中在 bottle 类小目标增强。

---

## 三、TU Delft Green Village（TUD-GV）floating litter dataset

| 项目 | 内容 |
|---|---|
| **发布机构** | Delft University of Technology / Noria Sustainable Innovators |
| **年份** | 2023（Frontiers in Water 5:1298465） |
| **论文标题** | Advancing deep learning-based detection of floating litter using a novel open dataset |
| **DOI** | [10.3389/frwa.2023.1298465](https://doi.org/10.3389/frwa.2023.1298465) |
| **Zenodo 记录** | [10.5281/zenodo.7636124](https://doi.org/10.5281/zenodo.7636124) |
| **代码仓库** | https://github.com/TianlongJia/deep_plastic |

### 1. 下载渠道（实际验证）

**论文 Data availability statement 原文**（逐字）：

> "The code for this study is available on https://github.com/TianlongJia/deep_plastic. The 'TU Delft-Green Village' dataset is available for download from Zenodo at https://doi.org/10.5281/zenodo.7636124."

**Zenodo 记录页已访问成功**（2026-09-18）：

| 指标 | 值 |
|---|---|
| 记录标题 | TUD-GV Dataset for Floating Litter Detection |
| 发布日期 | 2023-04-19，Version 1.0 |
| 文件 | `TUD-GV Dataset.zip`，**5.6 GB** |
| MD5 | 6c1d264351a788741fd6025f45909f95 |
| 下载次数 | 361 次 |
| 浏览次数 | 1003 次 |
| 文件结构 | ZIP 内含 77 个目录 + `TUD-GV.xls`；每个目录下 4 个类别子目录（JPG 图） |

> **核实结论**：✅ Zenodo 直链可下载，文件完整（5.6 GB），无需登录、无需申请。

### 2. 许可协议

**Zenodo 记录页明确标注：Creative Commons Attribution 4.0 International (CC BY 4.0)**。

> 原文："License: Creative Commons Attribution 4.0 International. The Creative Commons Attribution license allows re-distribution and re-use of a licensed work on the condition that the creator is appropriately credited."

### 3. 规模

| 指标 | 值 |
|---|---|
| 图像总数 | **9473 张** RGB（703 张手机 + 8770 张运动相机） |
| 拍摄设备 | GoPro HERO4、GoPro MAX 360、Huawei P30 Pro |
| 拍摄场景 | 荷兰 TU Delft 校园排水沟渠，半受控实验环境 |
| 拍摄条件 | 晴天/阴天，2.7m/4.0m 高度，0°/45° 视角 |

### 4. 类别体系与标注格式 — ⚠️ 关键限制

**这是图像分类数据集，不是目标检测数据集。**

4 个类别按**画面中垃圾数量**划分，而非按垃圾材质划分：

| 类名 | 含义 | 图像数 |
|---|---|---|
| no litter | 0 个垃圾 | 2357 |
| little litter | 1–2 个垃圾 | 2299 |
| moderate litter | 3–5 个垃圾 | 2969 |
| lots of litter | 6–10 个垃圾 | 1848 |

**标注格式：整图文件夹级分类标签，无 bounding box。**

论文原文明确说明："To accurately estimate litter fluxes, we need the information of the spatio-temporal variation of floating litter... The number of such application is expected to increase... we aim to build on the released version by **providing individual labels for each item as well as bounding boxes** to perform object detection."

> **即：当前版本没有目标框标注，无法直接训练 YOLO 检测器。** 论文作者明确将"加 bounding box"列为未来工作。

### 5. 覆盖 HYHQ 细类

| HYHQ 细类 | TUD-GV 对应 | 映射质量 |
|---|---|---|
| floating_debris 大类（概念覆盖） | 4 级垃圾密度分类 | ⚠️ 无框，不能训练检测；可用于 backbone 预训练或场景分类 |
| bloom_blackwater / outfall_discharge / bank_problem | — | ❌ 不覆盖 |

> **关键判断**：TUD-GV 对 YOLOv8n 检测器训练**无直接价值**（无框标注）。可考虑用于：(1) 图像分类预训练 backbone；(2) 水面场景场景理解；(3) 但不解决 HYHQ 的检测标注需求。

### 6. 核实结论

> **✅ 已核实可下载（Zenodo 直链，CC BY 4.0，5.6 GB）— 但不适合 YOLO 检测训练**
>
> 数据真实、开放、可下载，但标注粒度为整图分类（垃圾密度 4 级），无 bounding box。对 HYHQ YOLOv8n 检测管线无直接训练价值，仅可作为辅助预训练数据。

---

## 四、WATER-DET（D0 决策门核心）

| 项目 | 内容 |
|---|---|
| **发布机构** | 论文作者 Song X., Zuo G., Wang X., Xie J.（Frontiers in Environmental Science） |
| **年份** | 2025（Front. Environ. Sci. 13:1657930） |
| **论文标题** | Automatic recognition of environmental hazards in river and lake ecosystems using deep learning |
| **DOI** | [10.3389/fenvs.2025.1657930](https://doi.org/10.3389/fenvs.2025.1657930) |
| **论文页面** | https://www.frontiersin.org/articles/10.3389/fenvs.2025.1657930/full |

### 1. 下载渠道（实际验证）— ❌ 无公开下载

**Data availability statement 原文**（逐字，Frontiers 论文 Statements 区块）：

> "**The original contributions presented in the study are included in the article/supplementary material, further inquiries can be directed to the corresponding authors.**"

> **这是 Frontiers 论文系统中标准的"数据不公开，需联系通讯作者"声明。** 没有给出任何 GitHub / Zenodo / Figshare / Kaggle / Roboflow 链接。

**进一步搜索验证**：

- 以 "WATER-DET" + "github" / "download" 为关键词搜索，**未发现任何公开代码仓库或数据集仓库**。
- Frontiers 论文 supplementary material 页面未包含数据集下载链接（仅有论文图表补充材料）。
- 论文全文中未出现任何 URL 指向数据托管平台。

> **核实结论**：❌ **WATER-DET 数据集无公开下载渠道**。论文声称构建了该数据集，但 Data Availability 只说"进一步咨询联系通讯作者"。获取数据必须邮件联系通讯作者，且是否回复、是否提供、许可条件均不可控。

### 2. 许可协议

- 论文本身为 **CC BY 4.0**（Frontiers 开放获取，原文："This is an open-access article distributed under the terms of the Creative Commons Attribution License (CC BY)"）。
- **但数据集本身未公开，因此数据集许可协议未知**。即使论文是 CC BY，数据集的实际使用权需在获取时与作者确认。

### 3. 规模

| 指标 | 值 |
|---|---|
| 图像总数 | **1500 张**（RGB）（论文说 "over 1,500"，Table 1 合计为 1590） |
| 类别数 | **12 类** |
| 训练/验证/测试 | 1050 / 150 / 300（7:1:2） |
| 标注工具 | labelImg，矩形 bounding box |
| 输入分辨率 | 160×160（论文实验配置） |

### 4. 12 个类别完整清单与各类别样本量

**论文 Table 1 完整数据**：

| # | 识别目标（论文原文） | 样本量 | HYHQ 映射 |
|---|---|---|---|
| 1 | Algae Pollution（水华藻类，绿色变色+可见浮藻） | 150 | → algae_mass ✅ |
| 2 | Oil Film Pollution（水面油膜） | 80 | → sewage_color ⚠️（油膜色） |
| 3 | Red Pollution（红色水体） | 150 | → sewage_color ⚠️ |
| 4 | Yellow Pollution（黄色水体） | 150 | → sewage_color ⚠️ |
| 5 | Foam Pollution（水面泡沫） | 150 | → foam_pollution ✅ |
| 6 | Sewage（黑/灰色污水） | 150 | → sewage_color ✅ |
| 7 | Garbage（水面或岸线垃圾） | 150 | → misc_debris / bank_garbage ✅ |
| 8 | Fish（水面漂浮死鱼） | 80 | ❌ 不在 HYHQ 15 细类中 |
| 9 | Leaves（水面漂浮落叶） | 80 | ❌ 不在 HYHQ 15 细类中 |
| 10 | Sewage Outlet（排污管道/排水口） | 150 | → outfall ✅ |
| 11 | Sand Yard（岸线采砂场） | 150 | ❌ 不在 HYHQ 15 细类中 |
| 12 | Building（岸线旁建筑） | 150 | → bank_encroach ✅ |

**标注格式**：labelImg 手动标注矩形框，标准目标检测格式（YOLO 可用，需确认是 YOLO txt 还是 VOC XML）。论文未明确说明导出格式，但使用 labelImg 通常可导出 YOLO/VOC 两种格式。

### 5. 覆盖 HYHQ 细类 — 关键价值

**WATER-DET 是 4 个数据集中唯一同时覆盖 HYHQ 三大问题域的数据集**：

| HYHQ 大类 | WATER-DET 覆盖的细类 |
|---|---|
| floating_debris | Garbage（水面/岸线垃圾） |
| bloom_blackwater | Algae Pollution → algae_mass；Foam Pollution → foam_pollution；Sewage/Oil/Red/Yellow → sewage_color |
| outfall_discharge | Sewage Outlet → outfall |
| bank_problem | Building → bank_encroach；Garbage → bank_garbage |

> 其余 3 个数据集（YRDG / FloW-Img / TUD-GV）**均只覆盖 floating_debris 中的垃圾材质类**，完全不涉及水华黑臭、排污口、岸带问题。

### 6. 核实结论

> **❌ 不可直接下载 — 需邮件联系通讯作者，无公开仓库**
>
> D0 决策门核心判断：WATER-DET 论文 Data Availability 声明为"further inquiries can be directed to the corresponding authors"，无任何公开数据链接。该数据集对 HYHQ 价值最高（唯一覆盖 bloom_blackwater / outfall_discharge / bank_problem），但获取路径不可控。
>
> **建议**：(1) 立即邮件联系通讯作者申请数据；(2) 不要将其作为 D0 阶段的确定性数据来源；(3) 同时规划替代方案（自采数据 + YRDG/FloW-Img 增强 floating_debris 类）。

---

## 五、4 个数据集核实状态对比汇总表

| 维度 | YRDG | FloW-Img | TUD-GV | WATER-DET |
|---|---|---|---|---|
| **论文 DOI** | 10.3390/s24010050 | 10.1049/ipr2.70248 | 10.3389/frwa.2023.1298465 | 10.3389/fenvs.2025.1657930 |
| **下载渠道** | 百度网盘（GitHub 空壳） | 官网 Request 弹窗/邮件 | Zenodo 直链 | ❌ 无公开渠道 |
| **渠道状态** | ⚠️ 链接反复过期 | ⚠️ 需申请 | ✅ 直链可下 | ❌ 需邮件联系作者 |
| **issue/反馈证据** | 5 个 issue 全为链接过期 | — | 361 次正常下载 | — |
| **许可协议** | 论文 CC BY 4.0；repo GPLv3 | 未公开，待确认 | ✅ CC BY 4.0 | 论文 CC BY；数据集许可未知 |
| **图像数** | 3807 | 2000 | 9473 | ~1590 |
| **类别数** | 7（垃圾材质） | 1（bottle） | 4（垃圾密度，非材质） | 12（含水质/排污口/岸带） |
| **标注格式** | YOLO txt（+ VOC 类名） | VOC XML（需转 YOLO） | 文件夹级分类（无框） | labelImg 矩形框 |
| **有 bounding box** | ✅ 有 | ✅ 有 | ❌ **无** | ✅ 有 |
| **HYHQ 覆盖** | floating_debris 7/10 细类 | floating_debris > bottle | 无直接检测价值 | **4 大类全覆盖** |
| **bloom_blackwater** | ❌ | ❌ | ❌ | ✅ 3 细类 |
| **outfall_discharge** | ❌ | ❌ | ❌ | ✅ outfall |
| **bank_problem** | ❌ | ❌ | ❌ | ✅ 2 细类 |
| **综合结论** | ⚠️ 可下载但不稳定 | ⚠️ 需申请 | ✅ 可下但无框 | ❌ 不可直接获取 |

---

## 六、对 HYHQ 数据选型的行动建议

1. **TUD-GV**：可立即从 Zenodo 下载备份，但**不要用于 YOLO 检测训练**（无框）。如需要水面场景预训练 backbone 可考虑。
2. **YRDG**：立即用当前百度网盘链接（提取码 yghb）下载备份，下载后自行托管。这是 floating_debris 类（plastic/paper/glass/metal/fabric）的主力数据源。
3. **FloW-Img**：立即向 datasets@orca-tech.com.cn 邮件申请，重点获取 bottle 小目标类。同时确认许可协议。
4. **WATER-DET（D0 决策门）**：**不满足 D0 可下载性要求**。立即邮件联系通讯作者申请，但不可作为确定性依赖。HYHQ 的 bloom_blackwater / outfall_discharge / bank_problem 三大类若无 WATER-DET 数据，需规划自采或其他公开数据源补充。

---

*本报告所有结论均基于 2026-09-18 实际访问的 URL 页面内容。百度网盘链接有效性可能随时间变化，建议尽早下载备份。*

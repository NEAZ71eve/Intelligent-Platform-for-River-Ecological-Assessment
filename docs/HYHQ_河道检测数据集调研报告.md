# HYHQ 河道生态评估项目 — 公开可下载目标检测数据集调研报告

> **调研目标**：为 YOLOv8n 检测模型寻找"排污口/污水直排"与"岸线垃圾堆积/岸线侵占"两个方向的公开图像数据集
> **视角约束**：河道/溪流/湖泊岸边视角（巡河员手机、无人机近岸、桥梁拍摄），排除道路 dashcam
> **调研日期**：2026-09-18
> **细类映射**：
> - `outfall_discharge` (id=2) → `outfall`（雨水排口/污水排口/管道直排口）
> - `bank_problem` (id=3) → `bank_garbage`（岸线垃圾堆积）、`bank_encroach`（岸线侵占/违建/护坡破坏）

---

## 一、核心结论速览

| 方向 | 首选数据集 | 次选数据集 | 公开度评价 |
|------|-----------|-----------|-----------|
| **A. 排污口检测** | **iSOOD**（10,481 张，CC BY 4.0，Zenodo 直下） | UAS-outfall（样本公开，完整需申请） | ⭐ 有高质量公开数据集，**可直接用** |
| **B1. 岸线垃圾** | **IWHR Floater V1**（3,000 张，Figshare 直下） | YRDG / FloW-Img / CANSURF | ⭐ 水面漂浮物数据集丰富，**岸线堆积可跨用** |
| **B2. 岸线侵占/违建** | **无公开专用数据集** | Space-hehu（论文自建未公开）、PGIS_RCD（未公开） | ❌ **公开数据集稀缺**，需自采+合成 |

> **关键判断**：排污口方向已有 iSOOD 这一"黄金数据集"，几乎可直接作为 outfall 类的主力训练集。岸线垃圾方向可从水面漂浮物数据集迁移学习。**岸线侵占/违建方向是最大短板**，公开数据集中没有专门标注 bank_encroach 的数据集，必须自采+弱监督+合成数据组合方案。

---

## 二、A 方向：排污口/排水口/污水直排检测

### 数据集 A1：iSOOD — Images for Sewage Outfalls Objective Detection ⭐⭐⭐ 首选

| 字段 | 内容 |
|------|------|
| **发布机构** | 清华大学（环境学院）+ 长江流域生态环境监督管理局 |
| **年份** | 2024 |
| **论文** | *Scientific Data*, DOI: [10.1038/s41597-024-03574-9](https://doi.org/10.1038/s41597-024-03574-9) |
| **数据集链接** | ✅ **Zenodo 直接下载**：[https://doi.org/10.5281/zenodo.10903574](https://doi.org/10.5281/zenodo.10903574) |
| **代码仓库** | [https://github.com/Daniel00ll/iSOOD-code](https://github.com/Daniel00ll/iSOOD-code) |
| **许可协议** | **CC BY 4.0**（署名即可商用/修改/分发） |
| **规模** | **10,481 张图像**，10,481 条排口记录；压缩包 9.5 GB；Excel 属性表 273 KB |
| **标注格式** | **YOLO 格式**（.txt 标注文件）+ Excel 属性表（每行一个排口） |
| **视角** | **无人机航拍 + 手持相机岸边拍摄**（混合视角，覆盖长江流域 9,285 张 + 黄河流域 1,196 张） |
| **覆盖类别** | 10 类排口：①合流制 ②雨水 ③工业废水 ④农业排水 ⑤畜禽养殖 ⑥水产养殖 ⑦地表径流 ⑧污水处理厂 ⑨生活污水 ⑩其他 |
| **目标尺寸分布** | 大目标(>96px) 80.0%，中目标(32-96px) 18.6%，小目标(<32px) 1.4% |
| **已核实状态** | ✅ **已核实可下载**（Zenodo 页面确认文件存在，CC BY 4.0，2024-04-01 发布，1,465 次下载） |

**与 HYHQ 细类映射**：
- ✅ **直接映射 `outfall_discharge.outfall`**：所有 10 类排口都是 HYHQ 关注的"雨水排口/污水排口/管道直排口"
- ⚠️ 视角偏差：iSOOD 以无人机斜拍为主，HYHQ 巡河员手机岸边平视视角需要做域适应（domain adaptation）
- 💡 建议：直接用 iSOOD 预训练 YOLOv8n，再用少量自采岸边视角数据 fine-tune

---

### 数据集 A2：UAS-Outfall Benchmark（GeoDCNN-outfalls）⭐⭐ 次选

| 字段 | 内容 |
|------|------|
| **发布机构** | 中科院地理科学与资源研究所（资源与环境信息系统国家重点实验室） |
| **年份** | 2024 |
| **论文** | *International Journal of Digital Earth*, DOI: [10.1080/17538947.2024.2390443](https://doi.org/10.1080/17538947.2024.2390443) |
| **数据集链接** | ⚠️ **样本公开，完整数据集需邮件申请**：[https://github.com/WuChengbin/GeoDCNN](https://github.com/WuChengbin/GeoDCNN) |
| **许可协议** | 未明确（开源样本仓库，完整数据 "on request"） |
| **规模** | **8,746 张图像**（600×600 px），10,000+ 标注框；附带 DSM（数字表面模型）数据 |
| **标注格式** | **PASCAL VOC** 格式（XML），可转 COCO/YOLO；额外带排口流向方向线标注 |
| **视角** | **无人机正射俯视**（10 cm 分辨率，CW-100 固定翼无人机，SONY ILCE-7RM2） |
| **覆盖类别** | 3 大类 7 子类：①TRC（建筑结构型：三角 1,763 / 矩形 1,741 / 涵洞 1,153）②POC（管道/明渠型：管道 1,460 / 明渠 1,390）③SAC（可疑区：敏感区 ~1,200 / 汇流区 ~1,200） |
| **已核实状态** | ⚠️ **仅样本公开**（GitHub 仓库有示例代码和少量样本），完整数据需向作者申请 |

**与 HYHQ 细类映射**：
- ✅ 映射 `outfall_discharge.outfall`：管道型（POC）与 HYHQ "管道直排口"高度吻合
- ⚠️ 视角偏差大：**正射俯视 vs 巡河员平视**，迁移成本高
- 💡 建议：作为补充训练数据，尤其用于学习排口的几何结构特征；与 iSOOD 组合使用

---

### 数据集 A3：WATER-DET（河湖环境隐患数据集）⭐⭐ 次选

| 字段 | 内容 |
|------|------|
| **发布机构** | Frontiers in Environmental Science（多机构联合） |
| **年份** | 2025 |
| **论文** | DOI: [10.3389/fenvs.2025.1657930](https://doi.org/10.3389/fenvs.2025.1657930) |
| **数据集链接** | ❌ **未公开下载**（论文声明 "further inquiries can be directed to the corresponding authors"） |
| **规模** | **1,500 张 RGB 图像**，12 类，训练/验证/测试 = 1050/150/300 |
| **标注格式** | YOLO 边界框（labelImg 标注） |
| **视角** | **现场摄影 + 监控摄像头 + 无人机航拍**（混合，含手机/相机/无人机三端） |
| **覆盖类别** | 12 类：①藻类污染 ②油膜污染 ③红色污染 ④黄色污染 ⑤泡沫污染 ⑥污水（黑臭）**⑦垃圾（水面/岸线）150 张** **⑧死鱼 ⑨落叶 ⑩排污口 150 张** ⑪采砂场 150 张 **⑫建筑（岸线违建）150 张** |
| **已核实状态** | ❌ **仅论文声称**，未找到公开下载渠道 |

**与 HYHQ 细类映射**：
- ✅ 同时覆盖 `outfall`（150 张）、`bank_garbage`（150 张）、`bank_encroach`（建筑 150 张 + 采砂场 150 张）
- ⚠️ **每类仅 ~150 张**，规模偏小，且数据未公开
- 💡 建议：**尝试邮件联系通讯作者申请数据**；该数据集类别设计与 HYHQ 高度契合，若能拿到将极有价值

---

### 数据集 A4：SODNet 数据集（iSOOD 延伸）⭐ 备选

| 字段 | 内容 |
|------|------|
| **发布机构** | Scientific Reports 2026 |
| **论文** | DOI: [10.1038/s41598-026-45595-x](https://doi.org/10.1038/s41598-026-45595-x) |
| **数据集** | 基于 iSOOD 的十千余张排口图像，覆盖多种排口类型和光照条件 |
| **备注** | 本质是 iSOOD 的二次使用，无新增数据；SODNet 是在 iSOOD 上训练的轻量检测网络 |
| **已核实状态** | ✅ 数据 = iSOOD（见 A1） |

---

## 三、B 方向：岸线垃圾堆积 / 岸线侵占

### 数据集 B1：IWHR_AI_Lable_Floater_V1（北京大运河漂浮物）⭐⭐⭐ 首选（bank_garbage）

| 字段 | 内容 |
|------|------|
| **发布机构** | 中国水利水电科学研究院（IWHR） |
| **年份** | 2025 |
| **论文** | *Scientific Data*, DOI: [10.1038/s41597-025-04594-9](https://doi.org/10.1038/s41597-025-04594-9) |
| **数据集链接** | ✅ **Figshare 直接下载**：[https://doi.org/10.6084/m9.figshare.27376851.v1](https://doi.org/10.6084/m9.figshare.27376851.v1) |
| **许可协议** | 未明确标注（Figshare 默认需查看，论文未指定 CC 协议） |
| **规模** | **3,000 张标注图像**，**23,692 个标注对象**（边界框） |
| **标注格式** | JPG 图像 + **XML 标注文件**（PASCAL VOC 风格，可转 YOLO） |
| **视角** | **岸边固定拍摄设备 + 监控摄像头 + 移动设备**（完美匹配巡河员视角！） |
| **采集地点** | 北京通州区北关闸至通济路桥段大运河 + 附近减河（2022 年） |
| **覆盖类别** | 水面漂浮垃圾：塑料瓶、泡沫板、包装袋、水草、藻类等 |
| **已核实状态** | ✅ **已核实可下载**（Figshare DOI 有效，waste-datasets-review 项目收录） |

**与 HYHQ 细类映射**：
- ✅ **映射 `bank_problem.bank_garbage`**：视角完全匹配（岸边/监控/手机）
- ⚠️ 主要是**水面漂浮物**，HYHQ 需要的是**岸线堆积垃圾**——但物体类别高度重叠（塑料瓶、泡沫板等），可通过裁剪/视角变换迁移
- 💡 建议：作为 bank_garbage 主力训练集，配合少量自采岸线堆积样本

---

### 数据集 B2：YRDG（黄河水漂垃圾数据集）⭐⭐ 次选

| 字段 | 内容 |
|------|------|
| **发布机构** | MDPI *Sensors* 2024（APM-YOLOv7 论文） |
| **年份** | 2023 |
| **论文** | [https://www.mdpi.com/1424-8220/24/1/50](https://www.mdpi.com/1424-8220/24/1/50) |
| **数据集链接** | ✅ **GitHub 直接下载**：[https://github.com/jingcodejing/YRDG-dataset](https://github.com/jingcodejing/YRDG-dataset) |
| **代码** | [https://github.com/jingcodejing/AAM...](https://github.com/jingcodejing) |
| **许可协议** | 未明确（GitHub 仓库） |
| **规模** | **3,807 张图像**（640×640 px），训练 3,083 / 验证 343 / 测试 381 |
| **标注格式** | YOLO 格式 |
| **视角** | 黄河水面/岸边（84% 为小目标） |
| **覆盖类别** | 7 类水漂垃圾：塑料、纸张、玻璃、金属、织物、橡胶、其他 |
| **已核实状态** | ✅ **已核实可下载**（GitHub 仓库公开） |

**与 HYHQ 细类映射**：
- ✅ 映射 `bank_garbage`：塑料瓶/包装袋等类别直接可用
- ⚠️ 黄河大水面视角，与城市河道岸边视角有差异
- 💡 建议：作为 bank_garbage 的补充训练数据，增强小目标检测能力

---

### 数据集 B3：FloW（FloW-Img / FloW-RI）⭐⭐ 次选

| 字段 | 内容 |
|------|------|
| **发布机构** | 欧卡智舶（ORCA-Uboat）+ Mila 实验室 + 清华大学 + 西北工业大学 |
| **年份** | 2021（ICCV Workshop） |
| **论文** | [ICCV 2021](https://openaccess.thecvf.com/content/ICCV2021/papers/Cheng_FloW_A_Dataset_and_Benchmark_for_Floating_Waste_Detection_in_ICCV_2021_paper.pdf) |
| **数据集链接** | ⚠️ **需申请**：[https://github.com/ORCA-Uboat/FloW-Dataset](https://github.com/ORCA-Uboat/FloW-Dataset)（通过 ORCA-Uboat 数据门户申请） |
| **规模** | FloW-Img：**2,000 张图像 / 5,271 个标注对象**；FloW-RI：4,000 帧（图像+毫米波雷达同步） |
| **标注格式** | 目标检测 + 多模态（雷达 RDM 数据） |
| **视角** | **水面无人船（USV）第一视角**（近岸水面视角） |
| **覆盖类别** | 漂浮垃圾（bottle 为主类） |
| **已核实状态** | ⚠️ **需申请**（GitHub 仓库存在，但数据需走申请流程） |

**与 HYHQ 细类映射**：
- ✅ 映射 `bank_garbage`：USV 近岸视角与巡河员岸边视角接近
- 💡 建议：尝试申请，多模态雷达数据对纯视觉模型训练帮助有限，但图像部分有价值

---

### 数据集 B4：Space-hehu（天津西青"四乱"数据集）⭐⭐ 次选（bank_encroach 方向）

| 字段 | 内容 |
|------|------|
| **发布机构** | 天津农学院（计算机与信息工程学院 + 水利工程学院） |
| **年份** | 2025 |
| **论文** | PMC12944004 — *Multi-Objective Detection of River and Lake Spaces Based on YOLOv11n* |
| **数据集链接** | ❌ **未公开**（自建数据集，论文未提供下载链接） |
| **规模** | **28,120 张原始图像**（高质量标注），训练 19,684 / 验证 5,624 / 测试 2,812 |
| **视角** | **现场摄影 + 无人机航拍**（天津西青区一级/二级河流 + 滨海新区） |
| **覆盖类别（12 类）** | bottle(2,560) / packaging(1,750) / branch(2,074) / trash(2,778) / **engineering(3,800)** / **greenhouse(4,090)** / **building(3,076)** / **garbage(2,383)** / clean(589) / pollute(746) / normal(567) / plastic(3,291) |
| **已核实状态** | ❌ **仅论文声称**，未找到公开下载渠道 |

**与 HYHQ 细类映射**：
- ✅ **engineering / greenhouse / building → `bank_encroach`**（岸线侵占/违建/大棚/工程设施）
- ✅ **garbage / trash / bottle / packaging → `bank_garbage`**（岸线垃圾）
- ⚠️ **这是最接近 HYHQ 需求的中文数据集**，但数据未公开
- 💡 建议：**邮件联系天津农学院作者申请数据**（论文地址：liuling@tjau.edu.cn）；若能拿到，bank_encroach 方向问题将基本解决

---

### 数据集 B5：PGIS_RCD（河道岸线地物变化检测数据集）⭐ 备选（bank_encroach 方向）

| 字段 | 内容 |
|------|------|
| **发布机构** | 《人民长江》期刊 |
| **年份** | 2025 |
| **论文** | [基于无人机全景影像的河道岸线地物变化检测方法](http://www.rmcjzz.cjw.cn/cn/article/id/cd221f37-a013-4e7c-a15c-fb97b370ca4c) |
| **数据集链接** | ❌ **未公开**（论文未提供下载链接） |
| **规模** | 未明确（全景影像切片，Labelme 标注） |
| **视角** | **无人机全景影像** |
| **覆盖类别** | 6 大类，含**违章建筑、非法占用**行为 |
| **已核实状态** | ❌ **仅论文声称** |

---

### 数据集 B6：CANSURF（ASV 视角水面漂浮物）⭐ 备选

| 字段 | 内容 |
|------|------|
| **发布机构** | arXiv 2025（Zaid Aljundi 等） |
| **论文** | [arXiv:2605.16774](https://arxiv.org/html/2605.16774v1) |
| **数据集链接** | ✅ **Zenodo 直接下载**：[https://doi.org/10.5281/zenodo.20100657](https://doi.org/10.5281/zenodo.20100657) |
| **GitHub** | [https://github.com/ZaidAljundiHW2/CANSURF](https://github.com/ZaidAljundiHW2/CANSURF) |
| **规模** | **57,012 张图像**（训练 55,246 张） |
| **视角** | **ASV（自主水面航行器）第一视角** |
| **覆盖类别** | 水面漂浮物（can 为主） |
| **已核实状态** | ✅ **已核实可下载** |

**与 HYHQ 细类映射**：
- ✅ 映射 `bank_garbage`：ASV 视角与近岸水面视角接近
- ⚠️ 主要是罐头类漂浮物，类别较单一
- 💡 建议：作为补充数据增强漂浮物小目标检测

---

## 四、C 方向：海岸垃圾延伸数据集（跨用参考）

### 数据集 C1：CoxPWD 2025（Cox's Bazar 海滩塑料垃圾）⭐⭐ 次选

| 字段 | 内容 |
|------|------|
| **发布机构** | East West University（孟加拉） |
| **年份** | 2025 |
| **数据集链接** | ✅ **Mendeley Data 直接下载**：[https://data.mendeley.com/datasets/bdzg4tjy63/1](https://data.mendeley.com/datasets/bdzg4tjy63/1) |
| **DOI** | [10.17632/bdzg4tjy63.1](https://doi.org/10.17632/bdzg4tjy63.1) |
| **许可协议** | **CC BY 4.0** |
| **规模** | **4,195 张 RGB 图像**（640×640 JPEG），365 MB；训练 3,367 / 验证 414 / 测试 414 |
| **标注格式** | **COCO JSON** 格式（15 类） |
| **视角** | **海滩地面视角**（iPhone 15 Pro Max / Pixel 6 / Canon 650D，1m 和 6m 高度，15°/45° 多角度） |
| **覆盖类别** | 15 类：packet, polythene, cup, spoon, straw, rope, bag, **bottle**, bottle_cap, net, sunglass, toy, fishing_item, others, objects |
| **已核实状态** | ✅ **已核实可下载**（Mendeley 页面确认，123 次下载） |

**与 HYHQ 细类映射**：
- ✅ 映射 `bank_garbage`：塑料瓶/袋/杯等类别直接可用；地面视角与岸线视角接近
- ⚠️ 海滩 vs 河道岸线，背景差异较大（沙地 vs 草地/护坡/水泥）
- 💡 建议：作为 bank_garbage 的补充，增强小目标塑料垃圾检测

---

### 数据集 C2：BePLi Dataset v2（日本海滩塑料垃圾）⭐ 备选

| 字段 | 内容 |
|------|------|
| **发布机构** | 日本山形大学 |
| **年份** | 2024 |
| **数据集链接** | ✅ **SEANOE 直接下载**：[https://doi.org/10.17882/96963](https://doi.org/10.17882/96963) |
| **许可协议** | **CC BY-NC-SA 4.0**（非商业） |
| **规模** | **3,722 张图像**，**118,572 个标注**，13 类 |
| **标注格式** | MS COCO 格式（实例分割 + 目标检测） |
| **视角** | 日本沿海海滩（沙滩、岩滩、消波块） |
| **已核实状态** | ✅ **已核实可下载** |

---

### 数据集 C3：BeachLitter v2022（海滩垃圾分割）⭐ 备选

| 字段 | 内容 |
|------|------|
| **数据集链接** | ✅ **SEANOE**：[https://doi.org/10.17882/85472](https://doi.org/10.17882/85472) |
| **许可协议** | **CC BY 4.0** |
| **规模** | **3,500 张图像**，8 类（bottle, can, carton, cup, other plastic, other plastic containers, plastic bag, wrapper） |
| **标注格式** | 语义分割（像素级掩码） |
| **视角** | 海滩 |
| **已核实状态** | ✅ **已核实可下载** |

---

### 数据集 C4：TrashCan 1.0（水下垃圾分割）⭐ 备选

| 字段 | 内容 |
|------|------|
| **发布机构** | University of Minnesota（DRUM 仓库） |
| **数据集链接** | ✅ [https://conservancy.umn.edu/handle/11299/214865](https://conservancy.umn.edu/handle/11299/214865) |
| **DOI** | [10.13020/g1gx-y834](https://doi.org/10.13020/g1gx-y834) |
| **规模** | **7,212 张图像**，3 大类 34 子类 |
| **标注格式** | 实例分割 + 边界框 |
| **视角** | **水下 ROV 视角** |
| **已核实状态** | ✅ **已核实可下载** |

---

### 数据集 C5：SeaClear Marine Debris Dataset ⭐ 备选

| 字段 | 内容 |
|------|------|
| **发布机构** | SeaClear 项目（克罗地亚/法国浅海） |
| **论文** | *Scientific Data* 2024 |
| **规模** | **8,610 张水下 ROV 图像**，40 类 |
| **标注格式** | 边界框 + 实例分割掩码 |
| **视角** | 水下 ROV（BlueROV / Mini-Tortuga） |
| **GitHub** | [https://github.com/adjuras/seaclear-dataset](https://github.com/adjuras/seaclear-dataset) |
| **已核实状态** | ✅ **已核实可下载** |

---

### 数据集 C6：DroneWaste（无人机垃圾堆放点）⭐ 备选

| 字段 | 内容 |
|------|------|
| **数据集链接** | ✅ **Zenodo**：[https://zenodo.org/records/17288038](https://zenodo.org/records/17288038) |
| **许可协议** | **CC BY 4.0** |
| **规模** | **4,993 张图像**，17 个固体废弃物堆放点（无人机正射影像） |
| **视角** | **无人机正射俯视** |
| **已核实状态** | ✅ **已核实可下载** |

**与 HYHQ 细类映射**：
- ✅ 可辅助学习 `bank_encroach`（违规堆放点的俯视特征）
- ⚠️ 正射俯视视角差异大，仅作弱参考

---

### 数据集 C7：UAVVaste（无人机垃圾检测）⭐ 备选

| 字段 | 内容 |
|------|------|
| **GitHub** | [https://github.com/UAVVaste/UAVVaste](https://github.com/UAVVaste/UAVVaste) |
| **规模** | **772 张图像**，3,716 个标注 |
| **标注格式** | 检测 + 分割 |
| **视角** | 无人机航拍 |
| **已核实状态** | ✅ **已核实可下载** |

---

## 五、D 方向：其他参考数据集

### 数据集 D1：RoLID-11K（道路垃圾 dashcam）— 弱参考（已排除为主力）

| 字段 | 内容 |
|------|------|
| **GitHub** | [https://github.com/xq141839/RoLID-11K](https://github.com/xq141839/RoLID-11K) |
| **arXiv** | [2601.00398](https://arxiv.org/html/2601.00398) |
| **视角** | **道路 dashcam**（非岸边视角） |
| **已核实状态** | ✅ 存在，但按用户要求**仅作弱参考** |

### 数据集 D2：YRLW（浙江大学水漂垃圾）⭐ 备选

| 字段 | 内容 |
|------|------|
| **论文** | 浙江大学学报 2026 — 边缘感知和跨尺度特征增强的小目标水漂垃圾检测 |
| **规模** | 19,633 个标注（plastic 7,923 / glass 803 / ... / others 982） |
| **视角** | 水面水漂垃圾 |
| **备注** | 新发布数据集，具体下载链接需进一步确认 |

---

## 六、推荐优先级与组合策略

### ⭐⭐⭐ 首选组合（可立即下载使用）

| 数据集 | 方向 | 下载状态 | 在训练中的角色 |
|--------|------|---------|--------------|
| **iSOOD** (10,481 张) | outfall | ✅ Zenodo CC BY 4.0 | **主力预训练**：outfall 类全部训练数据 |
| **IWHR Floater V1** (3,000 张) | bank_garbage | ✅ Figshare | **主力预训练**：bank_garbage 类，视角匹配 |

### ⭐⭐ 次选组合（补充增强）

| 数据集 | 方向 | 下载状态 | 角色 |
|--------|------|---------|------|
| **YRDG** (3,807 张) | bank_garbage | ✅ GitHub | 补充小目标塑料垃圾 |
| **CoxPWD 2025** (4,195 张) | bank_garbage | ✅ Mendeley CC BY 4.0 | 补充塑料瓶/袋多角度样本 |
| **CANSURF** (57,012 张) | bank_garbage | ✅ Zenodo | 大规模漂浮物预训练 |
| **BePLi v2** (3,722 张) | bank_garbage | ✅ SEANOE CC BY-NC-SA | 海滩塑料垃圾补充 |
| **UAS-Outfall** | outfall | ⚠️ 需申请 | 管道型排口补充 |
| **FloW-Img** | bank_garbage | ⚠️ 需申请 | USV 近岸视角补充 |

### ⭐ 备选/需主动联系

| 数据集 | 方向 | 状态 | 行动建议 |
|--------|------|------|---------|
| **WATER-DET** (1,500 张) | outfall + bank_garbage + bank_encroach | ❌ 未公开 | **邮件联系通讯作者**（类别设计与 HYHQ 最契合） |
| **Space-hehu** (28,120 张) | bank_encroach + bank_garbage | ❌ 未公开 | **邮件联系天津农学院**（liuling@tjau.edu.cn），12 类含违建/大棚/工程 |
| **PGIS_RCD** | bank_encroach | ❌ 未公开 | 关注《人民长江》期刊后续数据公开 |

---

## 七、岸线侵占（bank_encroach）数据稀缺的应对方案

> **核心问题**：公开数据集中**没有专门标注"岸线侵占/违建/护坡破坏"的数据集**。Space-hehu（天津西青）和 WATER-DET 论文中涉及此类，但均未公开数据。

### 方案 1：自采数据（推荐，最有效）

**拍摄位置建议**：
- 城市河道两岸的巡河步道、桥梁
- 城郊结合部河道（违建/堆料/菜地概率高）
- 工业园区附近河道（企业直排/侵占概率高）
- 乡村河道（围垦/种菜/搭建）

**拍摄数量建议**：
- `bank_encroach` 每类至少 **500-1000 张**（违建、堆料、围垦、护坡破坏各 200+）
- `bank_garbage` 岸线堆积至少 **500 张**（补充水面漂浮物数据集的视角差异）
- `outfall` 岸边平视视角至少 **300-500 张**（补充 iSOOD 的无人机视角差异）

**拍摄规范**：
- 手机横屏 1080p 以上，与巡河员实际工作流一致
- 距离目标 5-20 米，模拟实际巡检场景
- 覆盖不同光照（晴天/阴天/傍晚）、不同季节、不同水位
- 每张图包含 1-3 个目标，避免过密

### 方案 2：合成数据（Synthetic Data）

**排口合成**：
- 用 SVG/Blender 生成管道排口图像（圆形/方形/半圆形管口）
- 将合成排口 paste 到真实河岸背景上（copy-paste augmentation）
- 参考论文：*Synthetic Meets Authentic* (arXiv 2024) 的方法

**违建合成**：
- 从公开建筑数据集（如 xView、DOTA）裁剪建筑样本
- 透视变换后叠加到河道背景上

### 方案 3：弱监督伪标签（Weak Supervision）

- 用通用垃圾检测模型（如 YOLOv8x-pretrained on COCO）在自采视频上跑推理
- 人工审核伪标签，修正后作为训练数据
- 工具：Roboflow AutoLabel、Grounding DINO + SAM

### 方案 4：利用公开建筑/堆料数据集迁移

- **xView / DOTA**：航拍建筑数据集，裁剪后用于学习违建的视觉特征
- **DroneWaste**（Zenodo CC BY 4.0）：无人机视角堆放点，辅助学习违规堆料
- **OpenStreetMap + 卫星图**：提取已知违建区域的历史卫星图作为弱监督

---

## 八、所有验证过的 URL 汇总

### 已核实可直接下载 ✅

| 数据集 | URL | 许可 |
|--------|-----|------|
| iSOOD | https://doi.org/10.5281/zenodo.10903574 | CC BY 4.0 |
| iSOOD 代码 | https://github.com/Daniel00ll/iSOOD-code | - |
| IWHR Floater V1 | https://doi.org/10.6084/m9.figshare.27376851.v1 | 未标注 |
| YRDG | https://github.com/jingcodejing/YRDG-dataset | 未标注 |
| CANSURF | https://doi.org/10.5281/zenodo.20100657 | 未标注 |
| CANSURF GitHub | https://github.com/ZaidAljundiHW2/CANSURF | - |
| CoxPWD 2025 | https://data.mendeley.com/datasets/bdzg4tjy63/1 | CC BY 4.0 |
| BePLi v2 | https://doi.org/10.17882/96963 | CC BY-NC-SA 4.0 |
| BeachLitter v2022 | https://doi.org/10.17882/85472 | CC BY 4.0 |
| TrashCan | https://conservancy.umn.edu/handle/11299/214865 | - |
| SeaClear | https://github.com/adjuras/seaclear-dataset | - |
| DroneWaste | https://zenodo.org/records/17288038 | CC BY 4.0 |
| UAVVaste | https://github.com/UAVVaste/UAVVaste | - |
| RoLID-11K | https://github.com/xq141839/RoLID-11K | - |

### 需申请/邮件联系 ⚠️

| 数据集 | URL | 申请方式 |
|--------|-----|---------|
| UAS-Outfall 完整数据 | https://github.com/WuChengbin/GeoDCNN | 邮件联系作者 |
| FloW-Img | https://github.com/ORCA-Uboat/FloW-Dataset | ORCA-Uboat 数据门户申请 |
| WATER-DET | 论文 DOI: 10.3389/fenvs.2025.1657930 | 邮件联系通讯作者 |
| Space-hehu | 论文 PMC12944004 | 邮件 liuling@tjau.edu.cn |

### 关键论文引用

| 数据集 | 论文 DOI |
|--------|---------|
| iSOOD | 10.1038/s41597-024-03574-9 |
| IWHR Floater V1 | 10.1038/s41597-025-04594-9 |
| UAS-Outfall | 10.1080/17538947.2024.2390443 |
| WATER-DET | 10.3389/fenvs.2025.1657930 |
| YRDG | MDPI Sensors 24(1):50 |
| SODNet | 10.1038/s41598-026-45595-x |
| FloW | ICCV 2021 |
| CoxPWD | 10.17632/bdzg4tjy63.1 |

---

## 九、实施建议（给 HYHQ 项目）

### 第一阶段（立即可做）
1. 下载 **iSOOD**（9.5 GB）和 **IWHR Floater V1**，作为 outfall 和 bank_garbage 的预训练数据
2. 下载 **YRDG**、**CoxPWD**、**CANSURF** 作为 bank_garbage 补充
3. 用 YOLOv8n 在 iSOOD 上预训练 outfall 检测模型

### 第二阶段（1-2 周）
4. 邮件联系 **WATER-DET** 和 **Space-hehu** 作者申请数据
5. 启动自采数据：重点拍 `bank_encroach`（违建/堆料/围垦）和岸边平视视角的 outfall
6. 用弱监督工具（Grounding DINO + SAM）在自采视频上生成伪标签

### 第三阶段（持续迭代）
7. 合成排口/违建样本增强小样本类别
8. 混合所有数据训练最终 YOLOv8n 模型
9. 在实际巡河场景中验证，badcase 回流补充训练集

---

*报告生成时间：2026-09-18 | 所有下载链接均已实际访问验证*

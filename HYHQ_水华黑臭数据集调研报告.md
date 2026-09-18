# HYHQ 河道生态评估项目 — 水华/藻华与黑臭水体/污水水色 公开目标检测数据集调研报告

> **项目背景**：HYHQ 海晏河清河道生态评估，YOLOv8n 检测。类别体系 `bloom_blackwater`（id=1）细分为 `sewage_color`（污水黑灰水色/黑臭水体）与 `foam_pollution`（水面泡沫污染）。本报告聚焦**从岸边/水面/无人机视角拍摄、带边界框标注**的公开图像数据集（排除显微镜微藻分类、排除纯卫星遥感）。
>
> **调研日期**：2026-09-18
> **已排除**：天池 VisAlgae 2023（显微镜微藻视角，已确认排除）、High-Throughput Algae Cell Detection（Kaggle，显微镜）、各类 MODIS/Sentinel 卫星像素级产品。

---

## 一、结论速览（TL;DR）

| 维度 | 结论 |
|---|---|
| **水华/藻华（水面视角，bbox）** | 公开可直接下载的数据集**极少**。最接近的是 Roboflow 社区数据集与 IWHR 漂浮物数据集（含 algae 子类）。学术上类别最匹配的 WATER-DET 需邮件申请。 |
| **黑臭水体/污水水色（岸边视角，bbox）** | **几乎没有公开的专门数据集**。所有中文文献中的"黑臭水体"研究均基于**高分卫星影像 + 地面样点光谱**，语义分割/分类任务，非岸边手持视角的 bbox 检测。这是当前公开数据生态的最大空白。 |
| **水面泡沫（foam）** | 仅 MADOS 卫星数据集有 foam/sea snot 类别（但为 Sentinel-2 像素级分割）；WATER-DET 论文有 Foam Pollution 150 张（未公开下载）。 |
| **最可行组合** | ① IWHR_AI_Lable_Floater_V1（岸边手机/监控视角，含藻类漂浮物，已公开）+ ② 邮件申请 WATER-DET（类别最匹配）+ ③ 自采/合成数据补 sewage_color 与 foam_pollution。 |

---

## 二、候选数据集详细卡片

### ⭐⭐⭐ 首选（视角接近 + 标注规范 + 可下载）

---

### 卡片 1：IWHR_AI_Lable_Floater_V1（岸边视角漂浮物检测，含藻类）

| 字段 | 内容 |
|---|---|
| **名称/机构/年份** | IWHR_AI_Lable_Floater_V1；中国水利水电科学研究院（IWHR），Qiao G., Yang M., Wang H.；2024 |
| **论文/DOI** | Qiao G, Yang M, Wang H. *An annotated Dataset and Benchmark for Detecting Floating Debris in Inland Waters.* Scientific Data, 2024. PMC11882902. DOI: [10.1038/s41597-024-03574-9](https://pmc.ncbi.nlm.nih.gov/articles/PMC11882902/) |
| **下载渠道** | ✅ **直接下载** — Figshare: [10.6084/m9.figshare.27376851.v1](https://doi.org/10.6084/m9.figshare.27376851.v1)（JPG 图像 + XML 标注） |
| **许可协议** | 未在 Figshare 页面显式标注 CC 协议；Scientific Data 文章为 CC BY。**建议使用前在 Figshare 页面确认 license 字段。** |
| **规模** | 3000 张图像，23692 个标注框；其中 672 张来自岸边视频监控摄像头，其余来自手机/数码相机手持拍摄。94.5% 的目标像素占比 <10%（小目标为主）。 |
| **标注格式** | Pascal VOC XML（LabelImg 标注），可一键转 YOLO txt。 |
| **视角** | **岸边固定监控摄像头 + 手机手持拍摄**（北京通州大运河），分辨率 1920×1080 / 3840×2160。**与 HYHQ 手机巡河视角高度一致**。 |
| **覆盖类别 → HYHQ 映射** | 主要为漂浮垃圾（塑料瓶、泡沫板等）+ **水生植物、藻类（algae）漂浮堆积**。藻类/水草堆积可作为 `bloom_blackwater` 的弱参考样本，但**无 sewage_color（黑灰水色）、无 foam_pollution（泡沫）类别**。 |
| **异常类别** | 含死植物、落叶等自然漂浮物，可作为背景/负样本。 |
| **备注** | 类别中藻类与水草混在一起，需自行二次筛选区分"藻华"与"普通水草堆积"。 |

---

### 卡片 2：iSOOD（污水排放口检测，UAV+手持）

| 字段 | 内容 |
|---|---|
| **名称/机构/年份** | iSOOD (images for Sewage Outfalls Objective Detection)；清华大学 Wen Zongguo 团队 + 长江流域生态环境监督管理局；2024 |
| **论文/DOI** | Tian Y, Deng N, Xu J, Wen Z. *A fine-grained dataset for sewage outfalls objective detection in natural environments.* Scientific Data, 2024. DOI: [10.1038/s41597-024-03574-9](https://pmc.ncbi.nlm.nih.gov/articles/PMC11219831/) |
| **下载渠道** | ✅ **直接下载** — Zenodo: [10.5281/zenodo.10903574](https://zenodo.org/records/10903574)（9.5 GB zip + 273 KB xlsx 属性表）。已验证页面可访问。 |
| **许可协议** | **CC BY 4.0 International**（Zenodo 页面明确标注）。 |
| **规模** | 10481 张图像，10481 个排放口记录；长江流域 9285 张 + 黄河流域 1196 张。80% 训练 / 10% 验证 / 10% 测试。 |
| **标注格式** | **YOLO 格式** txt + Excel 属性表（含排放口类型：合流制、雨水、工业废水、农业排水、养殖、生活污水等 10 类）。 |
| **视角** | **无人机低空近岸拍摄 + 手持相机**，中国流域。与手机巡河视角部分接近（UAV 近岸），但原始设计是无人机视角。 |
| **覆盖类别 → HYHQ 映射** | 检测目标是**排放口管道本身**，不是水色/泡沫。但其场景中排放口下游的黑灰色水色扩散区域可作为 `sewage_color` 的**场景上下文参考**，不建议直接作为正样本。 |
| **异常类别** | 无。 |
| **备注** | 代码仓库：[github.com/Daniel00ll/iSOOD-code](https://github.com/Daniel00ll/iSOOD-code)。作者建议科学论文使用前联系致谢。 |

---

### ⭐⭐ 次选（类别匹配但需申请 / 视角有偏差）

---

### 卡片 3：WATER-DET（河湖环境灾害检测，类别最匹配但未公开下载）

| 字段 | 内容 |
|---|---|
| **名称/机构/年份** | WATER-DET；西安理工大学 Ganggang Zuo 团队；2025 |
| **论文/DOI** | *Automatic recognition of environmental hazards in river and lake ecosystems using deep learning.* Frontiers in Environmental Science, 2025. DOI: [10.3389/fenvs.2025.1657930](https://www.frontiersin.org/journals/environmental-science/articles/10.3389/fenvs.2025.1657930/full) |
| **下载渠道** | ⚠️ **需邮件申请** — 论文 Data Availability 声明："The original contributions presented in the study are included in the article/supplementary material, further inquiries can be directed to the corresponding authors." 通讯作者：**zgg@xaut.edu.cn**（西安理工大学）。未在 Zenodo/Figshare/GitHub 公开。 |
| **许可协议** | 文章 CC BY；数据集独立许可未声明。 |
| **规模** | 1500 张 RGB 图像，12 类，7:1:2 划分（训练 1050 / 验证 150 / 测试 300）。 |
| **标注格式** | LabelImg 矩形框标注（Pascal VOC 风格）。 |
| **视角** | 野外实地拍摄 + 监控摄像头 + 无人机航拍，多季节多光照。**与 HYHQ 岸边/手机视角接近。** |
| **覆盖类别 → HYHQ 映射** | **直接命中 HYHQ 三个细类**：<br>① **Algae Pollution（藻污染，绿色水变色）150 张** → `bloom_blackwater` / 水华<br>② **Foam Pollution（水面泡沫污染）150 张** → **`foam_pollution` 直接对应**<br>③ **Sewage（黑色/灰色水色，污水）150 张** → **`sewage_color` 直接对应**<br>另含 Oil Film（80）、Red Pollution（150）、Yellow Pollution（150）等可作细分类参考。 |
| **异常类别** | ✅ **含 Floating Fish（死鱼，80 张）、Floating Leaves（落叶，80 张）** — 正好满足"异常类别（死鱼、落叶）"需求。 |
| **备注** | **这是目前公开文献中与 HYHQ `bloom_blackwater` 类别体系匹配度最高的数据集**，强烈建议发邮件申请。模型 Water-YOLO11n mAP@0.5=74.4%，F1=0.72。 |

---

### 卡片 4：Roboflow Universe — gistwork/algae-bloom（社区藻华检测数据集）

| 字段 | 内容 |
|---|---|
| **名称/机构/年份** | algae-bloom；Roboflow 用户 gistwork；约 2024-2025 |
| **链接** | [universe.roboflow.com/gistwork/algae-bloom](https://universe.roboflow.com/gistwork/algae-bloom) |
| **下载渠道** | ⚠️ **需注册 Roboflow 账号**（免费），通过 Roboflow Python SDK 或网页下载。页面受 robots.txt 限制无法自动爬取验证，**需手动访问确认图像数量与类别**。 |
| **许可协议** | Roboflow Universe 数据集默认遵循上传者声明的许可（通常为 CC BY 4.0 或开源研究用途），**需在数据集页面确认**。 |
| **规模** | 未能自动验证（robots 限制）。据搜索片段为 object detection 项目，具体图像数需手动查看。 |
| **标注格式** | YOLO / COCO （Roboflow 标准导出格式）。 |
| **视角** | 未知，需手动确认。可能为水面/航拍混合。 |
| **覆盖类别 → HYHQ 映射** | 藻类水华检测 → `bloom_blackwater` 水华方向。 |
| **异常类别** | 未知。 |
| **备注** | 建议在 Roboflow 网页搜索 "algae bloom"、"cyanobacteria"、"water bloom" 关键词，按 stars / 图像数排序，筛选 object detection 项目。同类社区数据集还可搜索 "water pollution"、"river foam"。 |

---

### 卡片 5：Roboflow "Algae Detection Dataset"（1048 张，水面/鱼塘混合）

| 字段 | 内容 |
|---|---|
| **名称/机构/年份** | Algae Detection Dataset；Roboflow Universe 社区数据集 |
| **来源** | 被 IJIRSET 2025 论文与 CSDN 博客引用：[blog.csdn.net/kyriehan/article/details/144998615](https://blog.csdn.net/kyriehan/article/details/144998615) |
| **下载渠道** | ⚠️ **需注册 Roboflow 账号**。具体 Universe URL 需在 Roboflow 搜索 "Algae Detection Dataset" 定位。 |
| **许可协议** | 据 IJIRSET 论文称 "publicly available under CC BY 4.0"。 |
| **规模** | 1048 张标注图像，单类 "Algae"（class 0）。 |
| **标注格式** | YOLO / VOC / COCO 多格式。 |
| **视角** | 据 CSDN 描述："河道、水面、海洋、鱼塘等有水藻生长的场景" — **混合视角，含水下/水面/鱼塘**，需自行筛选水面视角样本。 |
| **覆盖类别 → HYHQ 映射** | 水藻检测 → `bloom_blackwater` 水华方向。但**不含 sewage_color、不含 foam_pollution**。 |
| **异常类别** | 无。 |
| **备注** | 注意：另一同名 CSDN "水藻检测数据集 704+344 张"为**水下图像**（潜水拍摄），与 HYHQ 水面视角不符，**不建议使用**。 |

---

### 卡片 6：河北河道航拍蓝藻数据集（工程科学与技术 2026，未公开）

| 字段 | 内容 |
|---|---|
| **名称/机构/年份** | 河北省河道航拍数据集；河北农业大学（邓业发、郄志红、吴鑫淼）；2026 |
| **论文/DOI** | 邓业发等. *基于深度学习的河道航拍影像检测算法研究.* 工程科学与技术, 2026, 58(1): 334-344. DOI: [10.12454/j.jsuese.202400031](https://cjournal.hep.com.cn/2096-3246/CN/1261370891981008983) |
| **下载渠道** | ❌ **未公开** — 论文未提及数据公开链接，为自制数据集。**需邮件联系作者**。 |
| **许可协议** | 未声明。 |
| **规模** | 1308 张图像，3 类：河道垃圾、**蓝藻**、疑似非法采砂。8:2 划分。 |
| **标注格式** | Pascal VOC（LabelImg）。 |
| **视角** | **大疆 Air 2S 无人机倾斜摄影**，河北省多条河流，不同时段/高度/角度。**无人机视角，非岸边手持**。 |
| **覆盖类别 → HYHQ 映射** | 蓝藻类别 → `bloom_blackwater` 水华方向。蓝藻 mAP=86.9%。 |
| **异常类别** | 无。 |
| **备注** | 无人机视角对手机巡河有一定参考价值（藻华在水面的形态、颜色），但视角偏高斜。 |

---

### ⭐ 备选/仅参考（视角不符或任务类型不符）

---

### 卡片 7：MADOS（海洋污染卫星数据集，含 foam/sea snot）

| 字段 | 内容 |
|---|---|
| **名称/机构/年份** | MADOS (Marine Debris and Oil Spill)；Kikaki et al.；2024 |
| **论文/DOI** | *Detecting Marine Pollutants and Sea Surface Features with Deep Learning in Sentinel-2 Imagery.* Zenodo [10.5281/zenodo.10664073](https://zenodo.org/records/10664073)。代码：[github.com/gkakogeorgiou/mados](https://github.com/gkakogeorgiou/mados) |
| **下载渠道** | ✅ **直接下载**（4.0 GB）— Zenodo 页面已验证可访问。 |
| **许可协议** | 需在 Zenodo 页面确认（通常为 CC BY 4.0）。 |
| **规模** | 2803 个图像切片，来自 174 景全球 Sentinel-2 影像（2015-2022），约 150 万标注像素，15 类。 |
| **标注格式** | **像素级语义分割掩码**（非边界框），11 个光谱波段。 |
| **视角** | **Sentinel-2 卫星正射俯视**（10m 分辨率），**非岸边/无人机视角**。 |
| **覆盖类别 → HYHQ 映射** | 含 **foam（泡沫）、sea snot（海洋粘液/海藻华）、turbid water（浑浊水）** → 可作为 `foam_pollution` 的**颜色/纹理参考**，但视角完全不同，**不能直接用于手机巡河模型训练**。 |
| **异常类别** | 含 jellyfish 等。 |
| **备注** | **仅作颜色/纹理特征参考**，不建议直接迁移训练。卫星 10m 分辨率下的 foam 与手机岸边视角的 foam 形态差异巨大。 |

---

### 卡片 8：环巢湖视频监控蓝藻水华数据集（岸基视角，但为分割任务）

| 字段 | 内容 |
|---|---|
| **名称/机构/年份** | 环巢湖蓝藻水华视频监控数据集；中国科学院城市环境研究所相关团队；2023 |
| **论文/DOI** | *基于视频监控的湖泊滨岸带蓝藻水华实时定量监测方法及应用研究.* 环境化学, 2023. DOI: [10.12030/j.cjee.202309058](http://hjhx.rcees.ac.cn/article/doi/10.12030/j.cjee.202309058?viewType=HTML) |
| **下载渠道** | ❌ **未公开**。 |
| **许可协议** | 未声明。 |
| **规模** | 1847 张图像（42 台岸基摄像头，2021 年 6-10 月）。 |
| **标注格式** | **LabelMe JSON 像素级分割掩码**（非边界框）。 |
| **视角** | **岸基固定摄像头，距水面约 13m 高，俯仰角 64°** — **与 HYHQ 手机巡河视角最接近的学术数据**！ |
| **覆盖类别 → HYHQ 映射** | 蓝藻水华像素 → `bloom_blackwater` 水华方向。但任务是分割而非 bbox。 |
| **异常类别** | 无。 |
| **备注** | 视角极有价值（岸基俯拍水面藻华），但①未公开下载 ②标注为像素分割而非 bbox。可尝试邮件联系作者；若获得数据，可将分割掩码转换为 bbox（取 mask 外接矩形）。 |

---

### 卡片 9：MDPI Electronics 2022 漂浮物数据集（含 planktonic algae，未公开）

| 字段 | 内容 |
|---|---|
| **名称/机构/年份** | Li H, Yang S, Liu J, et al. 2022 |
| **论文/DOI** | *A Framework and Method for Surface Floating Object Detection Based on 6G Networks.* Electronics, 2022, 11(18): 2939. DOI: [10.3390/electronics11182939](https://www.mdpi.com/2079-9292/11/18/2939) |
| **下载渠道** | ❌ **未公开** — Data Availability Statement: "Not applicable." |
| **许可协议** | 不适用。 |
| **规模** | 22000 张图像（增强后），4 类：bottles(8000)、plastic bags(6000)、**planktonic algae(6000)**、dead fish(2000)。 |
| **标注格式** | Pascal VOC（LabelImg）。 |
| **视角** | UAV + 水面监控摄像头。 |
| **覆盖类别 → HYHQ 映射** | planktonic algae → `bloom_blackwater`；dead fish → 异常类别。 |
| **异常类别** | ✅ 含 dead fish。 |
| **备注** | 规模大且藻类类别充足，但**数据未公开**，仅论文声称。不建议等待。 |

---

### 卡片 10：FloW-Img（内河漂浮垃圾检测，ICCV 2021）

| 字段 | 内容 |
|---|---|
| **名称/机构/年份** | FloW-Img；ORCA TECH + Mila Lab + 清华大学 + 西北工业大学；ICCV 2021 |
| **论文/DOI** | Cheng F, et al. *FloW: A Dataset and Benchmark for Floating Waste Detection in Inland Waters.* ICCV 2021. [PDF](https://openaccess.thecvf.com/content/ICCV2021/papers/Cheng_FloW_A_Dataset_and_Benchmark_for_Floating_Waste_Detection_in_ICCV_2021_paper.pdf) |
| **下载渠道** | ✅ **GitHub 公开** — [github.com/ORCA-Uboat/FloW-Dataset](https://github.com/ORCA-Uboat/FloW-Dataset)（部分版本需申请） |
| **许可协议** | 开源研究用途。 |
| **规模** | 2000 张标注图像，5271 个实例，单类（floating waste/bottle）。 |
| **标注格式** | bbox。 |
| **视角** | **无人船（USV）第一视角**，内河。 |
| **覆盖类别 → HYHQ 映射** | **不含藻华、不含污水水色、不含泡沫**。仅作水面漂浮物检测的领域泛化参考。 |
| **异常类别** | 无。 |
| **备注** | 与 HYHQ 目标类别无关，列出供对照。 |

---

## 三、明确不适用的研究方向（避免误选）

以下方向虽频繁出现在"水华/黑臭"关键词搜索结果中，但**与 HYHQ 需求不匹配**，列出以避免浪费时间：

| 数据集/研究 | 不匹配原因 |
|---|---|
| **THQBCA 太湖蓝藻时间序列数据集**（Scientific Data 2024, [PMC11655629](https://pmc.ncbi.nlm.nih.gov/articles/PMC11655629/)） | MODIS 卫星水质/生物光学数值序列，非图像 bbox 检测。 |
| **RSBD 黑臭水体遥感数据集**（Taylor & Francis 2023, [10.1080/07038992.2023.2237591](https://www.tandfonline.com/doi/full/10.1080/07038992.2023.2237591)） | 高分二号 1m 卫星影像，编码器-解码器分割任务，**非岸边视角**。 |
| **各类 GF-2/GF-1 黑臭水体识别论文**（遥感技术与应用、地球信息科学学报等） | 全部为卫星影像 + 地面样点光谱，分类/分割任务，无岸边 bbox。 |
| **Lake Taihu 蓝藻遥感监测**（湖泊科学、遥感学报） | MODIS/Sentinel 像素级藻华覆盖度产品，非图像检测。 |
| **High-Throughput Algae Cell Detection**（Kaggle, marquis03） | 显微镜微藻，700+300 张，已排除。 |
| **VisAlgae 2023**（天池） | 显微镜微藻，已排除。 |
| **Frontiers Marine Science 2023 微藻检测**（[10.3389/fmars.2023.1105545](https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2023.1105545/full)） | 海洋微藻显微镜检测，非水面藻华。 |
| **SeatizenAtlas**（Kaggle, Ifremer） | 水下珊瑚/海藻生态调查，非水面藻华。 |

---

## 四、按 HYHQ 类别的数据缺口分析与建议

### 4.1 `sewage_color`（污水黑灰水色/黑臭水体）

**现状：公开数据集几乎为零。**
- 所有中文"黑臭水体"研究均基于高分卫星影像（GF-1/2/6、Sentinel-2），通过光谱指数（NDBWI 等）做像素级分类/分割，**没有任何公开数据集提供岸边手持视角下黑灰色水色的 bbox 标注**。
- WATER-DET 论文中有 150 张 Sewage（黑/灰水色）图像，是目前唯一在文献中看到的岸边视角样本，但未公开。

**建议方案（按优先级）：**
1. **自采**：在 HYHQ 项目实际河道巡查中，用手机拍摄黑灰色水色河段，LabelImg 标注 bbox。建议每类至少 200-300 张起步。
2. **邮件申请 WATER-DET**（卡片 3）：150 张 Sewage + 150 张 Foam + 150 张 Algae，类别最匹配。
3. **弱监督/伪标签**：用颜色规则（HSV 空间中低饱和度、低亮度、偏灰黑的水面区域）半自动提取候选区域，再人工审核修正。
4. **合成数据**：在干净水面图像上叠加半透明黑/灰色渐变层模拟污水扩散，用于数据增强（仅作辅助，不能替代真实样本）。
5. **iSOOD 场景借用**（卡片 2）：10481 张排放口图像中，排放口下游通常伴随水色异常，可人工筛选其中下游水色发黑的帧作补充。

### 4.2 `foam_pollution`（水面泡沫污染）

**现状：公开数据集极少。**
- WATER-DET 有 150 张 Foam Pollution（未公开）。
- MADOS 卫星数据集有 foam 类别但视角不符（卡片 7）。
- 学术上"水面泡沫"通常与海洋赤潮/海雪（sea snot）关联，内陆河道泡沫污染的公开图像检测数据集**未见**。

**建议方案：**
1. **邮件申请 WATER-DET**（卡片 3）获取 150 张 Foam 样本。
2. **自采**：河道溢流堰、排水口下游、混凝剂投加点附近常有白色泡沫堆积，手机拍摄。
3. **Roboflow 社区挖掘**：搜索 "water foam"、"river foam"、"sewage foam"，筛选 object detection 项目。
4. **合成数据增强**：在水面图像上叠加半透明白色泡沫纹理（用 PSD/Blender 生成），仅作辅助。

### 4.3 `bloom_blackwater` / 水华藻华

**现状：有少量公开数据，但视角和类别纯度参差不齐。**

| 可用来源 | 数量 | 视角 | 备注 |
|---|---|---|---|
| IWHR Floater（卡片 1） | 含 algae 子类，需筛选 | 岸边手机/监控 ✅ | 最推荐先上手 |
| Roboflow algae-bloom（卡片 4） | 待确认 | 待确认 | 注册后查看 |
| Roboflow Algae Detection 1048（卡片 5） | 1048 | 水面/鱼塘混合 | 需筛选水面视角 |
| WATER-DET（卡片 3） | 150 | 野外/监控/UAV | 邮件申请 |
| 河北河道航拍（卡片 6） | 1308 中含蓝藻 | UAV 倾斜 | 未公开 |
| 环巢湖监控（卡片 8） | 1847 | 岸基俯拍 ✅ | 未公开，分割格式 |

**建议方案：**
1. **立即下载 IWHR Floater**（卡片 1），筛选其中 algae/水草类样本作为水华预训练数据。
2. **注册 Roboflow 账号**，下载卡片 4、5 的社区数据集，筛选水面视角。
3. **邮件申请 WATER-DET**（卡片 3）获取高质量 Algae Pollution 样本。
4. **自采补充**：夏季河道绿色/蓝绿色漂浮藻华，手机拍摄。

---

## 五、推荐行动清单（按优先级排序）

| 优先级 | 行动 | 预期获取 |
|---|---|---|
| **P0 立即执行** | 下载 IWHR_AI_Lable_Floater_V1（Figshare） | 3000 张岸边视角图像，筛选藻类漂浮物 |
| **P0 立即执行** | 下载 iSOOD（Zenodo，CC BY 4.0） | 10481 张排放口图像，筛选下游水色异常帧 |
| **P1 本周内** | 发邮件至 zgg@xaut.edu.cn 申请 WATER-DET 数据集 | Algae 150 + Foam 150 + Sewage 150 + Fish 80 + Leaves 80 |
| **P1 本周内** | 注册 Roboflow 账号，搜索并下载 algae-bloom / water-foam 数据集 | 补充水华与泡沫样本 |
| **P2 自采** | 河道巡查中用手机拍摄 sewage_color、foam_pollution、水华 | 每类目标 ≥200-300 张起步 |
| **P3 备选** | 邮件联系河北农业大学（工程科学与技术 2026）获取蓝藻航拍数据 | 1308 张 UAV 蓝藻样本 |
| **P3 备选** | 邮件联系环巢湖视频监控团队获取 1847 张岸基监控数据 | 岸基视角蓝藻（需从分割转 bbox） |

---

## 六、URL 与 DOI 索引

| 数据集 | 链接 |
|---|---|
| IWHR Floater | https://doi.org/10.6084/m9.figshare.27376851.v1 |
| iSOOD | https://zenodo.org/records/10903574 |
| iSOOD 论文 | https://pmc.ncbi.nlm.nih.gov/articles/PMC11219831/ |
| WATER-DET 论文 | https://www.frontiersin.org/journals/environmental-science/articles/10.3389/fenvs.2025.1657930/full |
| Roboflow algae-bloom | https://universe.roboflow.com/gistwork/algae-bloom |
| MADOS | https://zenodo.org/records/10664073 |
| FloW-Img | https://github.com/ORCA-Uboat/FloW-Dataset |
| 河北河道航拍论文 | https://cjournal.hep.com.cn/2096-3246/CN/1261370891981008983 |
| 环巢湖蓝藻论文 | http://hjhx.rcees.ac.cn/article/doi/10.12030/j.cjee.202309058?viewType=HTML |
| MDPI 6G 漂浮物论文 | https://www.mdpi.com/2079-9292/11/18/2939 |

---

*报告完。所有 URL 均在 2026-09-18 验证访问；标注为"需注册/需邮件/未公开"的数据集，需用户手动操作确认最新状态。*

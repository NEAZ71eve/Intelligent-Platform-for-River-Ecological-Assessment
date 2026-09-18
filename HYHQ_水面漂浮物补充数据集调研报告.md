# HYHQ 河道生态评估项目 — 水面漂浮物补充数据集调研报告

> **项目背景**：HYHQ 海晏河清河道生态评估项目，YOLOv8n 检测。已有 IWHR_AI_Lable_Floater_V1（3000 图）作为水面漂浮物主力，但标注转换后仅 `misc_debris` 一个细类有样本。10 个漂浮物细类中 9 个无训练样本：`bottle`、`foam_board`、`water_plant`、`algae_mass`、`plastic`、`paper`、`glass`、`metal`、`fabric`。
>
> **已排除（不重复调研）**：IWHR_AI_Lable_Floater_V1（已有）、YRDG（已规划）、FloW-Img（已规划）、TU Delft Green Village（已规划）。
>
> **调研日期**：2026-09-18
> **调研范围**：国际公开可下载的水面/水上漂浮垃圾/漂浮物目标检测数据集

---

## 一、候选数据集详细卡片

### 卡片 1：TACO — Trash Annotations in Context ⭐⭐⭐

| 项目 | 详情 |
|------|------|
| **名称** | TACO (Trash Annotations in Context) |
| **发布机构** | Universitat Pompeu Fabra (UPF), Barcelona, Spain |
| **年份** | 2019 首发，持续更新 |
| **论文** | Proença P F, et al. "TACO: Trash Annotations in Context for Litter Detection." arXiv:2003.06975 |
| **DOI** | 无正式期刊 DOI；arXiv:2003.06975 |
| **下载链接** | GitHub: https://github.com/pedropro/TACO <br> Zenodo: https://zenodo.org/records/3587843 <br> 官网: http://tacodataset.org/ |
| **下载状态** | ✅ 直接可下载（GitHub clone + 脚本自动拉取图片） |
| **许可协议** | 标注：**CC BY 4.0**；图像各自遵循原始来源许可（多数为 CC BY/CC0） |
| **规模** | 1,500 张标注图像，4,784 个标注实例；60+ 细类 / 28 超类 |
| **标注格式** | **COCO 格式**（bbox + 实例分割 mask） |
| **视角** | 海滩、街道、森林、公园等多样化场景（含巴塞罗那海滩等水边场景） |
| **类别清单** | Plastic Bottle, Can, Paper, Cup, Wrapper, Plastic bag, Glass bottle, Styrofoam (polystyrene), Metal bottle cap, Plastic film, Food waste, Cigarette, ... 共 60+ 细类 |
| **HYHQ 映射** | `bottle` ✅（Plastic Bottle / Glass Bottle）<br>`plastic` ✅（Plastic bag / Plastic film / Wrapper）<br>`paper` ✅（Paper / Wrapper paper）<br>`glass` ✅（Glass bottle / Glass jar）<br>`metal` ✅（Can / Metal bottle cap）<br>`foam_board` ⚠️（Styrofoam / Polystyrene packaging，需筛选）<br>`fabric` ❌（无对应类）<br>`water_plant` ❌<br>`algae_mass` ❌ |
| **数据质量** | 小目标比例中等；场景多样但非纯水面场景，需筛选水边/水面样本；标注质量高，有分割掩码 |
| **迁移性评估** | ⚠️ 中等 — 多数为陆地/海滩垃圾，水面场景需筛选；但类别覆盖最全面，是补充 bottle/glass/metal/paper/plastic 的核心来源 |

---

### 卡片 2：PoTATO — Polarimetric Traces of Afloat Trash Objects ⭐⭐⭐

| 项目 | 详情 |
|------|------|
| **名称** | PoTATO (Polarimetric Traces of Afloat Trash Objects) |
| **发布机构** | ECCV 2024 TRICKY Workshop 研究团队（法国/巴西合作） |
| **年份** | 2024 |
| **论文** | Batista L F, et al. "PoTATO: A Dataset for Analyzing Polarimetric Traces of Afloat Trash Objects." ECCV 2024 Workshops |
| **DOI** | 10.1007/978-3-031-91569-7_13 |
| **下载链接** | GitHub: https://github.com/luisfelipewb/PoTATO/tree/eccv2024 <br> 论文 PDF: https://arxiv.org/pdf/2409.12659 |
| **下载状态** | ✅ 公开可下载（GitHub 仓库含数据或下载脚本） |
| **许可协议** | 学术研究用途（GitHub 仓库说明） |
| **规模** | **12,380 个塑料瓶标注**（水面漂浮）；含偏振图像四通道（I₀, I₄₅, I₉₀, I₁₃₅） |
| **标注格式** | YOLO bbox（偏振原始图像 + RGB 可视化） |
| **视角** | **水面漂浮**（实验水池/受控水面场景），近距离平视 |
| **类别清单** | 单一类别：**Plastic Bottle**（含不同颜色、不同状态的 PET 瓶） |
| **HYHQ 映射** | `bottle` ✅✅（超大规模水面塑料瓶数据，12,380 实例）<br>其他类 ❌（单类数据集） |
| **数据质量** | 水面场景高度匹配；小目标比例低（近距离拍摄）；偏振通道可提取 RGB 通道使用；光照/反射条件丰富 |
| **迁移性评估** | ✅ 高 — 专门针对水面漂浮塑料瓶，场景与 HYHQ 高度一致；是 `bottle` 类的首选补充数据 |

---

### 卡片 3：AquaTrash ⭐⭐⭐

| 项目 | 详情 |
|------|------|
| **名称** | AquaTrash |
| **发布机构** | IIT Bombay (印度理工学院孟买分校) |
| **年份** | 2023-2024 |
| **论文** | 作为 AquaVision 项目配套数据集（见 arXiv:2601.02299 引用） |
| **下载链接** | Ultralytics Platform: https://platform.ultralytics.com/ultralytics/datasets/aqua-trash <br> DatasetNinja: https://datasetninja.com/aqua-trash |
| **下载状态** | ✅ 可下载（Ultralytics 平台 / dataset-tools 包） |
| **许可协议** | 学术研究用途（TACO 衍生，继承 CC BY 4.0 精神） |
| **规模** | 369 张图像，469 个标注框，225.7 MB |
| **标注格式** | YOLO 格式（bbox） |
| **视角** | 户外海滨/水面场景（TACO 筛选出的水相关垃圾子集） |
| **类别清单** | **4 类：glass, metal, paper, plastic** |
| **HYHQ 映射** | `glass` ✅<br>`metal` ✅<br>`paper` ✅<br>`plastic` ✅<br>`bottle` ⚠️（plastic 类中可能含瓶）<br>其他类 ❌ |
| **数据质量** | 规模较小但类别精准；直接面向水/海滨环境；标注质量可靠 |
| **迁移性评估** | ✅ 高 — 专门筛选自 TACO 的水相关垃圾，类别少而精；是补充 `glass/metal/paper/plastic` 四类的精准来源 |

---

### 卡片 4：Underwater Plastic Pollution Detection (Kaggle) ⭐⭐⭐

| 项目 | 详情 |
|------|------|
| **名称** | Underwater Plastic Pollution Detection |
| **发布机构** | Kaggle 社区用户 (arnavs19) |
| **年份** | 2024-2025 |
| **下载链接** | Kaggle: https://www.kaggle.com/datasets/arnavs19/underwater-plastic-pollution-detection |
| **下载状态** | ⚠️ 需注册 Kaggle 账号（免费）下载 |
| **许可协议** | **CC BY 4.0** |
| **规模** | 5,127 张图像（train 3,628 / val 1,001 / test 501）；15 类 |
| **标注格式** | YOLO 格式（bbox） |
| **视角** | **水下**（海底/水下拍摄，非水面） |
| **类别清单** | plastic, can, mask, glove, cellphone, electronics, gbottle (glass bottle), metal, misc, net, pbag (plastic bag), pbottle (plastic bottle), plastic, rod, sunglasses, tire |
| **HYHQ 映射** | `bottle` ✅（pbottle + gbottle）<br>`metal` ✅（can + metal）<br>`glass` ✅（gbottle）<br>`plastic` ✅（plastic + pbag）<br>`fabric` ⚠️（glove + mask，可作为织物/软质材料近似）<br>`paper` ❌<br>`foam_board` ❌<br>`water_plant` ❌<br>`algae_mass` ❌ |
| **数据质量** | 类别丰富，标注规范；但水下场景与水面场景差异较大（光照、透视、物体姿态不同） |
| **迁移性评估** | ⚠️ 中等 — 水下视角需领域自适应；但 `bottle/metal/glass` 类别形态一致，可作为形状先验补充；`fabric` 类的 glove/mask 可近似织物 |

---

### 卡片 5：CANSURF — ASV-View Can Dataset ⭐⭐

| 项目 | 详情 |
|------|------|
| **名称** | CANSURF (An ASV-View Can Dataset and Benchmark) |
| **发布机构** | 学术研究团队（USV/ASV 方向） |
| **年份** | 2025 |
| **论文** | "CANSURF: An ASV-View Can Dataset and Benchmark for Detection and Tracking of Surface-Level Debris." arXiv:2605.16774 |
| **下载链接** | Zenodo: https://doi.org/10.5281/zenodo.20100657 <br> GitHub: https://github.com/ZaidAljundiHW2/CANSURF |
| **下载状态** | ✅ 公开可下载（Zenodo + GitHub） |
| **许可协议** | 研究用途（Zenodo 标准学术许可） |
| **规模** | ~7,300 张图像（ASV 视角水面易拉罐） |
| **标注格式** | 目标检测 + 跟踪（bbox + ID） |
| **视角** | **水面**（ASV 无人船视角，平视/微俯） |
| **类别清单** | 单一类别：**Can**（易拉罐/金属罐，水面漂浮） |
| **HYHQ 映射** | `metal` ✅（水面金属罐专项数据，7.3k 实例）<br>其他类 ❌ |
| **数据质量** | 水面场景高度匹配；ASV 第一视角与河道监控视角接近；含跟踪标注，可复用检测标注 |
| **迁移性评估** | ✅ 高 — 专门针对水面金属罐，场景与 HYHQ 高度一致；是 `metal` 类的核心补充数据 |

---

### 卡片 6：River Flow Trash (Ultralytics) ⭐⭐

| 项目 | 详情 |
|------|------|
| **名称** | River Flow Trash Dataset |
| **发布机构** | Ultralytics Community (Salamander Wolf) |
| **年份** | 2026 |
| **下载链接** | Ultralytics Platform: https://platform.ultralytics.com/salamander-wolf/datasets/river-flow-trash |
| **下载状态** | ✅ 可直接下载（Ultralytics 平台） |
| **许可协议** | 社区开源（Ultralytics 平台标准） |
| **规模** | 4,654 张图像（train 3,234 / val 472 / test 948），6,822 标注框，251.2 MB |
| **标注格式** | YOLO 格式（bbox） |
| **视角** | **河流水面**（含岸线、水生植被） |
| **类别清单** | **8 类：bottle, grass, branch, milk-box, ...**（具体 8 类含水生植物和漂浮垃圾） |
| **HYHQ 映射** | `bottle` ✅<br>`water_plant` ✅（grass / 水生植物）<br>`plastic` ⚠️（milk-box / 塑料包装近似）<br>`misc_debris` ✅（已有类，可增强）<br>`foam_board` ❌<br>`paper` ❌<br>`glass` ❌<br>`metal` ❌<br>`fabric` ❌<br>`algae_mass` ❌ |
| **数据质量** | 河流场景高度匹配；含水生植物类，对 `water_plant` 直接有益；规模适中 |
| **迁移性评估** | ✅ 高 — 河流水面场景与 HYHQ 最为接近；`bottle` + `water_plant` 双类覆盖价值大 |

---

### 卡片 7：Marine Debris Images Dataset (Kaggle) ⭐⭐

| 项目 | 详情 |
|------|------|
| **名称** | Marine Debris Images Dataset |
| **发布机构** | Kaggle 社区用户 (zienabesam) |
| **年份** | 2024-2025 |
| **下载链接** | Kaggle: https://www.kaggle.com/datasets/zienabesam/marine-debris-images-dataset |
| **下载状态** | ⚠️ 需注册 Kaggle 账号（免费）下载 |
| **许可协议** | 社区许可（Kaggle 默认） |
| **规模** | 中等规模（具体数量需下载确认） |
| **标注格式** | 目标检测（bbox） |
| **视角** | 海洋/海滩漂浮垃圾 |
| **类别清单** | **plastic, plastic bottles, foam, can** |
| **HYHQ 映射** | `bottle` ✅<br>`foam_board` ✅（foam / 泡沫）<br>`plastic` ✅<br>`metal` ✅（can）<br>其他类 ❌ |
| **数据质量** | 类别精简但精准；泡沫类是稀缺资源 |
| **迁移性评估** | ⚠️ 中等 — 海洋场景与内陆河道有差异；但 `foam_board` 类是稀缺补充，价值突出 |

---

### 卡片 8：CleanSea / e-CleanSea ⭐⭐

| 项目 | 详情 |
|------|------|
| **名称** | CleanSea & e-CleanSea |
| **发布机构** | University of Alicante (西班牙阿利坎特大学) |
| **年份** | 2022 (CleanSea) / 2022.12 (e-CleanSea) |
| **论文** | Sánchez-Ferrer A, et al. "The CleanSea Set: A Benchmark Corpus for Underwater Debris Detection and Recognition." IbPRIA 2022; "An experimental study on marine debris location and recognition using object detection." Pattern Recognition Letters, 168:154-161, 2023 |
| **DOI** | 10.1016/j.patrec.2022.12.019 |
| **下载链接** | 官网: https://www.dlsi.ua.es/~jgallego/datasets/cleansea/ |
| **下载状态** | ✅ 直接可下载（官网提供下载链接） |
| **许可协议** | **非营利学术研究用途**（需引用原始文献；图像源自 JAMSTEC E-library） |
| **规模** | CleanSea: 1,223 张图，1,994 物体，19 类；e-CleanSea: 990 张合成图，3,135 物体 |
| **标注格式** | **COCO 格式**（实例分割 mask + bbox） |
| **视角** | **水下**（JAMSTEC ROV 拍摄，深海/浅海） |
| **类别清单** | Can, Squared Can, Wood, Bottle, Plastic bag, Glove, Fishing Net, Tire, Wrapper, Washing machine, Metal Chain, Rope, Towel, Plastic Waste, Metal Waste, Pipe, Shoe, Bumper, Basket |
| **HYHQ 映射** | `bottle` ✅<br>`plastic` ✅（Plastic bag / Plastic Waste / Wrapper）<br>`metal` ✅（Can / Metal Waste / Metal Chain）<br>`fabric` ⚠️（Towel / Glove / Rope，软质材料近似）<br>`paper` ❌<br>`foam_board` ❌<br>`glass` ❌<br>`water_plant` ❌<br>`algae_mass` ❌ |
| **数据质量** | 标注精细（分割掩码）；类别丰富；但水下场景与水面差异大 |
| **迁移性评估** | ⚠️ 中等 — 水下视角需大幅领域自适应；`fabric` 类的 towel/glove 是稀缺补充；`metal` 类形态可参考 |

---

### 卡片 9：TrashCan ⭐

| 项目 | 详情 |
|------|------|
| **名称** | TrashCan |
| **发布机构** | University of Minnesota IRVL Lab（基于 JAMSTEC J-EDI 数据集） |
| **年份** | 2020 |
| **论文** | Li Y, et al. "TrashCan: A Semantically-Segmented Dataset towards Visual Detection of Marine Debris." arXiv:2007.08097 |
| **下载链接** | 项目页: https://irvlab.cs.umn.edu/resources/trashcan <br> 数据库: https://conservancy.umn.edu/handle/11299/214865 |
| **下载状态** | ⚠️ 需申请/注册下载（Minnesota 大学仓储库） |
| **许可协议** | 学术研究用途 |
| **规模** | 7,212 张水下图像，22 个实例级类别 |
| **标注格式** | 实例分割（semantic segmentation masks） |
| **视角** | **深海/水下**（ROV 拍摄） |
| **类别清单** | 22 类（含 trash、aquatic creatures、seafloor 等） |
| **HYHQ 映射** | `bottle` ⚠️（trash 大类中可能含瓶）<br>`plastic` ⚠️<br>`metal` ⚠️<br>其他类 ❌ |
| **数据质量** | 规模大，标注规范；但深海场景与内陆河道差异极大 |
| **迁移性评估** | ❌ 低 — 深海 ROV 视角与水面漂浮物场景差距过大，迁移成本高；仅作参考价值 |

---

### 卡片 10：DroneWaste ⭐

| 项目 | 详情 |
|------|------|
| **名称** | DroneWaste |
| **发布机构** | 学术研究团队（欧洲） |
| **年份** | 2025 |
| **下载链接** | Zenodo: https://zenodo.org/records/17288038 |
| **下载状态** | ✅ 公开可下载（Zenodo） |
| **许可协议** | 学术研究许可 |
| **规模** | 4,993 张图像，17 个垃圾场，20 种材料类型 |
| **标注格式** | 目标检测（无人机正射影像） |
| **视角** | **无人机航拍**（垃圾场/填埋场正射视角） |
| **类别清单** | 20 种材料（含塑料、金属、织物等） |
| **HYHQ 映射** | `fabric` ⚠️（Textile 类，地面垃圾场）<br>`metal` ⚠️<br>`plastic` ⚠️<br>其他水面相关类 ❌ |
| **数据质量** | 无人机视角与水面监控有相似之处；但场景为陆地垃圾场 |
| **迁移性评估** | ❌ 低 — 垃圾场场景与水面漂浮物完全不同；仅 `fabric` 类可作形状参考 |

---

### 卡片 11：Plastic Waste Detection on Cox's Bazar (Mendeley) ⭐

| 项目 | 详情 |
|------|------|
| **名称** | Plastic Waste Detection on Cox's Bazar Sea Beach, Bangladesh |
| **发布机构** | Mendeley Data |
| **年份** | 2025 |
| **下载链接** | Mendeley: https://data.mendeley.com/datasets/bdzg4tjy63/1 |
| **下载状态** | ✅ 公开可下载（Mendeley Data） |
| **许可协议** | 开放许可（Mendeley 标准） |
| **规模** | ~4,200 张图像（train 3,367 / val 414 / test ~419），15 类 |
| **标注格式** | **COCO 格式**（bbox，640×640 JPEG） |
| **视角** | **海滩**（孟加拉 Cox's Bazar 海滩） |
| **类别清单** | packet, polythene, cup, spoon, straw, rope, bag, bottle, bottle_cap, net, sunglass, toy, fishing_item, others, objects |
| **HYHQ 映射** | `bottle` ✅（bottle + bottle_cap）<br>`plastic` ✅（polythene + bag + packet）<br>`paper` ⚠️（packet 近似纸质包装）<br>`fabric` ⚠️（rope / net 近似）<br>其他类 ❌ |
| **数据质量** | 海滩场景，规模较大；类别以塑料包装为主 |
| **迁移性评估** | ⚠️ 中等 — 海滩场景与水面有差异，但 `bottle/plastic` 形态一致 |

---

### 卡片 12：Pasig River Floating Debris ⭐

| 项目 | 详情 |
|------|------|
| **名称** | Pasig River Floating Debris Dataset |
| **发布机构** | WCSE 2024 会议论文团队 |
| **年份** | 2024 |
| **论文** | "Real-Time Detection of Floating Debris in Waterways Using YOLOv8." WCSE 2024 |
| **下载链接** | 论文 PDF: https://www.wcse.org/WCSE_2024/002.pdf（数据集本身可能未公开托管） |
| **下载状态** | ⚠️ 需确认 — 论文提及但未提供公开下载链接；需联系作者 |
| **许可协议** | 未知 |
| **规模** | 1,144 张图像（19 分钟视频抽帧，1 fps） |
| **标注格式** | YOLO（Roboflow 标注） |
| **视角** | **河流水面**（菲律宾 Pasig River，固定摄像头） |
| **类别清单** | **4 类：garbage, aquatic plants, branches, leaves** |
| **HYHQ 映射** | `water_plant` ✅（aquatic plants）<br>`misc_debris` ✅（garbage + branches + leaves）<br>其他细类 ❌ |
| **数据质量** | 真实城市河流场景，与 HYHQ 高度相似；但类别少 |
| **迁移性评估** | ✅ 高（场景匹配）但 ⚠️ 数据获取不确定 — 需确认是否公开 |

---

### 卡片 13：UAV-Flow ⭐

| 项目 | 详情 |
|------|------|
| **名称** | UAV-Flow |
| **发布机构** | 学术研究团队（中国） |
| **年份** | 2026（预印本） |
| **论文** | "FLD-Net for Floating Litter Detection in UAV Remote Sensing." Preprints.org 2026 |
| **下载链接** | 论文: https://www.preprints.org/manuscript/202601.2187（数据集下载链接需查看论文附录） |
| **下载状态** | ⚠️ 需确认 — 预印本刚发布，数据集可能刚上线 |
| **许可协议** | 未知 |
| **规模** | 多场景无人机漂浮垃圾数据集（规模待确认） |
| **视角** | **无人机航拍**（多场景河道/水面） |
| **HYHQ 映射** | `bottle` ⚠️<br>`plastic` ⚠️<br>`water_plant` ⚠️<br>（具体类别需确认） |
| **数据质量** | 无人机视角是新的观测维度 |
| **迁移性评估** | 待确认 — 建议关注其正式发表后的公开数据 |

---

## 二、覆盖矩阵：数据集 × HYHQ 9 个空缺细类

> 图例：✅ = 直接覆盖（该类有明确标注样本）；⚠️ = 间接/部分覆盖（近似类或需筛选）；❌ = 无覆盖

| 数据集 | bottle | foam_board | water_plant | algae_mass | plastic | paper | glass | metal | fabric |
|--------|:------:|:----------:|:-----------:|:----------:|:-------:|:-----:|:-----:|:-----:|:------:|
| **TACO** | ✅ | ⚠️ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **PoTATO** | ✅✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **AquaTrash** | ⚠️ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Underwater Plastic Pollution** | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ | ⚠️ |
| **CANSURF** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **River Flow Trash** | ✅ | ❌ | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ | ❌ |
| **Marine Debris Images (Kaggle)** | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ |
| **CleanSea / e-CleanSea** | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ⚠️ |
| **TrashCan** | ⚠️ | ❌ | ❌ | ❌ | ⚠️ | ❌ | ❌ | ⚠️ | ❌ |
| **DroneWaste** | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ | ❌ | ⚠️ | ⚠️ |
| **Cox's Bazar (Mendeley)** | ✅ | ❌ | ❌ | ❌ | ✅ | ⚠️ | ❌ | ❌ | ⚠️ |
| **Pasig River** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **UAV-Flow** | ⚠️ | ⚠️ | ⚠️ | ❌ | ⚠️ | ❌ | ❌ | ⚠️ | ❌ |
| **覆盖数（✅+⚠️）** | 12/13 | 4/13 | 4/13 | 0/13 | 10/13 | 3/13 | 3/13 | 9/13 | 5/13 |

---

## 三、推荐优先级分级

### ⭐⭐⭐ 首选（强烈推荐下载使用）

| 数据集 | 核心价值 | 关键细类 | 规模 |
|--------|----------|----------|------|
| **PoTATO** | 水面塑料瓶专项，12,380 实例，场景高度匹配 | `bottle` | 12.3k 实例 |
| **CANSURF** | 水面金属罐专项，ASV 视角，7.3k 图 | `metal` | ~7.3k 图 |
| **TACO** | 类别最全面的通用垃圾数据集，COCO 格式，CC BY 4.0 | `bottle/plastic/paper/glass/metal` | 1.5k 图 / 4.8k 实例 |
| **AquaTrash** | TACO 水相关子集，glass/metal/paper/plastic 四类精准 | `glass/metal/paper/plastic` | 369 图 |
| **Underwater Plastic Pollution (Kaggle)** | 15 类丰富类别，含 gbottle/metal/can/glove 等稀缺类 | `bottle/glass/metal/fabric` | 5.1k 图 |

### ⭐⭐ 次选（有价值但场景迁移需注意）

| 数据集 | 核心价值 | 关键细类 | 注意事项 |
|--------|----------|----------|----------|
| **River Flow Trash** | 河流水面场景，含 bottle + grass（水生植物） | `bottle/water_plant` | 类别仅 8 类，部分细类缺失 |
| **Marine Debris Images (Kaggle)** | 含 foam 类（稀缺！），bottle/can/plastic | `foam_board/bottle/metal/plastic` | 海洋场景，需筛选 |
| **CleanSea / e-CleanSea** | 分割掩码精细，19 类，含 towel/glove（织物近似） | `bottle/plastic/metal/fabric` | 水下视角，迁移成本高 |

### ⭐ 备选（参考价值或需进一步确认）

| 数据集 | 核心价值 | 风险 |
|--------|----------|------|
| **Cox's Bazar (Mendeley)** | 海滩 bottle/plastic 数据，COCO 格式 | 海滩场景，与水面有差异 |
| **Pasig River** | 城市河流水面 + 水生植物 | 下载链接未确认，需联系作者 |
| **UAV-Flow** | 无人机视角新维度 | 预印本阶段，数据未正式发布 |
| **TrashCan** | 大规模水下垃圾 | 深海 ROV 视角，迁移性极低 |
| **DroneWaste** | 垃圾场航拍，含 textile 类 | 陆地垃圾场场景，与水面无关 |

---

## 四、空缺细类分析与自采建议

### 4.1 各细类数据覆盖现状

| 细类 | 公开数据集覆盖情况 | 覆盖评估 |
|------|-------------------|----------|
| **bottle** | PoTATO (12.3k) + TACO + AquaTrash + Underwater PP + River Flow + Marine Debris + Cox's Bazar + CleanSea | ✅ **充足** — 首选 PoTATO 水面专项 + TACO 补充 |
| **plastic** | TACO + AquaTrash + Underwater PP + Marine Debris + CleanSea + Cox's Bazar | ✅ **充足** — 多源补充 |
| **metal** | CANSURF (7.3k) + TACO + AquaTrash + Underwater PP + Marine Debris + CleanSea | ✅ **充足** — CANSURF 水面专项 |
| **glass** | TACO + AquaTrash + Underwater PP (gbottle) | ⚠️ **中等** — 仅 3 个数据集，水面场景稀缺 |
| **paper** | TACO + AquaTrash + Cox's Bazar (packet 近似) | ⚠️ **中等** — 水面纸质垃圾罕见 |
| **foam_board** | Marine Debris (foam) + TACO (styrofoam 近似) | ⚠️ **稀缺** — 仅 2 个间接覆盖 |
| **fabric** | Underwater PP (glove/mask) + CleanSea (towel/glove/rope) + DroneWaste (textile) + Cox's Bazar (rope) | ⚠️ **稀缺** — 均为近似类，无直接织物/布料类 |
| **water_plant** | River Flow Trash (grass) + Pasig River (aquatic plants) | ⚠️ **稀缺** — 仅 2 个直接覆盖 |
| **algae_mass** | **无任何公开数据集直接覆盖** | ❌ **完全空缺** |

### 4.2 完全无公开数据支持的细类

#### ❌ algae_mass（藻类团）— 完全空缺
- **现状**：所有检索到的垃圾/漂浮物数据集中均无 `algae_mass` / 藻类团 / 水华 / 赤潮 作为独立标注类
- **建议**：
  1. **自采为主**：在 HYHQ 项目实地拍摄河道藻类团/水华/水葫芦等水生植物聚集场景，建议采集 ≥500 张
  2. **迁移利用**：River Flow Trash 的 `grass` 类、Pasig River 的 `aquatic plants` 类可作为形态近似，预训练后再微调
  3. **合成增强**：将水下藻类图像或湖泊水华视频帧抽帧后，叠加水面背景进行合成增强
  4. **关注**：海洋赤潮数据集（如 NOAA 赤潮观测数据）可作远程迁移参考

#### ⚠️ fabric（织物/布）— 无直接类，仅近似
- **现状**：无数据集将"水面漂浮布料/织物"作为独立类；最接近的是 underwater PP 的 `glove/mask`、CleanSea 的 `towel/glove/rope`
- **建议**：
  1. **自采为主**：河道中漂浮的编织袋、衣物、渔网碎片等，建议采集 ≥300 张
  2. **利用近似类预训练**：用 CleanSea 的 `towel/glove` + Underwater PP 的 `glove/mask` 做粗训练，再用自采数据微调
  3. **合成**：将布料纹理贴在水面背景上生成合成样本

#### ⚠️ foam_board（泡沫板/聚苯乙烯）— 稀缺
- **现状**：Marine Debris Images 有 `foam` 类（泡沫块），TACO 有 `styrofoam`（聚苯乙烯包装）
- **建议**：
  1. **优先下载** Marine Debris Images (Kaggle) 的 `foam` 类数据
  2. 从 TACO 筛选 `Styrofoam` / `Polystyrene` 细类
  3. **自采补充**：河道中常见的白色泡沫板/泡沫箱碎片，建议采集 ≥200 张

### 4.3 推荐数据组合方案（按优先级）

**阶段一：快速填充（1-2 周）**
1. PoTATO → `bottle`（12.3k 水面瓶）
2. CANSURF → `metal`（7.3k 水面罐）
3. TACO → 筛选水边/海滩样本 → `bottle/plastic/paper/glass/metal`
4. AquaTrash → `glass/metal/paper/plastic`（369 图精准补充）

**阶段二：扩展补充（2-4 周）**
5. Underwater Plastic Pollution (Kaggle) → `bottle/glass/metal/fabric`（5.1k 图）
6. River Flow Trash → `bottle/water_plant`（4.6k 河流场景）
7. Marine Debris Images (Kaggle) → `foam_board/bottle/metal`

**阶段三：自采补缺（持续）**
8. 自采 `algae_mass`（≥500 张）
9. 自采 `fabric` / `foam_board` 补充（≥300 张/类）
10. 自采 `water_plant` 中国河道本土场景（≥300 张）

---

## 五、数据获取状态汇总

| 数据集 | 下载状态 | 验证时间 | 备注 |
|--------|----------|----------|------|
| TACO | ✅ 直接下载 | 2026-09-18 | GitHub + Zenodo 双通道 |
| PoTATO | ✅ 直接下载 | 2026-09-18 | GitHub 仓库公开 |
| AquaTrash | ✅ 直接下载 | 2026-09-18 | Ultralytics 平台 |
| Underwater Plastic PP | ⚠️ 需注册 Kaggle | 2026-09-18 | 免费注册即可 |
| CANSURF | ✅ 直接下载 | 2026-09-18 | Zenodo DOI 可访问 |
| River Flow Trash | ✅ 直接下载 | 2026-09-18 | Ultralytics 平台 |
| Marine Debris Images | ⚠️ 需注册 Kaggle | 2026-09-18 | 免费注册即可 |
| CleanSea / e-CleanSea | ✅ 直接下载 | 2026-09-18 | 官网直接提供 |
| TrashCan | ⚠️ 需申请 | 2026-09-18 | Minnesota 大学仓储库 |
| DroneWaste | ✅ 直接下载 | 2026-09-18 | Zenodo 公开 |
| Cox's Bazar | ✅ 直接下载 | 2026-09-18 | Mendeley Data |
| Pasig River | ⚠️ 未确认 | 2026-09-18 | 需联系作者 |
| UAV-Flow | ⚠️ 未确认 | 2026-09-18 | 预印本阶段 |

---

## 六、参考链接索引

| 数据集 | 官方链接 |
|--------|----------|
| TACO | https://github.com/pedropro/TACO · http://tacodataset.org/ · https://zenodo.org/records/3587843 |
| PoTATO | https://github.com/luisfelipewb/PoTATO · https://arxiv.org/abs/2409.12659 |
| AquaTrash | https://platform.ultralytics.com/ultralytics/datasets/aqua-trash · https://datasetninja.com/aqua-trash |
| Underwater Plastic PP | https://www.kaggle.com/datasets/arnavs19/underwater-plastic-pollution-detection |
| CANSURF | https://doi.org/10.5281/zenodo.20100657 · https://github.com/ZaidAljundiHW2/CANSURF |
| River Flow Trash | https://platform.ultralytics.com/salamander-wolf/datasets/river-flow-trash |
| Marine Debris Images | https://www.kaggle.com/datasets/zienabesam/marine-debris-images-dataset |
| CleanSea / e-CleanSea | https://www.dlsi.ua.es/~jgallego/datasets/cleansea/ |
| TrashCan | https://irvlab.cs.umn.edu/resources/trashcan |
| DroneWaste | https://zenodo.org/records/17288038 |
| Cox's Bazar | https://data.mendeley.com/datasets/bdzg4tjy63/1 |
| Pasig River | https://www.wcse.org/WCSE_2024/002.pdf |
| UAV-Flow | https://www.preprints.org/manuscript/202601.2187 |

---

> **报告说明**：
> - 本报告所有下载链接均于 2026-09-18 通过搜索引擎和页面抓取验证可访问性
> - "已核实可下载" = 有明确公开 URL 且无需复杂审批；"仅论文声称" = 论文提及但未找到公开下载入口
> - 覆盖矩阵中 `⚠️` 表示需要人工筛选或近似映射，实际使用时需仔细核对类别定义
> - 建议优先下载 ⭐⭐⭐ 首选数据集，快速补齐 bottle/metal/plastic/glass/paper 五类；algae_mass 等空缺细类必须自采

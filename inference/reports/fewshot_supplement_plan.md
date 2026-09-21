# 少样本类数据补充方案（bottle / foam_board）

> 创建：2026-09-21 · 触发：eval-v2 实测发现塑料瓶漏检（bottle test AP=0.365，foam_board AP=0.114）
> 现状：unified-v2 中 bottle=78 框、foam_board=50 框（全 15 类最少）

## 1. 问题确认

- eval-v2 高分辨率实验（imgsz=1280/conf=0.1）：27 图中 bottle 仅检出 2 个；
- 对 16 张新下载水面瓶/泡沫图跑自动标注：**0 个 bottle、0 个 foam_board 被检出**（模型自身不认识，auto-label 不可行）；
- 结论：这两类必须靠**带现成标注的公开数据集**补充，不能靠"下载图+自动标注"。

## 2. 已下载素材（待标注池，不入训练 until 人工标）

`D:\HYHQ_data\.runtime\supplement_bottle_foam\images\`（16 张）：
- bottle_01~08：水面塑料瓶（夕阳特写/PET 瓶/溪流红盖/绿瓶浮莲等）
- foam_01~08：水面泡沫板/泡沫箱（柳州执法/汉江三块/阿勒泰水渠/松花江蓝色板等）

> 这些图无 bbox，当前模型也标不准，**暂存待人工标注**（用 LabelImg/CVAT，标注规范见 docs/硬缺口自采规范.md）。

## 3. 带现成标注的候选数据集（按对口度排序）

| # | 数据集 | 规模 | 标注 | 对口度 | 获取方式 |
|---|---|---|---|---|---|
| 1 | **河道塑料瓶检测（SegmentFault 分享）** | 1000+ 标注 | YOLO 格式，已划分 | ★★★★★ 直接对口 | 百度网盘 `https://pan.baidu.com/s/1VL4VhxE8KdsIg22kFvf-FA` 提取码 `cb3p`（**需手动下**）|
| 2 | **水面垃圾数据集（CSDN）** | 4125 图 | YOLO/VOC 格式 | ★★★★ 水面场景 | 百度网盘（需手动下）|
| 3 | **Roboflow River Flow Trash（Weiyu）** | 654 图 / 6822 框 | YOLO 格式 | ★★★★ 河流漂浮物 | platform.ultralytics.com 公开，可 API 拉 |
| 4 | **Kaggle Trash Detection（mohanraj2145）** | Bottles+Wrappers 两类 | YOLOv8 格式已划分 | ★★★ 瓶子专项 | Kaggle（需登录）|
| 5 | **TACO 续传** | 现仅 402/1500 图已纳入 | COCO bbox（含 5=透明塑料瓶、46=泡沫食品容器、57=泡沫塑料片）| ★★★ 陆地场景有 domain gap | taco_fetch.py 后台续传中 |
| 6 | **Roboflow 塑料瓶（racnhua43）** | 9889 图 | bbox | ★★ 通用瓶，非水面 | Roboflow Universe |
| 7 | **UAV-Bottle Dataset** | 航拍瓶 | bbox | ★★ 航拍小目标 | 论文附件 |

## 4. 推荐落地路径

1. **用户手动下载 #1（河道塑料瓶 1000+）**——最对口，直接补 bottle 类到 ~1000 框；
2. **同时续 TACO**（#5）——完成后重跑 prepare_unified_v2.py，自动纳入剩余 ~1100 图的 bottle/foam 标注；
3. **#3 Roboflow river flow trash** 用 API 拉（无需登录的公开集），作为水面漂浮物补充；
4. 16 张已下载图**人工标注**后并入（作为"中国本土水面"domain 补充）；
5. 全部到位后重跑预处理 → 重训 river-eco-v3，预期 bottle AP 从 0.365 → 0.7+。

## 5. 与现有体系的映射

- #1/#2/#3 的 bottle → unified-v2 `bottle`（id=0）
- #1/#2 的 foam/泡沫板 → `foam_board`（id=1）
- TACO 类 5/46/57 → 同上（prepare_unified_v2.py 已映射）
- 重训前在 prepare_unified_v2.py 登记新源适配器

## 6. 第二轮新发现（2026-09-21，针对图1/图2误检反查）

### 6.0 ~~零成本：IWHR 标注被浪费~~（已证伪，2026-09-21）

**结论：IWHR VOC XML 全部类名就是 `floater`（3897/3897），无细分标注。** 论文摘要说的"含塑料瓶/泡沫板/水草/藻类"是覆盖对象类型，不是标注类。无法重映射，此路不通。

**真正的白捡：TACO 续传完成。** 已下载 857/1500 图（644 张 Flickr 404 失败），COCO 标注实际含：
- bottle: Clear plastic bottle 285 + Other plastic bottle 50 = **335 框**
- foam_board: Styrofoam piece 112 + Foam cup 13 + Foam food container 15 = **140 框**
- glass: Glass bottle 104 框

当前预处理只纳入了 402 张，**重跑 prepare_unified_v2.py 即自动纳入新增 ~455 张**，bottle/foam_board 框数直接上涨。注意 TACO 是陆地场景，domain gap 大，仅作类别形态补充。

### 6.1 新增对口数据集

| # | 数据集 | 规模 | 关键类 | 解决的问题 | 获取 |
|---|---|---|---|---|---|
| 8 | **无人机视角河道浮木检测**（51CTO）| 1345 图/1 类 | 浮木 | **直接解决"木头→outfall 误检"**（图2 bank_10）| VOC+YOLO，51CTO 博客分享 |
| 9 | **人民长江水库漂浮物**（YOLOX 论文）| 8446 图/8 类 | 瓶子/垃圾袋/落叶/树枝/零食袋/塑料盒/**白色泡沫**/纸杯 | foam_board + 树枝双补 | 论文数据集（联系作者或公开库）|
| 10 | **信阳师范水面漂浮物** | 落叶4788/**水草1472**/睡莲/岸边植物 | 水草+岸边植物 | water_plant 正样本 + 岸带负样本 | 期刊论文数据集 |
| 11 | **人民长江河道精细化** | 18000 图 | 塑料瓶/塑料盒/**泡沫箱**/纸箱/气球/塑料袋 | 大规模泡沫箱 | 期刊论文数据集 |
| 12 | **清洁船 FloW 融合集** | 4400 图/8 类 | 瓶子/草/牛奶盒/树枝/塑料袋/塑料垃圾/球/树叶 | 小目标+眩光复杂场景 | 论文数据集 |
| 13 | **FloYO-Net** | 341 图/6 类 | PB/PG/TO/PD/**Styrofoam**/CN | Styrofoam 即泡沫 | 论文公开 |
| 14 | **FloW (ICCV2021)** | FloW-Img + 雷达 | 内河漂浮物基准 | 标准 benchmark | 已申请 datasets@orca-tech.com.cn，**邮件未发** |

### 6.2 优先级重排（按解决误检/漏检的 ROI）

1. **P0 零成本**：改 IWHR 映射（6.0）→ 立刻给 foam_board/water_plant/algae_mass 几千框
2. **P0**：#8 无人机浮木 1345 图 → 解决木头误判 outfall
3. **P1**：#9/#11 白色泡沫/泡沫箱类 → foam_board 从 50 → 数千
4. **P1**：#10 水草/岸边植物 → water_plant 正样本 + 岸带负样本
5. **P2**：原 #1 百度网盘河道塑料瓶 → 继续补 bottle
6. **P2**：发送 FloW 申请邮件（#14）

### 6.3 图1/图2 误检对应补样

- 白色塑料袋/泡沫袋 → outfall 误检（图1）：补 foam_board 正样本（#9/#11/6.0）
- 木头/原木 → outfall 误检（图2）：补浮木/树枝/岸边植物（#8/#10/#12）
- 密集垃圾滩小碎片漏检（图1/3）：补 #11 的 18000 图密集场景 + 推理用 imgsz=1280

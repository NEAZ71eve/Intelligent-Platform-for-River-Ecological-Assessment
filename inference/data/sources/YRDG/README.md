# YRDG 数据集获取记录

## 出处
- 论文：Jiang Z. et al., *Sensors* 24(1):50 (2024)
- DOI: https://doi.org/10.3390/s24010050
- 期刊：Sensors（MDPI）

## 许可
- 需确认（MDPI 默认 CC BY 4.0，但需核对论文 Data Availability 段与数据仓库条款）
- 待下载后在本文档补充具体许可类型与 URI

## 规模
- 图像数：3,807
- 标注对象：84% 为小目标
- 标注类别：7 类水面漂浮垃圾

## 映射到评估大类
- 水面漂浮物（补充数据集）

## 标注格式
- 需从论文"Data Availability"段确认（YOLO/COCO 等）

## 获取方式
1. 访问论文页面：https://doi.org/10.3390/s24010050
2. 在 "Data Availability" 段定位数据仓库链接（GitHub/Zenodo 等）
3. 下载归档包至 `data/raw/YRDG/`
4. 计算 SHA-256 填入下方
5. 运行 `python -m training.audit_datasets data/raw/YRDG --dedup`

## 下载记录
- 下载日期：__待填__
- 归档 SHA-256：__待填__
- 下载人：__待填__
- 归档原始文件名：__待填__

## 备注
- 本文件仅为获取记录，不包含数据本体
- 原始数据通过 .gitignore 排除入库

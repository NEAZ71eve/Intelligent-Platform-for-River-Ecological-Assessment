# IWHR_AI_Lable_Floater_V1 数据集获取记录

## 出处
- 论文：Qiao G. et al., *Scientific Data* 12, 385 (2025)
- DOI: https://doi.org/10.1038/s41597-025-04594-9
- 期刊：Scientific Data（Nature Portfolio）

## 许可
- CC BY 4.0（ Creative Commons Attribution 4.0 International）
- 许可 URI：https://creativecommons.org/licenses/by/4.0/

## 规模
- 图像数：3,000
- 标注对象数：23,692
- 标注类别：见论文数据可用性声明

## 映射到评估大类
- 水面漂浮物（主力数据集）

## 标注格式
- 需从论文"Data Availability"声明确认具体标注格式（COCO/YOLO/VIA 等）
- 下载后需在 `data/raw/IWHR_AI_Lable_Floater_V1/` 内补充 `LABELS.md` 说明字段定义

## 获取方式
1. 访问论文页面：https://doi.org/10.1038/s41597-025-04594-9
2. 在 "Data Availability" / "Code Availability" 段定位数据仓库链接（figshare / Zenodo / OSF 等）
3. 按仓库指引下载归档包至本地 `data/raw/IWHR_AI_Lable_Floater_V1/`
4. 计算归档 SHA-256 并填入下方
5. 运行 `python -m training.audit_datasets data/raw/IWHR_AI_Lable_Floater_V1 --dedup`

## 下载记录
- 下载日期：__待填（实际下载后填写）__
- 归档 SHA-256：__待填__
- 下载人：__待填__
- 归档原始文件名：__待填__

## 备注
- 本文件仅为获取记录，不包含数据本体
- 原始数据通过 .gitignore 排除入库

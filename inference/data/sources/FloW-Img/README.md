# FloW-Img 数据集获取记录

## 出处
- 论文：Hou Y. & Yu Y., *IET Image Processing* (2025)
- DOI: https://doi.org/10.1049/ipr2.70248
- 期刊：IET Image Processing

## 许可
- 需确认（待下载后核对数据仓库条款）
- 待补充许可类型与 URI

## 规模
- 图像数：2,000
- 标注类别：单类（bottle）

## 映射到评估大类
- 水面漂浮物（补充数据集）

## 标注格式
- 需从论文"Data Availability"段确认

## 获取方式
1. 访问论文页面：https://doi.org/10.1049/ipr2.70248
2. 在 "Data Availability" 段定位数据仓库链接（GitHub/Zenodo 等）
3. 下载归档包至 `data/raw/FloW-Img/`
4. 计算 SHA-256 填入下方
5. 运行 `python -m training.audit_datasets data/raw/FloW-Img --dedup`

## 下载记录
- 下载日期：__待填__
- 归档 SHA-256：__待填__
- 下载人：__待填__
- 归档原始文件名：__待填__

## 备注
- 本文件仅为获取记录，不包含数据本体
- 原始数据通过 .gitignore 排除入库

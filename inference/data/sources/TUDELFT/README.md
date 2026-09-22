# TUDELFT 数据集获取记录

## 出处
- 论文：Jia T. et al., *Frontiers in Water* 5 (2023)
- DOI: https://doi.org/10.3389/frwa.2023.1298465
- 期刊：Frontiers in Water

## 许可
- 需确认（Frontiers 默认 CC BY 4.0，需核对论文 Data Availability 段）
- 待下载后补充许可类型与 URI

## 规模
- 图像数：9,473（含相机采集 + 手机采集两种来源）

## 映射到评估大类
- 水面漂浮物（补充数据集）

## 标注格式
- 需从论文"Data Availability"段确认

## 获取方式
1. 访问论文页面：https://doi.org/10.3389/frwa.2023.1298465
2. 在 "Data Availability" 段定位数据仓库链接
3. 下载归档包至 `data/raw/TUDELFT/`
4. 计算 SHA-256 填入下方
5. 运行 `python -m training.audit_datasets data/raw/TUDELFT --dedup`

## 下载记录
- 下载日期：__待填__
- 归档 SHA-256：__待填__
- 下载人：__待填__
- 归档原始文件名：__待填__

## 备注
- 本文件仅为获取记录，不包含数据本体
- 原始数据通过 .gitignore 排除入库

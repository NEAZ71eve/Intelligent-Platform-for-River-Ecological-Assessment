# 第三方来源说明

## 朋友仓库的河道图像观察功能

- 来源：[NEAZ71eve/Intelligent-Platform-for-River-Ecological-Assessment](https://github.com/NEAZ71eve/Intelligent-Platform-for-River-Ecological-Assessment)
- 参考版本：`c80982473418502fbff28f5864dbad8b97441ded`
- 复用依据：项目用户确认朋友仓库代码可用于本项目，授权整合尚未实现的功能。
- 参考实现：上游 `backend/ecology/assessment_worker.py`、`detection.py`、`geo.py`、`rules.py`、评估模型/API，以及 `miniprogram/pages/assessment/`、`lib/assessment.js` 与相关测试。
- 本项目改写为独立 assessments 模块，并补充模型隔离、权限、保留策略、规则快照和输入/输出边界检查。功能映射见 [整合说明](docs/朋友仓库整合说明.md)。

## 河道图像检测模型

- 上游文件：`inference/artifacts/river-eco-yolov8n-v1.onnx`
- 原文件 SHA-256：`96fc7178c28f1eb29bae9703f440d6bda9c041433edb3e335691f38a5ee6da6c`
- 上游清单声明：IWHR CC BY 4.0；Ultralytics YOLOv8n AGPL-3.0。
- 上游数据来源链接：[论文 DOI](https://doi.org/10.1038/s41597-025-04594-9)。软件来源：[Ultralytics](https://github.com/ultralytics/ultralytics)。
- 二进制在本地恢复并验证，不重新训练，不改写其原始字节。本项目派生清单只调整支持类别、名称和使用边界，保留上游原清单与来源记录。

## 花卉识别数据和预训练权重

原有 M3 花卉数据的逐图作者与许可保存在 [署名清单](inference/data/FLOWER_PHOTOS_ATTRIBUTION.txt)，权重来源及使用边界见 [模型评估报告](inference/reports/M3模型评估报告.md)。本次河道功能整合不改变这些文件。

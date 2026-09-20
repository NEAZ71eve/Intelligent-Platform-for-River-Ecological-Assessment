# 河道漂浮物检测模型

这是与五类花卉识别独立登记、独立任务的实验检测模型。复用朋友项目中已训练的 ONNX 权重，保留现有花卉模型及其登记约束。

## 来源与可复现获取

- 仓库：[Intelligent-Platform-for-River-Ecological-Assessment](https://github.com/NEAZ71eve/Intelligent-Platform-for-River-Ecological-Assessment/tree/c80982473418502fbff28f5864dbad8b97441ded)
- 固定提交：`c80982473418502fbff28f5864dbad8b97441ded`
- 权重：`inference/artifacts/river-eco-yolov8n-v1.onnx`
- SHA-256：`96fc7178c28f1eb29bae9703f440d6bda9c041433edb3e335691f38a5ee6da6c`
- 数据出处：[IWHR 数据论文](https://doi.org/10.1038/s41597-025-04594-9)。上游声明 IWHR 为 CC BY 4.0，Ultralytics YOLOv8n 为 AGPL-3.0；保留这些来源和许可说明。

```sh
.venv/bin/python inference/river/fetch_model.py
scripts/manage.sh register_detector "$PWD/inference/artifacts/river-floating-debris-v1.manifest.json" --activate
scripts/manage.sh seed_assessment_rules --activate
scripts/manage.sh run_assessment_worker
```

获取脚本只下载固定提交的权重、验证哈希并复制本目录中的派生 manifest，不执行上游代码。ONNX 权重被 git 忽略；源码提交保留获取脚本、派生 manifest 和未经修改的 `upstream.manifest.json`。

登记命令会输出模型 UUID；也可在管理后台的“河道检测模型版本”查看。停用与恢复指定版本：

```sh
scripts/manage.sh activate_detector --disable
scripts/manage.sh activate_detector <模型UUID>
```

启停只影响河道检测，不改变花卉模型。进行中的任务沿用领取时的模型快照，历史结果保持原版本。教学规则在管理后台分别启停；初始化命令不会替换已经启用的自定义规则。

## 实际支持范围

ONNX 输入为 `float32[1,3,640,640]`，输出为 `float32[1,19,8400]`，包含 15 类预测头。上游 `build_dataset.py` 将 IWHR 的 `floater` 映射到第 **9** 类 `misc_debris`；ONNX 的 names 元数据吻合。原 manifest 的第 0 类“塑料瓶罐”属于预留类别，不能当作已训练能力。

本次对上游三张公开训练/验证拼图做了前向诊断，超过 0.5 的预测全部来自第 9 类。使用正式子进程和等比例补边流程时，三个样本分别留下 25、22、20 个检测框，最大分数约为 0.852、0.863、0.834，详见 `runtime-diagnostic.json`（含样本哈希）。另一次预测头检查中其他头最大分数约 0.00001–0.00002。该诊断只验证类别编号和推理链路，不能证明准确率。

派生 manifest 仅开放 `supported_class_ids: [9]`，显示为“漂浮物（实验检测）”；其余头无法生成检测结果或污染原因。未检出和图片质量不足都返回“不确定”，不能得出“清洁/优/100 分”。即使检出了目标，框面积也只是图像中的框占比，不能当作水域污染覆盖率。

## 训练与指标限制

- 上游 v1 是 IWHR 单类训练；v2 多源报告仅记录数据预处理，没有提交可用的 v2 权重。
- 上游末轮验证指标为 precision 0.89652、recall 0.81657、mAP50 0.9035、mAP50–95 0.65835；它们来自训练运行的最后一轮，不能直接代表导出的 best 权重或实际河道巡查表现。
- 原 manifest 引用的 `inference/reports/yolo-v1-report.md` 不在固定提交中，派生 manifest 明确记录此缺失。
- 上游旧版建集脚本把“dHash 与 SHA 同时相同”作为去重条件，无法保证相似场景不跨训练/验证集；数字 YOLO 标签也直接套用全局细类表，扩展其他数据源时必须逐源重新映射。
- v2 报告中的水草类近似映射、陆地 TACO 场景与五类零样本缺口都仍需人工复核和重新训练；本集成没有把这些数据准备结果包装为已完成能力。

## 运行时边界

模型登记检查 manifest、哈希、标准 ONNX 图、固定输入输出和一次零输入前向。正式任务使用继承全局执行锁的独立 CPU 子进程，硬超时终止进程组，限制图片像素、候选数、输出数，并拒绝非有限数值；不继承数据库凭据。任务保留模型配置快照和校验摘要。分数仅适用于透明的演示规则，不属于官方生态或水质评价。

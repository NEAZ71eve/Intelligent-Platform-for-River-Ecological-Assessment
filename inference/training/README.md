# 五类花卉实验的复现方法

本目录训练冻结的 ImageNet 特征提取器之上的线性分类头，比较 MobileNetV3-Small 和 EfficientNet-B0。它不会训练通用植物鉴定模型。当前冻结结果见 [M3 模型评估报告](../reports/M3模型评估报告.md)。训练不需要 Django 数据库，也不需要启动 API。

## 环境与文件

已验证环境为 Apple M2、8 GB 内存、macOS arm64、CPython 3.12.6。训练使用 CPU、2 个 PyTorch 线程、batch size 16，并顺序运行两个模型。生产服务不需要安装 PyTorch 或 scikit-learn；生产依赖在 `backend/requirements.txt`。

以下命令从项目根目录执行：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r inference/training/requirements.txt
mkdir -p .runtime/datasets
curl --fail --location --connect-timeout 15 \
  --output .runtime/datasets/flower_photos.tgz \
  https://storage.googleapis.com/download.tensorflow.org/example_images/flower_photos.tgz
.venv/bin/python inference/training/prepare_flowers.py
```

若已有 `.venv`，跳过创建环境。PyTorch 首次加载模型时会下载官方 `IMAGENET1K_V1` 权重，缓存在 `.runtime/torch-cache/hub/checkpoints/`。下载地址及完整 SHA256 记录在两份验证报告中。

数据准备会校验压缩包 SHA256、逐图署名、文件格式、图片数量，移除完全重复图片，并将 dHash 汉明距离不大于 4 的相近图片放入同一个组。每个组只能属于一个划分，按类分配约 70%/15%/15% 到训练、验证、测试集。若仓库已有的冻结划分与重新生成的内容不同，脚本会停止，不能直接覆盖它。

原始图片、训练缓存、ONNX 二进制均不提交 Git。仓库保留划分清单、逐图许可署名、模型清单和评估报告。下载全新仓库后，需要复现或从受信任的本地备份恢复二进制，才能启用真实识别。

## 安全复现已有实验

仓库已有冻结的 v1 报告。请使用一个新的、空的复现目录，避免修改原始证据：

```bash
.venv/bin/python inference/training/train_flowers.py \
  --stage all --reproduction-dir .runtime/flowers-reproduction-01
```

复现输出位于该目录的 `reports/`、`cache/`、`artifacts/`。需要分步运行或从中断处继续时，按顺序执行：

```bash
.venv/bin/python inference/training/train_flowers.py --stage fit --model mobilenet_v3_small --reproduction-dir .runtime/flowers-reproduction-01
.venv/bin/python inference/training/train_flowers.py --stage fit --model efficientnet_b0 --reproduction-dir .runtime/flowers-reproduction-01
.venv/bin/python inference/training/train_flowers.py --stage freeze --reproduction-dir .runtime/flowers-reproduction-01
.venv/bin/python inference/training/train_flowers.py --stage evaluate --model mobilenet_v3_small --reproduction-dir .runtime/flowers-reproduction-01
.venv/bin/python inference/training/train_flowers.py --stage evaluate --model efficientnet_b0 --reproduction-dir .runtime/flowers-reproduction-01
```

只执行尚未成功产出报告的阶段。`fit` 拒绝覆盖已完成的验证报告或冻结选择；`evaluate` 拒绝重复写入独立测试报告。省略 `--reproduction-dir` 会使用原 v1 路径，已有结果时将立即停止。

不同硬件、底层算子或依赖可能造成时间、浮点值和 ONNX 文件哈希不同。复现产物必须与它自己生成的 manifest 配套；不要修改原 manifest 的 SHA256 来掩盖不同的文件，也不要把一次复现称为新增的独立测试证据。若要修改数据、预处理、阈值规则或模型选择规则，应另开实验版本并重新设计独立评估，本次收尾未做这些改动。

## 防止测试集参与调参

1. 特征提取器设为 `eval()`、关闭梯度。缓存包含三个划分的特征，但只有训练集特征和标签用于拟合分类头，没有用测试集拟合 BatchNorm、归一化器或分类器。
2. 四个候选 `C` 值只按验证集 macro F1 选择；同分保留较小的 `C`。
3. 阈值只按验证集选择：接受样本至少 30 张、接受准确率至少 90%，满足要求时优先覆盖率最高；两模型 v1 均得到 `0.0`，所以正常图像不作低分拒识。
4. 两份验证报告的 SHA256 和最终模型选择先写入 `selection_v1.json`，才允许独立测试。v1 的模型选择依据是验证 macro F1；未触发延迟比较的同分分支。
5. 导出后只对冻结测试集进行一次评估，并记录所有错误图片的相对路径、真值、预测和分数。

`selection_v1.json` 的 `test_metrics_seen: false` 表示作出该选择时的状态，不是声称整个项目至今没看过测试结果。现有源码和冻结文件能支持这一执行流程，但不能替代外部预注册记录。

## 预处理和导出

训练和 ONNX 评估直接调用 `backend/recognition/adapter.py` 中的同一 `preprocess()`：EXIF 校正、RGB、短边缩放到 256（双线性）、中心裁剪 224、除以 255、按 ImageNet mean/std 归一化。输入为 NCHW float32，输出五类 logits。v1 使用 FP32、ONNX opset 17，没有量化。部署时只能使用 manifest 中的预处理配置，不能改用另一套 torchvision 默认变换。

线上上传还会重新编码并限制图片尺寸，线上另有低图质拦截。这些完整上传步骤不包含在离线测试指标中；端到端协议检查也不能替代重新采样的线上准确率评估。

## 本次收尾修正

原 `--stage all` 在发现已有最终测试之前，可能先重写验证报告和分类头，破坏冻结报告的哈希引用。现已添加前置拒绝覆盖检查和独立复现目录，并在测试前核对两份冻结验证报告、数据划分与特征缓存的实验标识；重复确认相同选择不再重写文件。本次未重训、未重跑独立测试，也未修改原 v1 的 JSON、划分、模型二进制或阈值。

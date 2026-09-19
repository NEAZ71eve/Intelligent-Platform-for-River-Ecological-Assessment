# M3 五类花卉识别

## 范围与目录

本轮用 TensorFlow 官方 flower_photos 做五类照片分类原型：雏菊类、蒲公英类、蔷薇属花卉、向日葵类、郁金香类。不能据此区分具体物种、园艺品种、食用/药用安全，也不能保证拒绝未知对象。

- `data/`：冻结实验配置、逐图划分/SHA-256/去重分组及作者署名。
- `training/`：数据准备、冻结特征与线性分类头训练、两模型比较和 ONNX 导出。复现见 [训练说明](training/README.md)。
- `reports/`：数据审计、模型指标、转换一致性与运行资源报告。
- `artifacts/`：模型清单；大体积 ONNX 权重只保留在本机，不进入 Git。

原始 3,670 张图片去除 3 张完全重复图后，训练/验证/测试为 2,566 / 551 / 550。dHash 近重复分组不会跨集合，清单提供逐图许可对应关系。数据出处：[TensorFlow 图像教程](https://www.tensorflow.org/tutorials/load_data/images)。原始归档及预训练权重下载缓存放在忽略目录 `.runtime/`，不可把公开照片换成未获许可的抓取图片。

训练仅使用公开花卉数据。校园实拍、范围外图片集与真实目标设备评估仍待补充；不将公开数据集成绩视为真实校园识别准确率。

## 登记并启用模型

在仓库根目录执行；已按后端说明配置数据库和虚拟环境：

```bash
scripts/manage.sh migrate
scripts/manage.sh seed_recognition_knowledge
# 先按训练说明生成制品，或从开发电脑复制经过校验的 ONNX + manifest。
scripts/manage.sh register_model "$PWD/inference/artifacts/flowers-efficientnet-b0-v1.manifest.json" --activate
scripts/manage.sh run_recognition_worker
```

本轮根据验证集 macro F1 选定 EfficientNet-B0；550 张独立测试图片的准确率为 92.18%、macro F1 为 0.9200。MobileNetV3-Small 为备选，测试准确率 90.00%。详见 [评估报告](reports/M3模型评估报告.md)。也可登记第二个模型以备回退；登记不带 `--activate` 时不会切换当前版本。重复登记相同清单幂等；同名同版本不同配置会被拒绝，需显式新版本。

`HYHQ_MODEL_ROOT` 默认为仓库内 `inference/artifacts`。manifest 必须位于该目录内；`artifact` 为 manifest 同目录的 ONNX 文件名。登记命令会验证文件边界、SHA-256、标签/预处理契约及图结构，拒绝外部权重、非标准自定义运算、错误输入/输出。服务不从用户提交的 URL 下载或执行模型。

登记输出模型 UUID，后续使用：

```bash
scripts/manage.sh activate_model <模型UUID>
scripts/manage.sh activate_model --disable
```

以上 `<模型UUID>` 是需替换的占位文字。Django Admin 的模型版本列表也提供单选启用/回退和停用操作，配置字段只读。只有具备相应管理权限的管理员可操作。原先 M1 的登记元数据需要重新通过 M3 制品登记流程，不能直接视为可执行模型。

## 任务与资源约束

- 前端通过现有鉴权上传/识别任务接口使用模型，不直接访问权重或用户私有文件路径。
- Web 进程不加载推理模型。消费者获取单机执行锁后领取任务，每次派生独立 Python 子进程，ONNX Runtime 固定 CPU、单线程。
- 全局队列 20，等待超过 300 秒失败；执行默认 10 秒，`HYHQ_RECOGNITION_TIMEOUT_SECONDS` 可配 1～60 秒。执行时间包括子进程启动与加载，上传/排队另计。
- 父进程超时终止并回收子进程；子进程有自身时限并继承执行锁，因此消费者崩溃不会放任旧子进程和新任务同时执行。
- 新消费者获得锁后，将遗留运行任务标记为中断或超时失败。部署时所有消费者必须共享同一锁文件；此版本限单主机。
- 模型内容及配置摘要随任务固定，停用/切换后正在进行的任务继续用已领取的版本，既有历史结果不被重写。

每次任务重新加载模型会产生额外启动时间。报告中的单次前向耗时只能衡量模型计算，目标服务器整体资源与 30 分钟负载测试属于 M4。

## 结果解释

`result` 包括 `decision`、前三个 `candidates`、`threshold`、`model`、`scope`、`disclaimer`。候选分数是 softmax 模型分数，未经概率校准。阈值基于验证集选择，高分未知图片仍可能误判。

**本轮两个 v1 模型的阈值均为 0。** 预设规则是在验证集接受准确率达到 90% 时最大化覆盖率，结果无需拒绝任何样本。因此当前 v1 不会产生 `LOW_CONFIDENCE`，界面明确标注“候选参考、未启用低分拒识”；低图质仍会拦截。此结果保留在冻结报告中，不通过修改阈值和重复调试测试集美化结果。未来若需要更严格拒识，需另立版本并补充未知对象数据验证。

- `recognized`：最高分达到阈值，仍需结合实物核对。
- `uncertain / LOW_CONFIDENCE`：分数未达阈值，可查看候选并换角度重拍。
- `uncertain / LOW_IMAGE_QUALITY`：图片太小或近乎纯色，不做类别判断，候选为空。
- 无模型、模型校验失败、图片过期和执行超时均为明确失败，不保存伪造类别。

`candidates[].content_id` 只关联已发布且标签对应的科普内容。可执行 `seed_recognition_knowledge` 初始化五篇原创观察稿；重复执行不会覆盖管理员编辑。

## 本地 HTTP 联调

开发 API 和工作进程启动且已启用模型后，从仓库根目录执行：

```bash
HYHQ_EXPECT_RECOGNITION=1 node miniprogram/tests/live-smoke.js
HYHQ_EXPECT_RECOGNITION=1 HYHQ_TEST_IMAGE=/absolute/path/flower.jpg node miniprogram/tests/live-smoke.js
```

第一条用 1 像素图片验证低图质协议；第二条使用实际图片验证推理及页面数据。脚本创建并删除自己的开发账号，覆盖越权、结果展示和任务图片删除。它使用真实 HTTP 与 wx mock，不等于微信开发者工具/真机验收，也不替代分类准确率评估。

当前不开启垃圾识别、本地 LLM 或外部模型 API。

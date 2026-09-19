# HYHQ 海晏河清智慧平台

面向校园及周边河湖、公园的生态信息、科普学习与绿色游览微信小程序。

当前阶段：**M3 五类花卉识别完成本地收尾，环境数据继续使用模拟来源；M2/M4 的未验收项保持待办。**

## 已实现

- Django / DRF 后端、PostgreSQL 迁移和 Django Admin。
- 原生微信小程序五个入口，以及详情、个人记录和隐私说明页。
- 开发模拟登录、正式微信登录适配、会话撤销、用户权限和账号注销。
- 受控图片上传、去除元数据、鉴权下载、过期清理与头像管理。
- 示范校园 12 个地点、4 个监测站、3 类可重放模拟场景和 CSV 导入。
- 收藏、浏览和游览记录，以及识别任务队列与运行日志。
- 五类花卉模型的训练与评估流程、CPU ONNX 推理、受限工作进程和模型版本管理。
- 候选结果、低分/低图质提示、历史模型版本及五篇关联观察科普。

识别需要本机登记并启用模型制品。模型权重不提交 Git，没有模型时明确返回 `MODEL_NOT_CONFIGURED`。首版只覆盖雏菊类、蒲公英类、蔷薇属花卉、向日葵类、郁金香类；不区分具体物种或品种，高分也不能保证排除范围外图片。当前 v1 的验证集规则选出阈值 0，不按低分拒识，仅输出候选参考；低图质会显示无法确认。天气、空气与河湖数据均明确标记为模拟数据。

## 本地启动

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
# 默认使用 PostgreSQL，连接配置见 backend/.env。
scripts/dev.sh
```

没有 PostgreSQL 时可用 `scripts/dev.sh --sqlite` 做显式本地开发；正式验收使用 PostgreSQL。管理员通过 `scripts/manage.sh createsuperuser` 创建，后台入口为 `http://127.0.0.1:8000/admin/`。

微信开发者工具导入 `miniprogram/`，按该目录 README 配置 AppID 和后端地址。无需 npm 构建依赖。

识别模型的训练、登记、启用和回退步骤见 [图像推理说明](inference/README.md)。生产环境只需 CPU 推理依赖；训练在开发电脑执行。

## 项目文档

- [开发方案稿](docs/开发方案稿.md)：项目定位、范围、架构、数据设计、AI 方案与交付标准。
- [开发目标 TODO](docs/开发目标TODO.md)：分阶段任务、依赖关系、验收条件与完成记录。
- [后端接口与开发说明](backend/README.md)
- [小程序开发说明](miniprogram/README.md)
- [部署与运行模板](deploy/README.md)
- [M1 验证记录](docs/verification/M1验证记录.md)
- [图像推理与模型管理](inference/README.md)
- [M3 验证记录](docs/verification/M3验证记录.md)
- [M3 模型评估报告](inference/reports/M3模型评估报告.md)

## 开发顺序

当前开发顺序：M1 快照 → M3 图像识别。M1 快照为 `6375b0c`，远程仓库为 [gruTGU/HYHQ](https://github.com/gruTGU/HYHQ)。M2 的完整可视化、静态底图和其他未验收项仍保留在任务清单，不自动视为完成。

核心演示版优先保证完整操作流程和数据来源可追溯；本地 LLM 通过整机测试后再启用。

## 当前约束

- 用途：课程、毕业设计或比赛演示。
- 微信主体：个人。
- 计划服务器：腾讯云韩国首尔，Debian 13，2 核 CPU、4GB 内存、60GB 硬盘、IPv4。
- 域名：已有 `.xyz` 域名并完成 DNS 解析；HTTPS、备案状态、合法域名及真机访问能力待验证。
- 使用明确标注的示范校园；真实数据服务商暂缓接入，M3 使用公开花卉数据，校园实拍与范围外图片评估待补充。

M3 收尾通过 PostgreSQL 上的 **66 项后端测试、38 项前端测试**，以及真实 ONNX 推理、HTTP + wx mock 和模型回退联调。微信开发者工具、真机、首尔部署和公开发布条件尚未验收，不能从本机接口通过推定。

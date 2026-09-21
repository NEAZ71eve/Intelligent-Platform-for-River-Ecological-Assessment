# 本地启动与部署模板

当前使用示范校园与模拟生态观测，同时通过独立 `weatherdata` 模块提供五地点真实天气、空气质量与预警。天气和 LLM 均需要后端私有环境凭据；未启用时其他基础业务仍可运行。M3 图像识别需要单独训练/复制并启用 ONNX 制品；没有模型时仍能运行其他业务。默认数据库为 PostgreSQL；SQLite 仅作为显式选择的本机开发方式。

2026-09-21 已将运行代码 `d4d0bed` 部署到北京 Debian 13.2 实例，上轮源码与文档快照为 `c7bbdbf`。三板块问答、Markdown、品牌与导航、真实天气、管理统计审计和模拟批次维护均已纳入当前版本。数据库、依赖、API、花卉、河道、LLM 四个服务及每日私有数据清理计时器已配置并开机启用；DeepSeek 和和风 Key 仅在私有环境中配置，服务器真实调用成功。完整后端 377 项、小程序 257 项与实际管理流程 48 项通过，详见 [最新验证记录](../docs/verification/真实天气与管理验证记录.md) 和 [北京部署与回退](../docs/北京天气版本部署与回退.md)。实例按实测 2 核、约 2GB 内存配置；域名放行、HTTPS、微信 AppSecret、正式登录、完整手机交互、30 分钟负载与整机重启恢复仍待验收。

## 1. 开发依赖

- Python 3.12，与仓库 `backend/requirements.txt` 中锁定的版本一起使用。
- PostgreSQL 17；可使用已有服务或本目录 Docker Compose。
- Node.js 用于检查小程序 JavaScript；运行小程序需微信开发者工具。

以下命令均从仓库根目录执行，使用终端已提供的 `python3`。这只创建项目虚拟环境，不向系统 Python 安装依赖。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
```

配置文件为普通 `KEY=value`，由后端加载，不作为 shell 脚本执行。不要把真实密钥提交到版本库。环境变量优先于 `backend/.env`。

### PostgreSQL：默认路径

如果已安装 Docker Engine / Docker Desktop 与 Compose：

```bash
cp deploy/.env.example deploy/.env
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d db
docker compose --env-file deploy/.env -f deploy/docker-compose.yml ps
```

Compose 只启动 PostgreSQL，端口限定为 `127.0.0.1:5432`，数据存于命名卷。默认开发数据库与账号均为 `hyhq`，示例密码为 `hyhq-dev-only`，与后端开发模板一致。已有 PostgreSQL 则直接修改后端 `DATABASE_URL`。端口被占用时同步修改 `deploy/.env` 中的 `POSTGRES_PORT` 和后端 URL。

### SQLite：显式快速检查

没有 PostgreSQL 时可以执行：

```bash
scripts/dev.sh --sqlite
```

该参数只对本次进程启用 SQLite，文件位于 `backend/var/dev.sqlite3`。SQLite 不能验证 PostgreSQL 的锁行为；正式的迁移和权限验收仍以 PostgreSQL 测试记录为准。切换数据库不会自动迁移已有业务数据。

## 2. 初始化并启动

```bash
scripts/dev.sh
```

脚本顺序执行迁移、`seed_demo`、`seed_recognition_knowledge`、`seed_assessment_rules`、开发服务器，默认监听 `127.0.0.1:8000`。种子命令创建示范资料、五类花卉观察稿、河道教学规则和最近 48 小时正常场景模拟快照；重复执行保留管理员对文章的修改，同一个时间窗口不会重复生成同批数据。下一个小时重新执行会产生新的完整快照，查询默认选择一个成功批次，不把不同批次混成曲线。

另开终端创建自己的管理员，按提示输入凭据：

```bash
scripts/manage.sh createsuperuser
```

管理后台：`http://127.0.0.1:8000/admin/`。使用 SQLite 启动时，其他命令也需显式使用同一数据库：

```bash
HYHQ_USE_SQLITE=1 scripts/manage.sh createsuperuser
HYHQ_USE_SQLITE=1 scripts/manage.sh check
```

开发服务器用于本地联调。微信开发者工具的本地地址、模拟身份开关等配置见 `miniprogram/README.md`。开发模拟登录需要后端同时满足 `ENV=development`、`DJANGO_DEBUG=1`、`ALLOW_DEV_AUTH=1`；生产环境禁用模拟登录。M0 的真实微信登录、HTTPS 与合法域名验证仍待完成。

## 3. 模拟场景与历史导入

固定时间、种子与场景可重复演示：

```bash
scripts/manage.sh generate_simulation --scenario normal --start 2026-09-14T00:00:00+00:00 --hours 48 --seed 20260916
scripts/manage.sh generate_simulation --scenario turbidity --start 2026-09-14T00:00:00+00:00 --hours 48 --seed 20260916
scripts/manage.sh generate_simulation --scenario missing --start 2026-09-14T00:00:00+00:00 --hours 48 --seed 20260916
```

使用接口的 `source`、`simulation_run` 参数查看对应批次，参数契约见后端说明。以上均为模拟数据。生成当前最近 48 小时正常快照可以运行：

```bash
scripts/simulate-current.sh normal
```

`systemd/hyhq-simulation.timer` 是可选模板，当前未默认启用。连续每小时生成会保留多个完整批次，示范规模每批约 624 条观测。保留策略和手动预览确认维护已实现，见 [模拟批次维护](../backend/ecology/MAINTENANCE.md)；这不等于已经启用自动删除。长期生成调度仍需结合数据量、磁盘容量与维护安排单独验收。

历史 CSV 导入命令保留原观测时间并校验来源、单位和重复值：

```bash
scripts/manage.sh import_observations /absolute/path/observations.csv --dry-run
scripts/manage.sh import_observations /absolute/path/observations.csv
```

必需列：`station_code,metric_code,value,unit,observed_at,source_code`；可选列：`quality_status,simulation_run_id`。先在后台配置对应监测站、指标和合法来源，时间必须带时区；空值表示缺失，不写成 0。模拟来源必须关联相应成功批次。

## 4. 工作进程与验证

### 可选 DeepSeek 分区问答与图像解读

L01–L06 增加独立的 `llm` 应用，2026-09-21 版本继续增加三板块公开上下文与分区计账迁移，已部署北京，不需要额外 Python 依赖或 Redis。其他实例更新到当前代码时先运行 `scripts/manage.sh migrate`；不能只替换小程序页面而沿用旧接口/数据库。保持密钥只在后端环境中：

```dotenv
LLM_ENABLED=1
DEEPSEEK_API_KEY=在本机或服务器环境文件中填写
DEEPSEEK_MODEL=deepseek-flash
LLM_DAILY_TURN_LIMIT=5
```

修改环境后重启 API 和 LLM 工作进程，在 Django Admin 的「AI 解读网关 → 网关配置」中启用。环境总开关、凭据和后台开关缺一不可；未启用时原有生态与图像识别功能照常可用。密钥不从小程序或后台表单收集，不返回给客户端。

```bash
scripts/manage.sh run_llm_worker
```

该进程负责外部网络调用，使用独立队列，不占用识别模型的 CPU 执行锁。一个进程逐个处理，数据库同时限制多消费者并发。`recognition`（花卉及河道识别）、`explore`（生态导览及相关环境页面）、`learn`（科普智游）各自限制每账号每日五个成功回合，按北京时间计算；前台隐藏额度，限制仍由后端执行。后台另有全站尝试次数、token 预算、输出长度和超时限制。输入预算采用保守预留，实际用量与未知用量分别记录；它不代表 DeepSeek 账号中其他应用的总费用。

小程序在生态与科普相关页面提供悬浮问答入口，后端按当前模块核验公开资料；识别解读只能关联本人记录，可选发送净化图片。回答通过固定版本的本地 Markdown 解析器转为受限 `rich-text` 节点，支持标题、强调、列表、引用、代码和表格，不执行原始 HTML 或加载外链图片，无需额外 npm 构建。五个底栏入口保留文字并增加绿色图标，中央 AI 识别按钮为上凸圆形并预留安全区。

协议入口保留在登录页与“我的”，登录按钮旁说明继续注册或登录即同意；不再反复显示协议勾选框。选图、上传、附图和定位仍由用户主动操作，微信系统授权与删除/注销确认保留。此说明记录当前教学版行为，不代表正式法务及平台发布验收。

`systemd/hyhq-llm.service` 是可选模板；北京已适配为 `hyhq-v3-llm.service` 并启用，服务器环境与后台网关开关已打开，Key 仅在 root 所有、`0600` 的私有环境文件中。服务器一次真实问答成功，持续负载和手机公网使用仍待验收。停用功能时先关闭后台网关和环境开关，再重启相应进程；已发出的第三方请求无法撤回。

2026-09-20 首轮本机真实联通使用原生微信开发者工具 Stable 2.02.2608070、基础库 3.7.12 的小程序模拟器，文字/附图各调用一次，合计 3131 token；当时 Key 尚未配置到服务器，额度也仍按旧规则共享。这是历史结果，不代表当前分区额度或累计费用，详情见 [真实联通记录](../docs/verification/DeepSeek真实联通验证记录.md)。2026-09-21 北京另一次真实问答成功，815 输入 + 8 输出，共 823 token；测试身份与会话已删除，用量账本保留。

**2026-09-21 当前本机与北京分别执行：三个板块各每日五个成功回合；每部署全站每日 50 次尝试、100000 token、单次输出 600 token、并发 1。**最新完整验证为后端 377 项、前端 257 项与实际管理数据库流程 48 项通过，不包含完整手机或真实微信登录验收。当前运行路径、实际资源配置和账本回退边界见 [北京部署与回退](../docs/北京天气版本部署与回退.md)。

会话删除不返还已消耗额度；账号注销清除会话内容，用量账目保留不含正文/图片且解除用户关联的记录，用于当日预算。过期清理由现有 `cleanup_private_data` 命令处理。详细范围见 [LLM 实施计划](../docs/LLM实施计划.md)。

### 图像识别与通用检查

```bash
scripts/manage.sh run_recognition_worker --once
scripts/manage.sh run_assessment_worker --once
scripts/check.sh
# 仅 SQLite 的快速检查：
scripts/check.sh --sqlite
```

工作进程在没有模型时将识别任务标记为明确失败，`MODEL_NOT_CONFIGURED`。M3 的登记命令校验模型及其清单后方可启用；训练、导出、启停和回退见 [推理说明](../inference/README.md)。不要在服务器安装 PyTorch 训练依赖，服务端只安装后端锁定的 CPU 推理依赖。

复制制品时同时复制 ONNX 和 manifest，放入 `HYHQ_MODEL_ROOT` 指定目录。Web 进程只提供任务 API，独立消费者派生子进程进行推理。单机多个消费者共享同一个执行锁，初始并发固定为 1；不要将锁文件放在容器独立文件系统或不同路径。当前设计不支持多主机分布式消费。

子进程每次重新加载模型，便于限制执行时间和释放内存。因此报告中的纯模型前向延迟不代表任务端到端耗时。`HYHQ_RECOGNITION_TIMEOUT_SECONDS` 默认 10 秒，可设 1～60 秒；队列等待和上传另计。systemd 识别服务模板限制 CPU 和内存，需在目标 Debian 13 实测后验收。

`scripts/check.sh` 执行 Django 检查、迁移漂移检查和自动测试。使用 PostgreSQL 时测试账号需要创建测试数据库的权限；仅开发数据库用户可配置此权限，生产业务账号不要照搬。文件清理命令和接口完整说明见后端文档。

## 5. Debian 服务器部署模板与北京实例

本目录包含部署通用模板。北京实例已按实际目录、资源及生产环境适配，已执行步骤、备份与回退以 [北京天气版本部署与回退](../docs/北京天气版本部署与回退.md) 为准；以下模板路径不等于当前服务器路径。

- `Dockerfile`：可选的 API 镜像；从仓库根目录构建。
- `backend.production.env.example`：生产配置样例。
- `systemd/hyhq-api.service`：2 个 Gunicorn Web 进程，不加载模型。
- `systemd/hyhq-recognition.service`：单独队列消费进程。
- `systemd/hyhq-assessment.service`：河道检测消费进程，与花卉消费者共享 `backend/var/recognition.lock`。
- `systemd/hyhq-llm.service`：可选外部问答消费进程；北京已适配为 v3 服务并启用。
- `systemd/hyhq-simulation.*`：可选小时模拟任务。
- `nginx.conf.example`：HTTPS、反向代理与公开静态文件。

模板假定源码放在 `/srv/hyhq`、运行账号为 `hyhq`、环境文件为 `/etc/hyhq/backend.env`、数据库在本机。安装前替换域名、路径、随机密钥和数据库密码，配置真实证书，并根据自己的系统创建服务账号与目录权限。不要将开发密码用于外部服务。

河道权重的固定版本获取和登记见 [河道推理说明](../inference/river/README.md)。它通过 `DetectionModel` 独立启停，不替换花卉 `ModelVersion`。迁移后运行 `seed_assessment_rules --activate`，登记模型再启动 assessment 服务；只启用 API 不会执行后台评估。初始化命令保留已有的活动规则，后续切换在管理后台进行。两个推理服务串行争用同一个锁，不会同时加载两份任务模型进行前向。河道超时配置 `HYHQ_ASSESSMENT_TIMEOUT_SECONDS` 默认为 10 秒。北京实际为 2 核 / 约 2GB，API 使用 1 个 worker；两类真实推理与内部 HTTP 已通过，正式 30 分钟负载和整机重启恢复仍待验收。

部署顺序：准备 PostgreSQL 与独立应用账号 → 安装锁定依赖 → 配置生产环境变量 → 迁移数据库 → `collectstatic --noinput` → 创建管理员 → 配置 Nginx/证书 → 启用 API 服务 → 验证真实微信链路。

生产启动前执行 `manage.py check --deploy`。服务账号需能写 `backend/var`；上传文件始终经鉴权接口访问，Nginx 不提供公开 media 目录。`TRUST_PROXY_HTTPS=1` 只适用于前端代理会覆盖协议头的部署；模板代理会覆盖该头。

首次迁移、`collectstatic` 和创建管理员属于部署操作，不能在每个 Web 进程启动时重复执行。数据库与上传目录应另行备份；systemd / Docker 模板并不代表 M4 的备份、恢复和负载验收完成。

## 6. 当前 macOS 验证运行时

当前工作机最初未预装 Docker 或 PostgreSQL。为实际验证 PostgreSQL 迁移，已从 [PostgreSQL 官方源码目录](https://ftp.postgresql.org/pub/source/v17.9/) 下载 17.9 源码并校验随包 SHA-256，按 [官方编译说明](https://www.postgresql.org/docs/17/install-make.html) 编译到项目 `.runtime/postgresql`，目前本机验证使用该实例；关闭 ICU/readline 仅用于本机测试，不影响数据库业务字段。

验证实例数据位于 `.runtime/postgres-data`，仅监听 `127.0.0.1:55432`；本机示例连接为：

```text
postgresql://hyhq:hyhq-dev-only@127.0.0.1:55432/hyhq
```

该目录与凭据仅供开发，不提交版本库，不安装到系统。使用时覆盖默认 URL：

```bash
DATABASE_URL=postgresql://hyhq:hyhq-dev-only@127.0.0.1:55432/hyhq scripts/dev.sh
```

已初始化的实例可用以下命令重启或停止，不删除数据：

```bash
.runtime/postgresql/bin/pg_ctl -D .runtime/postgres-data -l .runtime/postgres.log -o '-h 127.0.0.1 -p 55432 -k /Users/liu/Documents/ChatGPT/Seoul001/.runtime/postgres-socket' -w start
.runtime/postgresql/bin/pg_ctl -D .runtime/postgres-data -m fast -w stop
```

这里的 socket 路径是当前工作机路径，移动项目后要替换。这些命令只操作本机数据库；北京部署状态独立见 [北京天气版本部署与回退](../docs/北京天气版本部署与回退.md)。

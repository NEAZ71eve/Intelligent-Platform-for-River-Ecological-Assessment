# M1 本地启动与部署模板

本阶段使用示范校园与模拟环境数据。无需天气服务密钥、图像模型权重或 LLM。默认数据库为 PostgreSQL；SQLite 仅作为显式选择的本机开发方式。首尔服务器、域名、证书和微信真机链路尚未部署或验收。

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

脚本顺序执行迁移、`seed_demo`、开发服务器，默认监听 `127.0.0.1:8000`。种子命令创建示范资料和最近 48 小时正常场景模拟快照；同一个时间窗口重复执行不会重复生成同批数据。下一个小时重新执行会产生新的完整快照，查询默认选择一个成功批次，不把不同批次混成曲线。

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

`systemd/hyhq-simulation.timer` 是可选模板，本阶段不默认启用。连续每小时生成会保留多个完整批次，当前示范规模每批约 624 条观测；M4 完成保留策略后再启用长期调度。

历史 CSV 导入命令保留原观测时间并校验来源、单位和重复值：

```bash
scripts/manage.sh import_observations /absolute/path/observations.csv --dry-run
scripts/manage.sh import_observations /absolute/path/observations.csv
```

必需列：`station_code,metric_code,value,unit,observed_at,source_code`；可选列：`quality_status,simulation_run_id`。先在后台配置对应监测站、指标和合法来源，时间必须带时区；空值表示缺失，不写成 0。模拟来源必须关联相应成功批次。

## 4. 工作进程与验证

```bash
scripts/manage.sh run_recognition_worker --once
scripts/check.sh
# 仅 SQLite 的快速检查：
scripts/check.sh --sqlite
```

M1 工作进程在没有模型时将识别任务标记为明确失败，`MODEL_NOT_CONFIGURED`，不产生模拟植物预测。后台模型登记不等于接入真实推理，M3 接入说明见 `inference/README.md`。

`scripts/check.sh` 执行 Django 检查、迁移漂移检查和自动测试。使用 PostgreSQL 时测试账号需要创建测试数据库的权限；仅开发数据库用户可配置此权限，生产业务账号不要照搬。文件清理命令和接口完整说明见后端文档。

## 5. Debian / 首尔服务器部署模板

本目录包含可供 M4 使用的模板，尚未在 Debian 13 / 首尔实例执行：

- `Dockerfile`：可选的 API 镜像；从仓库根目录构建。
- `backend.production.env.example`：生产配置样例。
- `systemd/hyhq-api.service`：2 个 Gunicorn Web 进程，不加载模型。
- `systemd/hyhq-recognition.service`：单独队列消费进程。
- `systemd/hyhq-simulation.*`：可选小时模拟任务。
- `nginx.conf.example`：HTTPS、反向代理与公开静态文件。

模板假定源码放在 `/srv/hyhq`、运行账号为 `hyhq`、环境文件为 `/etc/hyhq/backend.env`、数据库在本机。安装前替换域名、路径、随机密钥和数据库密码，配置真实证书，并根据自己的系统创建服务账号与目录权限。不要将开发密码用于外部服务。

部署顺序：准备 PostgreSQL 与独立应用账号 → 安装锁定依赖 → 配置生产环境变量 → 迁移数据库 → `collectstatic --noinput` → 创建管理员 → 配置 Nginx/证书 → 启用 API 服务 → 验证真实微信链路。

生产启动前执行 `manage.py check --deploy`。服务账号需能写 `backend/var`；上传文件始终经鉴权接口访问，Nginx 不提供公开 media 目录。`TRUST_PROXY_HTTPS=1` 只适用于前端代理会覆盖协议头的部署；模板代理会覆盖该头。

首次迁移、`collectstatic` 和创建管理员属于部署操作，不能在每个 Web 进程启动时重复执行。数据库与上传目录应另行备份；systemd / Docker 模板并不代表 M4 的备份、恢复和负载验收完成。

## 6. 当前 macOS 验证运行时

当前工作机未安装 Docker 或 PostgreSQL。为实际验证 PostgreSQL 迁移，已从 [PostgreSQL 官方源码目录](https://ftp.postgresql.org/pub/source/v17.9/) 下载 17.9 源码并校验随包 SHA-256，按 [官方编译说明](https://www.postgresql.org/docs/17/install-make.html) 编译到项目 `.runtime/postgresql`；关闭 ICU/readline 仅用于本机测试，不影响数据库业务字段。

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

这里的 socket 路径是当前工作机路径，移动项目后要替换。Codex 沙箱不允许数据库共享内存和本机 socket 连接，本次初始化、启动和数据库测试需要经批准的本机执行；这不等于远程服务器已部署。

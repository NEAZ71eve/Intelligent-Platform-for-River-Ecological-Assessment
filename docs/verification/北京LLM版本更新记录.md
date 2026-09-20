# 北京服务器 M2 + LLM 版本更新记录

日期：2026-09-20。部署源码基线：`26fe5441af8f991a233528c62d624d398ca52987`。

**服务器已更新并通过内部验证；DeepSeek Key 保持空白，LLM 功能关闭，LLM 工作进程未启用。** 服务器没有接收本机 `.env`、本机 DeepSeek Key 或 SSH 私钥。本机真实 API 测试属于独立环境，不代表服务器开通了 LLM。

## 1. 发布与运行状态

| 项目 | 本次结果 |
| --- | --- |
| 发布目录 | `/srv/hyhq-releases/26fe544` |
| 新生产数据库 | `hyhq_26fe544`，从维护窗口内的旧库一致备份恢复 |
| 新环境文件 | `/etc/hyhq/26fe544.env`，root 所有，权限 `0600` |
| API | `127.0.0.1:18080`，1 个 Gunicorn worker、1 个线程 |
| API / 花卉 / 河道服务 | `hyhq-v3-api`、`hyhq-v3-recognition`、`hyhq-v3-assessment` 均 active、enabled，检查时 NRestarts 均为 0 |
| LLM 服务 | `hyhq-v3-llm.service` 已适配新目录与环境文件；disabled、inactive |
| 清理 | `hyhq-v3-cleanup.timer` 已同步新发布；真实执行 cleanup service 成功，退出码 0 |
| 旧发布保留 | `/srv/hyhq-releases/f31c55f`、`hyhq_f31c55f`、`/etc/hyhq/f31c55f.env` 原封保留 |
| 未触碰进程 | 原先监听 `127.0.0.1:18000` 的独立进程仍在 |

运行环境沿用 Debian 13.2、Python 3.13.5、PostgreSQL 17；实际资源为 2 核、约 2 GB 内存。依赖按仓库锁定版本通过腾讯 HTTPS PyPI 镜像安装；`pip check` 通过。没有安装 Redis、训练框架或本地 LLM。

生产环境文件及三个实际运行进程的 `/proc/.../environ` 均经过只输出布尔结果的检查，确认：

```dotenv
ENV=production
DJANGO_DEBUG=0
ALLOW_DEV_AUTH=0
LLM_ENABLED=0
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-flash
LLM_DAILY_TURN_LIMIT=5
```

数据库中的 `GatewayConfig.enabled=False`。这些设置没有从本机测试环境复制。

## 2. 更新内容与步骤

1. 仅使用 `git archive 26fe544` 上传源码；归档成员检查确认没有 `.env`、私钥、`.runtime` 或虚拟环境。
2. 新建发布目录和虚拟环境，先完成依赖安装；这一步旧服务继续运行。
3. 停止 API 新写入及清理定时器，确认两类图像任务没有 queued/running 后停止消费者。
4. 备份旧数据库、私有文件、代码、生产环境、systemd 与 Nginx 配置；恢复到独立新库。
5. 从服务器旧发布复制模型和私有文件；模型文件摘要与原版一致，没有训练、替换权重或切换活动版本。
6. 生成独立生产环境，执行迁移、收集静态文件及幂等种子更新。
7. 将既有 v3 单元指向新发布、新环境；Nginx 仅更新静态目录，API 仍使用回环 18080，原代理头和网络边界保持不变。
8. 启动三个业务服务并验证，恢复清理定时器；LLM 单元安装后保持停用。

源码归档 SHA-256：

```text
7482b7fc049882b8a1f25e224bff725cf3ed988ea0abedfebf6bb555a7c01b6e
```

新增迁移：

- `activity.0002_feedback_resolution`：反馈回复、处理人、处理时间。
- `llm.0001_initial`：网关配置、私人会话、回合及独立用量账本。

两项迁移均成功。`seed_demo --no-observations` 更新未修改的地图占位及缺失示范资料，不新增模拟观测批次；`seed_recognition_knowledge` 幂等核对，未覆盖管理员修改。最终公开示范资料为 **12 个地点、1 条 6 节点路线、8 篇科普**。原有模拟数据可用于四项水指标趋势。

模型摘要：

| 模型 | SHA-256 |
| --- | --- |
| 五类花卉 EfficientNet-B0 | `01d132fd6fc189adf636060adbe633de57343977d124590e944150f3084fac8f` |
| 河道漂浮物 YOLO | `96fc7178c28f1eb29bae9703f440d6bda9c041433edb3e335691f38a5ee6da6c` |

代码、虚拟环境和模型由 root 持有；`backend/var` 由 hyhq 持有。静态文件仅收集期间开放写入，完成后恢复 root 所有。

## 3. 验证证据

### 3.1 服务器完整后端回归

在服务器 Python 3.13 环境创建独立测试角色及独立测试库，强制空 Key、关闭 LLM，以低 CPU 优先级运行：

- **283 项 Django 测试全部通过，32.440 秒。**
- 临时角色 `hyhq_validation_26fe544`、底库及测试库均已清除。
- 生产角色 `hyhq` 的 `rolcreatedb=false`，没有为测试提升生产数据库权限。
- 测试中上游响应通过桩替代，未进行真实 DeepSeek 外发。

服务器日志：`/var/log/hyhq-26fe544-tests.log`。本机副本：`.runtime/beijing-26fe544/backend-tests.log`。

### 3.2 真实生产 HTTP + 两套模型

运行现有 `production-smoke.py --trusted-loopback --check-low-quality`：

- **71 次 HTTP 请求通过，总计 5.259 秒；单请求最大 67ms。**
- 实际花卉推理 417ms；河道推理 568ms，检测到 24 个实验漂浮物框。
- 一像素低质量图片在两套模型中均得到不确定结果。
- 用户间记录/私有图片隔离、图片复用冲突、删除记录连同原图和缩略图、退出/注销撤销会话均通过。
- 生产开发登录返回 `DEV_AUTH_DISABLED`。
- 专属临时测试账号、任务及图片清理检查为 `verified`。

测试花卉来自既有公开 TensorFlow flower_photos 样例；河道图为朋友仓库已有训练拼图。它们只用于验证流程，不用于评价模型准确率。临时上传至服务器的两张测试样例已删除。

本机证据：`.runtime/beijing-26fe544/production-smoke.json`。

### 3.3 M2 与关闭状态下的 LLM

另外 **14 次真实生产 HTTP 请求通过**：

- 静态地图路径、12 地点、6 个有序路线节点及相关科普。
- 水质四项指标的模拟趋势与有效数据统计。
- 新反馈结构的提交、列表及删除；收藏与账号清理。
- 游客 `GET /api/v1/llm/status/`：`enabled=false`、`quota=null`、`daily_limit=5`。
- 登录用户读取自己的额度正常；`POST /api/v1/llm/sessions/` 返回 **503 / `LLM_DISABLED`**，没有生成会话、任务或用量账目。

本机证据：`.runtime/beijing-26fe544/m2-disabled-smoke.json`。

### 3.4 服务与维护检查

- `nginx -t` 通过；三个业务服务 NRestarts 均为 0。
- 清理命令 dry-run 通过，实际清理 service 的 `Result=success`、`ExecMainStatus=0`；timer 仍启用。
- 检查时 API / 花卉 / 河道 cgroup 峰值分别约 111 / 165 / 196 MiB；整机可用内存约 961 MiB，磁盘剩余约 33 GB。
- `check --deploy` 没有错误；保留原有 HSTS 子域名与 preload 两项提示，没有为消除提示改变未验收的 HTTPS 范围。

本机最终检查记录：`.runtime/beijing-26fe544/final-check.log`。

## 4. 备份与回退

维护窗口备份目录：

```text
/var/backups/hyhq/pre-26fe544-20260920T150706Z
```

目录权限为 `0700`，其中数据库、私有文件、代码/配置归档、旧环境、旧服务及 Nginx 文件均为 `0600`。旧 release、旧数据库和旧环境仍独立保留。10 个备份文件同时复制到本机受限目录 `.runtime/remote-backups/beijing-pre-26fe544-20260920T150706Z/`，逐文件 SHA-256 与服务器一致；本机目录也是 `0700`，文件为 `0600`，且已确认被 Git 忽略。备份不进入 Git。

回退应使用 **旧代码、旧环境、旧数据库的完整组合**。新反馈列 `reply` 为 NOT NULL，Django 默认值不是保证长期存在的数据库默认值；不能把旧代码直接切向新 schema。也不要直接反向执行 `llm zero`，那会删除会话和账本。

以下回退命令是操作说明，**本次没有执行回退**。以 root 在服务器执行；先保留升级后新增数据，再恢复旧单元和静态目录：

```bash
rollback_snapshot="/var/backups/hyhq/rollback-26fe544-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 0700 "$rollback_snapshot"
systemctl stop hyhq-v3-api hyhq-v3-recognition hyhq-v3-assessment hyhq-v3-cleanup.timer hyhq-v3-cleanup.service
systemctl disable --now hyhq-v3-llm.service
runuser -u postgres -- pg_dump -Fc hyhq_26fe544 > "$rollback_snapshot/hyhq_26fe544.dump"
tar -czf "$rollback_snapshot/private-files.tar.gz" -C /srv/hyhq-releases/26fe544/backend var/private
chmod 0600 "$rollback_snapshot"/*

backup_dir=/var/backups/hyhq/pre-26fe544-20260920T150706Z
for service in hyhq-v3-api hyhq-v3-recognition hyhq-v3-assessment hyhq-v3-cleanup; do
  install -m 0644 "$backup_dir/$service.service" "/etc/systemd/system/$service.service"
done
install -m 0644 "$backup_dir/hyhq-v3-cleanup.timer" /etc/systemd/system/hyhq-v3-cleanup.timer
install -m 0644 "$backup_dir/nginx-hyhq.conf" /etc/nginx/sites-available/hyhq.conf
systemctl daemon-reload
nginx -t
systemctl start hyhq-v3-api hyhq-v3-recognition hyhq-v3-assessment
systemctl reload nginx
systemctl start hyhq-v3-cleanup.timer
```

逐步核对返回结果；如未来另行完成了 HTTPS 配置，应保留新证书与 TLS 配置，仅调整上游/静态路径，不用早期站点备份覆盖后续配置。新库切换后产生的数据不会自动合并回旧库，应保留两边并另行核对。

## 5. 本次未进行的事项

- 未把服务器 LLM 打开，未向服务器配置真实 DeepSeek Key。
- 未申请或更新证书、未修改备案设置、未尝试绕过云厂商拦截。
- 所有业务冒烟使用可信回环 HTTP，`public_https_verified=false`；这不是公网 HTTPS 或微信真机验收。
- 未做 30 分钟负载、整机重启验收或长期容量验证。

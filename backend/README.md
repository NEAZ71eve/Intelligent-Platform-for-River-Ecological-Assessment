# HYHQ 后端开发与 API

## 运行与范围

本机使用 Python 3.12；北京服务器使用 Python 3.13。2026-09-21 已部署运行代码 `d4d0bed`，包含三板块 AI、真实天气、管理统计审计与模拟批次维护；上轮源码和文档快照为 `c7bbdbf`。数据库、依赖、四个服务和私有数据清理计时器已配置，两个外部 API 已完成服务器真实调用验证，详见 [当前部署与回退](../docs/北京天气版本部署与回退.md)。锁定依赖见 `requirements.txt`。数据库默认 PostgreSQL；`HYHQ_USE_SQLITE=1` 仅用于显式本地开发。设置与私有文件位于后端目录，真实 `.env`、数据库、用户文件、模型和本地运行时均不提交。

从仓库根目录使用 `scripts/manage.sh` 执行命令，该脚本会切换到 backend 工作目录，确保 Django 能正确发现测试。

```bash
scripts/manage.sh migrate
scripts/manage.sh seed_demo
scripts/manage.sh seed_recognition_knowledge
scripts/manage.sh seed_assessment_rules --activate
scripts/manage.sh createsuperuser
scripts/manage.sh runserver 127.0.0.1:8000
# 另一个终端运行任务消费者：
scripts/manage.sh run_recognition_worker
```

真实微信身份适配已实现；北京已配置 AppID，AppSecret 仍待补齐，公网域名放行、HTTPS、合法域名和真实微信登录验收尚未完成。开发模拟登录必须同时开启 `ENV=development`、`DJANGO_DEBUG=1`、`ALLOW_DEV_AUTH=1`，生产即使误开第三项也不提供该接口。模拟身份不能替代真实用户认证。

## 响应、鉴权与权限

所有 API 使用 `/api/v1/` 和尾部 `/`。

```json
{"data": {"status": "ok"}, "request_id": "..."}
```

列表返回 `data` 数组和 `meta`，包含 `count`、`page`、`page_size`、`next`、`previous`。默认每页 20、最多 100 条。观测查询有独立的来源、时间及点数限制，详见 [生态模块说明](ecology/README.md)。

```json
{"error": {"code": "AUTH_REQUIRED", "message": "登录已过期，请重新登录", "details": {}}, "request_id": "..."}
```

私有接口使用 `Authorization: Bearer <token>`。服务端只保存令牌的 SHA-256 摘要；新登录会撤销该账号的旧业务会话，有效期 7 天。退出、到期、停用和注销都会阻止旧令牌继续访问。令牌不能放进图片 URL 查询参数。

| 接口 | 方法 | 权限与用途 |
| --- | --- | --- |
| `health/` | GET | 公开；数据库连通性、模拟模式、功能开关 |
| `auth/dev/` | POST | 仅开发；`device_id` 为 16～128 位字母/数字/下划线/连字符 |
| `auth/wechat/` | POST | 接收临时 `code`，后端固定调用微信 code2Session |
| `auth/logout/` | POST | 登录用户，撤销当前会话 |
| `me/` | GET/PATCH/DELETE | 当前用户；可修改 `nickname`、`record_history`、`avatar_asset_id` |
| `regions/`、`places/`、`maps/`、`stations/` | GET | 公开；区域、地点、静态底图与版本绑定点位；站点可按 `region,kind,place,water_body` 筛选 |
| `metrics/`、`data-sources/`、`observations/` | GET | 公开；指标、已启用来源及有界原始观测样例 |
| `observation-series/` | GET | 公开；单站多指标、单来源/成功单批次的完整窗口聚合，最长 31 天、最多 50000 条原始记录及每指标 240 个桶 |
| `simulation-runs/` | GET | 公开成功批次目录；按 `region,station,source,scenario` 筛选，标准分页 |
| `weather/`、`air-quality/`、`weather-alerts/` | GET | 公开；保留的模拟接口，旧预警接口明确返回未接入状态 |
| `weather-data/locations/`、`weather-data/summary/` | GET | 公开；独立的真实天气、空气质量与预警，详见 [和风天气接入](weatherdata/README.md) |
| `dashboard/` | GET | 公开；按单一来源/批次读取指标 |
| `contents/`、`content-tags/`、`routes/` | GET | 公开；科普组合筛选/标签目录，路线只展示公开节点，详见 [知识模块](knowledge/README.md) |
| `places/{id}/`、`contents/{id}/`、`routes/{id}/` | GET | 公开详情 |
| `uploads/` | POST | 登录；multipart `file`，`purpose=avatar/recognition` |
| `uploads/{id}/content/?variant=thumbnail` | GET | 仅所有者；variant 也可为 original |
| `uploads/{id}/` | DELETE | 仅所有者 |
| `recognition-jobs/` | GET/POST | 仅本人；创建参数 `asset_id`，同一图片幂等 |
| `recognition-jobs/{id}/` | GET/DELETE | 仅本人；删除任务同时删除其图片 |
| `assessment-jobs/`、`assessment-jobs/{id}/` | GET/POST、GET/DELETE | 仅本人；河道图像观察任务和私有历史 |
| `water-bodies/` | GET | 公开；已发布河流/湖泊，可按 `region` slug 或 UUID 筛选 |
| `nearby-water-bodies/` | GET | 公开；同坐标系的 2km 内水体建议，无匹配返回 null |
| `favorites/`、`histories/` | GET/POST | 仅本人；参数 `place_id` 或 `content_id` 二选一 |
| `favorites/{id}/`、`histories/{id}/` | DELETE | 仅本人 |
| `visits/`、`visits/{id}/` | GET/POST、DELETE | 自记游览；同一用户/地点/日期去重，无定位核验 |
| `feedback/`、`feedback/{id}/` | GET/POST、DELETE | 仅本人；最多 1000 字，答复/状态/处理时间只读，详见 [个人记录与反馈](activity/README.md) |

科普、路线与个人业务的专项历史验证见 [M2-B01～B04 记录](../docs/verification/M2业务闭环验证记录.md)，包含用户侧和后台答复实际 HTTP；相关迁移已纳入北京当前部署。最新完整验证为 PostgreSQL 后端 377 项、小程序 257 项及实际管理数据库流程 48 项通过，见 [真实天气与管理验证记录](../docs/verification/真实天气与管理验证记录.md)。

首页真实天气覆盖天津市、天津工业大学、天津师范大学、天津理工大学与北京市，校园入口代表附近天气网格。数据存于独立 `weatherdata` 表，不写入模拟观测历史。本机 100 次、北京 29,900 次分配共同约束本项目每月最多 30,000 次请求，另有滚动 31 天限制；费用账本必须连续保留。管理统计与审计见 [通用模块说明](common/README.md)，模拟保留策略和手动预览确认维护见 [批次维护说明](ecology/MAINTENANCE.md)。

公开读取不等于管理权限。内容管理员需显式授予 Django 模型权限；上传图片不通过公开 media 路由暴露。生产单层可信 Nginx 代理开启 `TRUST_PROXY_HTTPS=1` 后按其覆盖的 X-Forwarded-For 区分限流来源；不能直接暴露绕过代理的应用端口。

## M2 生态展示数据契约

`observation-series/` 必填 `station`（代码或 UUID），`region` 默认 `demo-campus`；可选 `metrics` 为 1～9 个不重复的适用指标代码。`source_type` 默认 `simulation`，`source` 必须与来源类型匹配；存在多个候选来源时必须显式选择。模拟查询固定一个成功批次，支持 `scenario` 与 `simulation_run`，不会拼接多个批次；非模拟来源不接受模拟批次/场景参数。

时间使用 `hours=1..744`（默认 48），或成对的带时区 `start/end`，两种方式互斥。区间为 `[start,end)`，最长 31 天。`max_points=1..240`（默认 120）限制每指标的时间桶数量，聚合覆盖整个窗口；原始记录总数超过 50000 时拒绝查询，不截断冒充全量。小时模拟页面采用整点批次窗口和每小时一个桶。

响应包含 `source,source_type,is_simulated,simulation_run_id,window,bucket_seconds,series`。`latest` 保留最后一条原始记录的实际时间与质量状态；`summary` 只对有效原始值统计最小、最大与均值，计数按原始记录而非桶数计算。空桶、缺失或存疑桶的曲线值为 `null`；零值为有效数值。混合桶保留有效样本计数与极值，但有缺失/存疑即形成断线。`simulation-runs/` 的 `counts` 仅统计本次区域/站点筛选中可公开的记录。

`water-bodies/?region=...` 与 `stations/?region=...&water_body=<uuid>` 支持详情页进入相应水体和监测站；隐藏地点、水体和停用站点不会通过观测与批次目录泄露。来源目录路径为 `data-sources/`。

示范静态图 `/assets/maps/demo-campus-v1.png` 为 HYHQ 原创虚构布局，固定为 `demo-campus`、v1、1000×700。已有点位的底图不能原地改尺寸、所属区域、版本或替换图片 URL，需新版本重新布点；初始化保留管理员编辑。完整参数表、批次目录及统计语义见 [生态模块说明](ecology/README.md)。

## 图片与记录生命周期

### 外部 AI 解读

LLM 网关使用独立的私人会话、问答任务与无正文用量账目。新增接口为 `llm/status/`、`llm/sessions/`、`llm/sessions/{id}/`、`llm/sessions/{id}/turns/` 和 `llm/turns/{id}/`，均使用现有响应封装与分页；除能力状态外需 Bearer 登录，且仅能访问本人数据。

三个板块分别按账号与北京时间日期计数：`recognition`（花卉和河道共享）、`explore`（生态导览）、`learn`（科普智游）。每板块每天最多 5 个成功回合；每板块提交次数另受 `per_user_attempt_limit` 约束。并发入队预占额度，失败释放成功回合，删除会话不重置账本；跨板块每用户同时最多 1 个进行中任务，全站预算继续共享。请求 UUID `request_id` 幂等，复用不同内容返回冲突。外部调用不自动重试。

`GET llm/status/?scope=explore` 返回该板块能力、真实模型名与后台额度结构；小程序不显示额度，仅在发送收到 `LLM_DAILY_LIMIT` 后显示该板块今日使用上限提示。非法 scope 拒绝，不静默退回其他板块。

创建识别会话保留旧入口：

```json
{"scope":"recognition","recognition_job_id":"<本人已完成任务 UUID>","include_image":false}
```

河道使用 `assessment_job_id`，两种 ID 只选一个。公开资料会话只传来源 ID：

```json
{"scope":"learn","source_type":"content","source_id":"<已发布文章 UUID>"}
```

`explore` 允许 `region/place/water`，`learn` 允许 `region/content/route`。不接受客户端正文或 system prompt，非识别会话不允许附图。返回值增加 `scope/source_type/source_id/source_region_id`，保留旧 `kind` 和识别任务 ID；公开资料当前正文及关联信息由服务端每轮重新读取，正文节选、模拟来源与缺测状态显式标记。来源下架、过期、删除以及等待回复时资料变化都重新校验；旧上下文的回答不会覆盖新资料。

注册/登录处统一说明协议，创建会话不再要求重复传递 `consent_version`，也不因旧会话说明版本变化弹确认。创建会话本身不请求 DeepSeek，用户仍需主动发送。识别附图默认关闭；主动开启后必须有有效原图，发送前缩小并去除元数据，过期不改用缩略图。

升级需执行 `llm` 的新增 scope 迁移；旧花卉/河道会话及已删除会话的账目全部归入 `recognition`，保留历史成功计数。公开来源会话最长保留 30 天；删除或下架主源后不能继续访问，账本继续保留当天使用量。

环境读取和运行步骤见 [部署说明](../deploy/README.md)，最新拆分见 [AI 分区互动计划](../docs/AI分区互动实施计划.md)，原始 L01–L06 记录保留为历史证据。

### 原有图片与识别记录

- 仅接受实际可解码的 JPEG、PNG、静态 WebP，输入最多 5MB、2000 万像素。
- 重建像素并转为 JPEG，移除 EXIF/GPS 等元数据；保存最大边 2048 的原图和 480 的缩略图。
- 识别原图 24 小时，识别图片和任务记录 30 天；已设为头像的缩略图保留到替换/注销，未使用头像上传 24 小时。
- 私有图片过期后下载接口立即拒绝，清理命令负责物理文件和记录回收。
- 注销会删除账号及关联记录、图片，审计中的操作者引用匿名化；日志只记录必要状态和计数，不写令牌或微信返回体。

```bash
scripts/manage.sh cleanup_private_data --dry-run
scripts/manage.sh cleanup_private_data
```

北京已启用每日私有数据清理计时器；其他新部署仍需单独配置调度。模拟历史批次已有保留策略和手动预览确认维护工具，尚未安排模拟批次定时删除，详见 [批次维护说明](ecology/MAINTENANCE.md)。

## M3 识别任务与模型版本

队列全局上限 20，通过数据库共享锁行控制入队。任务有 queued/running/succeeded/failed 状态，排队超过 300 秒会由消费者标记失败。单机文件锁覆盖领取到保存结果，多消费者仍只执行一个任务；推理在没有数据库凭据的独立子进程内运行。执行默认 10 秒超时，超时会终止并等待子进程回收。消费者意外退出后，新消费者取得执行锁时会将遗留的 running 任务终止为明确失败。

登记/启用模型后，消费者校验 SHA-256、输入预处理和五类标签，使用 ONNX Runtime CPU 推理。`result.decision` 为 `recognized` 或 `uncertain`；包含候选列表、阈值、模型版本和范围说明。低图质图片返回 `uncertain`、`reason=LOW_IMAGE_QUALITY` 和空候选；分数低于所用阈值时返回 `LOW_CONFIDENCE`。当前 v1 的验证集规则选出阈值 0，未启用低分拒识，正常图片均返回候选参考；低分分支另有配置测试。任务状态 succeeded 代表流程完成，并不意味着结论一定正确。

候选 `score` 是未经校准的模型分数，不是正确率。该模型只在五类公开花卉数据上训练，可能把未知对象高分误判为已知类别。`content_id` 仅链接对应 `plant_label` 的已发布科普文章，未发布内容不会返回链接。

`health/` 的 `recognition` 返回是否启用、模型名称/版本、类别、范围和阈值，不暴露制品路径；`features.recognition` 与之同步。没有启用模型时返回 `MODEL_NOT_CONFIGURED`，缺失/损坏模型或执行错误返回具体错误码，不生成固定答案。

同一时刻最多启用一个模型版本。登记、启停与回退见 [推理说明](../inference/README.md)。历史任务保存当时的模型配置快照，停用、切换或删除登记不改写既有结果；已用于任务的版本不能修改配置，需登记新版本。生产实例只支持同一主机和共享锁路径，不支持分布式消费。

## 河道图像观察

通过 `assessment-jobs/` 提交 `asset_id`，可选 `water_body_id`。定位字段为成对的 `latitude`、`longitude` 和 `coordinate_system`（`GCJ02` 或 `WGS84`）；不定位时全部省略。坐标只用于当前账号的记录和附近建议，不作为到访证明。示范水体没有真实坐标时可以手动选择，也可以不关联水体。

`nearby-water-bodies/` 使用上述三个定位查询参数，只匹配同坐标系、公开水体关联的有效水站。接口不会替用户确认河段，客户端取得建议后由用户选择关联。后台不会把 WGS84 与 GCJ02 数字直接混算距离。

河道与花卉使用独立的模型登记及消费者，但共用 20 个排队/运行任务的容量和同一主机推理锁。同一上传资产不能跨两类任务重复使用，需重新上传；删除任务会删除其私有图片。定位和评估记录保留 30 天，原图 24 小时，均纳入 `cleanup_private_data` 和账号注销。

模型登记和启停见 [河道模型说明](../inference/river/README.md)。初始化教学规则、启动消费者：

```bash
scripts/manage.sh seed_assessment_rules --activate
scripts/manage.sh run_assessment_worker
```

规则在入队时保存快照；模型在领取任务时保存快照。已使用的版本不能原地改写配置，应登记新版本。空检测、低图质返回 `decision=uncertain`、`score=null`，缺少模型则任务失败。模型当前只开放漂浮物实验检测；检测框并集占整张图片的比例用于透明教学规则，不能视为水面污染比例或官方水质指标。

`health/` 的 `assessment` 和 `features.assessment` 公布河道模型状态，与花卉模型分别管理。`HYHQ_ASSESSMENT_TIMEOUT_SECONDS` 默认 10 秒（1～60 秒），`HYHQ_ASSESSMENT_MODEL_ROOT` 默认沿用 `HYHQ_MODEL_ROOT`。两类消费者均通过受限子进程执行推理，工作进程未启动时任务不会自动被 Web 服务处理。

## 检查

```bash
scripts/check.sh
cd miniprogram # 此处需从仓库根目录执行
npm test
node tests/live-smoke.js
```

真实 HTTP 联调脚本需要开发服务器、显式模拟登录及工作进程运行；只创建并删除自己的测试账号。它使用 wx mock，不证明微信开发者工具或真机可用。聚合边界及真实 HTTP 三场景的专项历史结果见 [M2 核心展示验证记录](../docs/verification/M2核心展示验证记录.md)。2026-09-21 的 377 项完整后端测试已在本机和北京隔离 PostgreSQL 通过；小程序 257 项和实际管理流程 48 项通过，详见 [最新验证记录](../docs/verification/真实天气与管理验证记录.md)。开发者工具已显示真实天气和五地点选择器，完整手机交互及正式微信登录仍待验收，内部部署不代表公网正式可用。

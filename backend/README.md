# HYHQ 后端开发与 API

## 运行与范围

本机使用 Python 3.12；北京服务器既有基线已在 Python 3.13 上完成依赖安装、数据库及服务测试。M2 本轮仅在本机验证，未部署服务器。锁定依赖见 `requirements.txt`。数据库默认 PostgreSQL；`HYHQ_USE_SQLITE=1` 仅用于显式本地开发。设置与私有文件位于后端目录，真实 `.env`、数据库、用户文件、模型和本地运行时均不提交。

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

真实微信身份适配已实现，但未配置真实 AppID / AppSecret，尚未向微信验收。开发模拟登录必须同时开启 `ENV=development`、`DJANGO_DEBUG=1`、`ALLOW_DEV_AUTH=1`，生产即使误开第三项也不提供该接口。模拟身份不能替代真实用户认证。

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
| `weather/`、`air-quality/`、`weather-alerts/` | GET | 公开；均为模拟模式，官方预警未接入会明确说明 |
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

科普、路线与个人业务的最新本地验证见 [M2-B01～B04 记录](../docs/verification/M2业务闭环验证记录.md)：完整 PostgreSQL 214 项、前端 191 项，以及用户侧和后台答复实际 HTTP 均通过。反馈字段新增迁移 `activity/0002_feedback_resolution.py`；本轮没有部署到北京服务器。

公开读取不等于管理权限。内容管理员需显式授予 Django 模型权限；上传图片不通过公开 media 路由暴露。生产单层可信 Nginx 代理开启 `TRUST_PROXY_HTTPS=1` 后按其覆盖的 X-Forwarded-For 区分限流来源；不能直接暴露绕过代理的应用端口。

## M2 生态展示数据契约

`observation-series/` 必填 `station`（代码或 UUID），`region` 默认 `demo-campus`；可选 `metrics` 为 1～9 个不重复的适用指标代码。`source_type` 默认 `simulation`，`source` 必须与来源类型匹配；存在多个候选来源时必须显式选择。模拟查询固定一个成功批次，支持 `scenario` 与 `simulation_run`，不会拼接多个批次；非模拟来源不接受模拟批次/场景参数。

时间使用 `hours=1..744`（默认 48），或成对的带时区 `start/end`，两种方式互斥。区间为 `[start,end)`，最长 31 天。`max_points=1..240`（默认 120）限制每指标的时间桶数量，聚合覆盖整个窗口；原始记录总数超过 50000 时拒绝查询，不截断冒充全量。小时模拟页面采用整点批次窗口和每小时一个桶。

响应包含 `source,source_type,is_simulated,simulation_run_id,window,bucket_seconds,series`。`latest` 保留最后一条原始记录的实际时间与质量状态；`summary` 只对有效原始值统计最小、最大与均值，计数按原始记录而非桶数计算。空桶、缺失或存疑桶的曲线值为 `null`；零值为有效数值。混合桶保留有效样本计数与极值，但有缺失/存疑即形成断线。`simulation-runs/` 的 `counts` 仅统计本次区域/站点筛选中可公开的记录。

`water-bodies/?region=...` 与 `stations/?region=...&water_body=<uuid>` 支持详情页进入相应水体和监测站；隐藏地点、水体和停用站点不会通过观测与批次目录泄露。来源目录路径为 `data-sources/`。

示范静态图 `/assets/maps/demo-campus-v1.png` 为 HYHQ 原创虚构布局，固定为 `demo-campus`、v1、1000×700。已有点位的底图不能原地改尺寸、所属区域、版本或替换图片 URL，需新版本重新布点；初始化保留管理员编辑。完整参数表、批次目录及统计语义见 [生态模块说明](ecology/README.md)。

## 图片与记录生命周期

- 仅接受实际可解码的 JPEG、PNG、静态 WebP，输入最多 5MB、2000 万像素。
- 重建像素并转为 JPEG，移除 EXIF/GPS 等元数据；保存最大边 2048 的原图和 480 的缩略图。
- 识别原图 24 小时，识别图片和任务记录 30 天；已设为头像的缩略图保留到替换/注销，未使用头像上传 24 小时。
- 私有图片过期后下载接口立即拒绝，清理命令负责物理文件和记录回收。
- 注销会删除账号及关联记录、图片，审计中的操作者引用匿名化；日志只记录必要状态和计数，不写令牌或微信返回体。

```bash
scripts/manage.sh cleanup_private_data --dry-run
scripts/manage.sh cleanup_private_data
```

清理命令需要在实际部署时设置调度，M1 未自动修改系统定时任务。模拟历史批次的长期保留策略留待 M4。

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

真实 HTTP 联调脚本需要开发服务器、显式模拟登录及工作进程运行；只创建并删除自己的测试账号。它使用 wx mock，不证明微信开发者工具或真机可用。既有 PostgreSQL 结果见 [M1 验证记录](../docs/verification/M1验证记录.md)；M2 本轮完整后端 158 项通过，聚合边界及真实 HTTP 三场景结果见 [M2 核心展示验证记录](../docs/verification/M2核心展示验证记录.md)。服务器基线验证不代表 M2 已上线，微信开发者工具和真机验收仍需另行执行。

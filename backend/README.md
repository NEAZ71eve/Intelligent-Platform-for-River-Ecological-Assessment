# HYHQ 后端开发与 API

## 运行与范围

Python 3.12，锁定依赖见 `requirements.txt`。数据库默认 PostgreSQL；`HYHQ_USE_SQLITE=1` 仅用于显式本地开发。设置与私有文件位于后端目录，真实 `.env`、数据库、用户文件、模型和本地运行时均不提交。

从仓库根目录使用 `scripts/manage.sh` 执行命令，该脚本会切换到 backend 工作目录，确保 Django 能正确发现测试。

```bash
scripts/manage.sh migrate
scripts/manage.sh seed_demo
scripts/manage.sh seed_recognition_knowledge
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
| `regions/`、`places/`、`maps/`、`stations/` | GET | 公开；示范地区、地点、底图登记和监测站 |
| `metrics/`、`data-sources/`、`observations/` | GET | 公开；指标和带来源的数据 |
| `weather/`、`air-quality/`、`weather-alerts/` | GET | 公开；均为模拟模式，官方预警未接入会明确说明 |
| `dashboard/` | GET | 公开；按单一来源/批次读取指标 |
| `contents/`、`routes/` | GET | 公开；只展示已发布内容 |
| `places/{id}/`、`contents/{id}/`、`routes/{id}/` | GET | 公开详情 |
| `uploads/` | POST | 登录；multipart `file`，`purpose=avatar/recognition` |
| `uploads/{id}/content/?variant=thumbnail` | GET | 仅所有者；variant 也可为 original |
| `uploads/{id}/` | DELETE | 仅所有者 |
| `recognition-jobs/` | GET/POST | 仅本人；创建参数 `asset_id`，同一图片幂等 |
| `recognition-jobs/{id}/` | GET/DELETE | 仅本人；删除任务同时删除其图片 |
| `favorites/`、`histories/` | GET/POST | 仅本人；参数 `place_id` 或 `content_id` 二选一 |
| `favorites/{id}/`、`histories/{id}/` | DELETE | 仅本人 |
| `visits/`、`visits/{id}/` | GET/POST、DELETE | 自记游览；同一用户/地点/日期去重，无定位核验 |
| `feedback/` | GET/POST | 仅本人；最多 1000 字，管理员在后台处理 |

公开读取不等于管理权限。内容管理员需显式授予 Django 模型权限；上传图片不通过公开 media 路由暴露。生产单层可信 Nginx 代理开启 `TRUST_PROXY_HTTPS=1` 后按其覆盖的 X-Forwarded-For 区分限流来源；不能直接暴露绕过代理的应用端口。

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

## 检查

```bash
scripts/check.sh
cd miniprogram # 此处需从仓库根目录执行
npm test
node tests/live-smoke.js
```

真实 HTTP 联调脚本需要开发服务器、显式模拟登录及工作进程运行；只创建并删除自己的测试账号。它使用 wx mock，不证明微信开发者工具或真机可用。PostgreSQL 验证与结果见 [M1 验证记录](../docs/verification/M1验证记录.md)。

# 实现计划路径核对（河道生态评估）

日期：2026-09-17

## 核对结果

| 计划中的占位符 | 实际路径 | 备注 |
|---|---|---|
| `<识别模块>` | `backend/recognition/` (app 名 `recognition`) | models 在 `backend/recognition/models.py`，含 `QueueControl` / `ModelVersion` / `RecognitionJob` |
| `<AI识别页>` | `miniprogram/pages/recognize/` | 页面文件为 `index.{js,wxml,wxss,json}` |
| `scripts/manage.sh` | `scripts/manage.sh`（存在） | 是 `python manage.py` 的薄包装，接受任意 Django 子命令；项目无独立 `manage.sh` 子命令清单 |
| 推理工作进程 | `backend/recognition/worker.py`（`process_one` / `recover_stale_jobs` / `_claim` / `_finish`） | 子进程隔离：`backend/recognition/isolation.py`（`run_child` / `execution_lock`）、`backend/recognition/child.py`；management 命令：`backend/recognition/management/commands/run_recognition_worker.py` |
| 后端测试 | `scripts/check.sh` 或 `scripts/manage.sh test` | 使用 Django 内置测试（无 pytest.ini / pyproject.toml / setup.cfg）；各 app 测试在 `backend/<app>/tests.py`（recognition/knowledge/ecology/common 均有） |
| 小程序测试 | 在 `miniprogram/` 下执行 `node --test tests/*.test.js` | Node 20+ 原生测试；测试文件：`tests/{structure,recognition,pages,client}.test.js` 与 `tests/live-smoke.js` |
| `requirements.txt` | `backend/requirements.txt` | Python 3.12，含 Django 5.2.17 / DRF 3.17.2 / onnxruntime 1.23.1 / psycopg 3.3.5 |

## 仓库结构概览

```
HYHQ/
├── backend/                  # Django + DRF 后端
│   ├── manage.py
│   ├── requirements.txt
│   ├── config/               # settings/urls/wsgi
│   ├── accounts/             # 用户、AuthSession（微信登录）
│   ├── activity/             # Favorite/History/Visit/Feedback
│   ├── assets/               # 私有图片 Asset（含过期回收）
│   ├── common/               # AuditLog/TaskLog/middleware/renderers
│   ├── ecology/              # 河道生态核心：Region/Place/WaterBody/Station/Metric/Observation/Simulation*
│   ├── knowledge/            # Content/Route/RouteStop
│   └── recognition/          # 识别模块：ModelVersion/RecognitionJob/worker/isolation/child
├── inference/                # 训练与模型 artifacts（独立于运行时）
│   ├── training/             # train_flowers.py / prepare_flowers.py
│   ├── data/                 # flowers_split_v1.json / experiment_v1.json
│   ├── artifacts/            # *.manifest.json（flowers-efficientnet-b0-v1 / flowers-mobilenet-v3-small-v1）
│   └── reports/              # selection_v1.json / *_validation.json / *_test.json
├── miniprogram/              # 原生微信小程序（无 npm 构建）
│   ├── app.{js,json,wxss}
│   ├── pages/                # home/recognize/records/detail/learn/explore/profile/legal
│   ├── components/           # source-label / recognition-result / page-state
│   ├── lib/                 # client/session/recognition/format/page
│   ├── config/               # local.example.js / index.js
│   └── tests/                # Node 20 原生 test runner
├── scripts/                  # 4 个 bash 脚本（Windows 需 Git Bash/WSL）
│   ├── manage.sh             # 透传 `python manage.py "$@"`
│   ├── dev.sh                # migrate + seed_demo + seed_recognition_knowledge + runserver
│   ├── check.sh              # check + makemigrations --check --dry-run + test
│   └── simulate-current.sh   # 模拟数据生成
├── deploy/                   # 部署说明（README 指向 deploy/README.md）
└── docs/                     # 开发目标TODO / 开发方案稿 / verification/M1验证记录
```

## 关键模型清单

| App | 模型类名 | 备注 |
|---|---|---|
| accounts | `User`、`AuthSession` | 继承 `AbstractUser`；微信 + 系统账号 |
| common | `AuditLog`、`TaskLog` | 业务审计与任务运行日志 |
| assets | `Asset` | 私有图片，含 `original_expires_at` / `expires_at` |
| recognition | `QueueControl`、`ModelVersion`、`RecognitionJob` | 单例锁 + 模型版本 + 识别任务 |
| ecology | `Region`、`MapLayout`、`Place`、`WaterBody`、`Station`、`Metric`、`DataSource`、`SimulationScenario`、`SimulationRun`、`Observation` | `ValidatedModel` 为 abstract 基类（注：定义在 `ecology/models.py`，被 `knowledge` 复用） |
| knowledge | `Content`、`Route`、`RouteStop` | `Content.plant_label` 与识别结果 `candidates[].label` 关联 |
| activity | `Favorite`、`History`、`Visit`、`Feedback` | `TargetRecord` 为 abstract 基类 |

## 路径修正说明

原计划中下列占位符需替换为以下值：

- `<识别模块>` → Django app `recognition`（路径 `backend/recognition/`）
- `<AI识别页>` → `miniprogram/pages/recognize/`
- 推理工作进程入口 → `backend/recognition/worker.py`（不是 `inference/` 目录；`inference/` 仅承载训练与 artifacts）
- 后端测试运行命令 → `scripts/check.sh`（默认 PostgreSQL）或 `scripts/check.sh --sqlite`（本机 SQLite）；等价于 `scripts/manage.sh test`
- 小程序测试运行命令 → `cd miniprogram && node --test tests/*.test.js`
- requirements 路径 → `backend/requirements.txt`
- Windows 注意：`scripts/*.sh` 为 bash 脚本，需在 Git Bash 或 WSL 下运行（当前工作机为 PowerShell）

## 与后续 16 个任务相关的关键事实

1. **生态演进落点**：`backend/ecology/` 已有 `Region / Place / WaterBody / Station / Metric / Observation / SimulationScenario / SimulationRun` 等完整模型，新增"河道生态评估"模块应在 `ecology` app 内扩展，而非新建 app。
2. **识别-生态关联点**：`RecognitionJob` 已通过 `model_version` 与 `Asset` 解耦；`knowledge.Content.plant_label` 是识别 label 的下游锚点，新评估若需联动识别结果，可复用 `Content.plant_label`。
3. **数据源模式**：`DataSource.Kind` 含 `simulation`，`SimulationRun` + `Observation.simulation_run` 已为模拟数据预留接口；河道评估的模拟数据应走此通道。
4. **测试约定**：后端用 Django TestCase（每个 app 一份 `tests.py`），小程序用 Node 20 `node --test`，新增测试需沿用同范式。
5. **模型校验模式**：`ecology.ValidatedModel` 在 `save()` 中强制 `full_clean()`，新模型应继承 `ValidatedModel` 以复用校验管线。

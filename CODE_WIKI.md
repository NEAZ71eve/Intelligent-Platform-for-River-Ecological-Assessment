# HYHQ 海晏河清小程序 — Code Wiki

> **定位（2026-09-18 变更）**：本目录原为腾讯 **TDesign 组件库官方 Demo**；当日已将 HYHQ 业务小程序（`HYHQ\miniprogram`）**迁移覆盖**至此，作为微信开发者工具可直接打开的业务工程。原 TDesign Demo 内容（组件库、演示页）作为**素材残留**保留，未注册进路由、不影响运行。
>
> 业务代码同源维护于 `C:\Users\21516\WeChatProjects\HYHQ` 仓库（已推送至 GitHub，见 §8）。
>
> 更新日期：2026-09-18 ｜ 统计基于当前工作区实际文件。

---

## 1. 项目概览

| 项目 | 说明 |
| --- | --- |
| 工程类型 | 微信小程序（原生，无第三方依赖、无需 npm 构建） |
| 工程名 / AppID | hyhq-miniprogram（HYHQ 海晏河清）/ `touristappid`（游客模式） |
| 编译基础库 | 3.7.12（`project.config.json` → `libVersion`） |
| 语言 | JavaScript（ES6 / CommonJS）+ WXML + WXSS |
| 后端接口 | 统一 REST 客户端（`lib/client.js`），本地调试关闭域名校验（urlCheck:false） |
| UI 组件 | 自研 3 个全局组件（无第三方组件库） |
| 渲染 | WebView（无 Skyline 依赖） |

**关键数字（实测统计）：**

| 指标 | 数值 |
| --- | --- |
| 注册路由（`app.json` pages） | **9**（主包，无分包） |
| tabBar 项 | 5（首页 / 生态导览 / 河道巡查 / 科普智游 / 我的） |
| 全局组件 | 3（page-state / source-label / recognition-result） |
| 业务模块（`lib/`） | 6（assessment / client / format / page / recognition / session） |
| 测试文件（`tests/`） | 3（assessment.test.js / pages.test.js / client.test.js） |
| 仓库文件总数（不含 .git） | 2541（含 TDesign 残留） |
| TDesign 残留 | `miniprogram_npm/`（735 文件）、59 个未注册演示页等 |

---

## 2. 目录结构总览

```
miniprogram-2/                     # = HYHQ 业务小程序（迁移后）
├── app.js                         # 入口：onLaunch 创建 session + api client
├── app.json                       # 9 页注册、5 项 tabBar、定位权限、全局组件
├── app.wxss                       # 全局样式（业务）
├── project.config.json            # touristappid / libVersion 3.7.12 / urlCheck:false
├── project.private.config.json    # （TDesign 残留）
├── sitemap.json                   # 索引规则
├── package.json                   # node --test 测试入口（无依赖）
├── README.md                      # HYHQ 业务说明
│
├── config/                        # 后端 API 配置
│   ├── index.js                   #   服务地址 / 超时 / 端点前缀
│   └── local.example.js           #   本地调试配置样例
├── lib/                           # 业务核心模块
│   ├── client.js                  #   REST 客户端（token、错误归一化、重试）
│   ├── session.js                 #   登录会话（openid / token 管理）
│   ├── assessment.js              #   巡查评估：任务提交 / 结果轮询 / 状态机
│   ├── recognition.js             #   识别上报（M1 遗留能力）
│   ├── format.js                  #   格式化（数值 / 时间 / 列表）
│   └── page.js                    #   页面通用（loading 收尾、错误处理）
├── pages/                         # 9 个业务页 + TDesign 残留演示页（未注册）
│   ├── home/                      #   首页：健康概况 + 区域切换 + 天气/空气/提示
│   ├── explore/                   #   生态导览
│   ├── recognize/                 #   河道巡查（tab 3）：定位 + 拍照 + 提交评估任务
│   ├── learn/                     #   科普智游
│   ├── profile/                   #   我的
│   ├── detail/                    #   河段详情
│   ├── records/                   #   巡查记录（评估任务列表）
│   ├── assessment/                #   ★ Phase 3 新增：评估结果页（分数/等级/依据/重试）
│   └── legal/                     #   法律声明
├── components/                    # 自研全局组件（3 业务 + 4 TDesign 残留）
│   ├── page-state/                #   页面状态（加载/空/错误）
│   ├── source-label/              #   数据来源标签
│   ├── recognition-result/        #   识别结果展示
│   ├── demo-block/                #   （TDesign 残留）
│   ├── demo-header/               #   （TDesign 残留）
│   ├── pull-down-list/            #   （TDesign 残留）
│   └── trd-privacy/               #   （TDesign 残留）
├── tests/                         # node --test 单元测试
├── docs/superpowers/              # 用户设计文档（§6）
├── hyhq-phase3/                   # Phase 3 暂存目录（已合并进业务代码，可清理）
└── miniprogram_npm/               # TDesign 编译产物（残留，勿手改）
```

---

## 3. 应用入口与全局配置

### 3.1 app.js

```js
const config = require('./config/index');
const { createClient } = require('./lib/client');
const { createSession } = require('./lib/session');
App({
  config,
  globalData: { region: null, health: null },
  onLaunch() {
    this.session = createSession(wx);
    this.api = createClient(wx, config, this.session);
  },
});
```

启动即建立**登录会话**与 **API 客户端**，页面通过 `app().api.request(...)` 访问后端。

### 3.2 app.json（关键配置）

- **`pages`**：9 个业务页面（主包，无分包）。
- **`tabBar`**：5 项 — 首页 / 生态导览 / **河道巡查** / 科普智游 / 我的（浅绿主题 `#246746`）。
- **`usingComponents`**（全局注册）：`page-state`、`source-label`、`recognition-result`。
- **`permission.scope.userLocation`** + **`requiredPrivateInfos: ["getLocation"]`**：巡查上报时自动关联最近监测河段。
- **`lazyCodeLoading: "requiredComponents"`**：按需注入组件代码。

### 3.3 project.config.json

- `appid: "touristappid"`（游客模式；换正式 AppID 在此修改）
- `libVersion: "3.7.12"`；`urlCheck: false`（本地调试不校验域名）
- `compileType: "miniprogram"`

### 3.4 config/ 与 lib/

| 模块 | 职责 |
| --- | --- |
| `config/index.js` | 后端服务地址、端点前缀、超时 |
| `lib/session.js` | openid/token 会话（`createSession(wx)`） |
| `lib/client.js` | REST 客户端：请求封装、token 注入、错误归一化、重试（`createClient(wx, config, session)`） |
| `lib/page.js` | 页面工具：`app()` 取全局、`finish()` 收尾 loading |
| `lib/format.js` | `list/time/value/message` 格式化 |
| `lib/assessment.js` | 评估任务：提交 → 轮询 → 状态机（PENDING/PROCESSING/COMPLETED/FAILED） |
| `lib/recognition.js` | 识别上报（M1 遗留） |

### 3.5 package.json

```json
{ "name": "hyhq-miniprogram", "scripts": { "test": "node --test tests/*.test.js" }, "engines": { "node": ">=20" } }
```

无任何第三方依赖；测试用 Node 内置 `node:test` 运行。

---

## 4. 业务页面体系

### 4.1 路由与 tab

| 页面 | tab | 职责 | 依赖 API |
| --- | --- | --- | --- |
| `pages/home/index` | 首页 | 健康概况、区域切换、天气/空气/气象提示 | health/、regions/、weather/、air-quality/、weather-alerts/ |
| `pages/explore/index` | 生态导览 | 河段生态导览 | regions/ 等 |
| `pages/recognize/index` | **河道巡查** | 定位关联河段 → 拍照/选图 → 提交评估任务 | geo 关联、assessment-jobs POST |
| `pages/learn/index` | 科普智游 | 科普内容 | — |
| `pages/profile/index` | 我的 | 个人信息/设置 | — |
| `pages/detail/index` | — | 河段详情 | regions/<id> 等 |
| `pages/records/index` | — | 巡查记录（评估任务列表） | assessment-jobs GET |
| `pages/assessment/index` | — | **评估结果页**：分数 / 等级 / 依据 / 失败重试 | assessment-jobs GET 轮询 |
| `pages/legal/index` | — | 法律声明 | — |

### 4.2 巡查主流程（Phase 3 已实现）

```
recognize（拍照+定位）
  → POST assessment-jobs（创建评估任务）
  → records（任务列表，PENDING/PROCESSING）
  → assessment（轮询结果：分数/等级/依据）
```

> ⚠️ 评估结果依赖后端 ONNX 模型登记；模型未导出前提交任务将返回"评估模型未启用"（预期失败路径，见 §7.4）。

---

## 5. TDesign 素材残留（原官方 Demo 内容）

迁移后保留但**未注册、不影响运行**的部分：

- `miniprogram_npm/tdesign-miniprogram/`：80 个组件编译产物（735 文件），需"构建 npm"才可再生成。
- `pages/` 下 59 个组件演示页（`button`、`radio`、`swiper` 等）及 `skyline/` 变体：仅作**组件用法参考**。
- `components/` 的 `demo-block` / `demo-header` / `pull-down-list` / `trd-privacy`、`behaviors/skyline.js`、`demos/`、`utils/gulpError.js`、`assets/`、`theme.json`、`app.d.ts`。

如需完全清理（删除残留以瘦身），需先确认业务无引用后操作。

---

## 6. docs/superpowers（用户设计文档）

| 文件 | 内容 |
| --- | --- |
| `specs/2026-09-17-river-eco-assessment-design.md` | HYHQ 河道生态评估模块设计（v1.0，已批准）：YOLOv8n + ONNX CPU 推理、4 类检测、RULE v1 规则引擎、D0–D3 数据流水线、API 契约、验收标准 |
| `plans/2026-09-17-river-eco-assessment.md` | 对应实现计划（4 阶段 17 任务），含代码骨架与测试用例 |

---

## 7. HYHQ 河道生态评估 YOLO 实现状态

> 业务代码位于 `C:\Users\21516\WeChatProjects\HYHQ`（已推送 GitHub，见 §8）。本节为对 HYHQ 仓库的实测核查结果，对应 §6 设计文档的实现进度。

### 7.1 进度总览（17 任务 × 4 阶段）

| 阶段 | 任务 | 状态 | 说明 |
| --- | --- | --- | --- |
| Phase 0 | T0 克隆 / 路径核对 | ✅ 完成 | 已提交 |
| | T1 D0 决策门（WATER-DET） | ✅ 完成 | **有条件 NO-GO**：数据不可公开下载，已邮件联系作者，等待至 2026-10-01 |
| Phase 1 | T2 数据集下载与审计 | ⚠️ 部分 | 仅 IWHR 到位（3000 图 / 2.24GB / 已审计）；YRDG、FloW、TU Delft 未下载；WATER-DET 待定 |
| | T3 类别映射 | ✅ 完成 | class_mapping.yaml v1（4 大类 + 15 细类） |
| | T4 统一数据集构建 | ✅ 完成 | 3000 图（全 IWHR）2100/450/450 划分，seed 42 |
| | T5 YOLOv8n 训练 | ✅ 完成 | v1-4 完成 100 轮；**缺 yolo-v1-report.md** |
| | T6 ONNX 导出 + manifest | ⚠️ 部分 | onnx_detector.py 已提交且测试通过；**ONNX 未导出、模型未登记** |
| Phase 2 | T7 规则引擎 | ✅ 完成 | rules.py RULE v1（DB RuleSet 版本回退） |
| | T8 河段关联 | ✅ 完成 | geo.py Haversine 最近站 2km |
| | T9 assessment-jobs API | ✅ 完成 | views / serializers / urls 已实现 |
| | T10 推理 worker | ✅ 完成 | assessment_worker.py 全链路 |
| | T11 Admin | ✅ 完成 | RuleSet + AssessmentJob 后台 |
| Phase 3 | T12 巡查上报页 | ✅ 已实现 | recognize 改造 + assessment-jobs 提交（**未提交 git、未联调**） |
| | T13 评估结果页 | ✅ 已实现 | assessment/index（分数/等级/依据/重试） |
| | T14 记录页 + 入口 | ✅ 已实现 | records 任务列表 + tab「河道巡查」 |
| Phase 4 | T15–T16 联调与验收 | ❌ 未开始 | — |

### 7.2 已实现模块（实测核对）

**推理侧（inference/training/，已提交 9bf3023）**

| 文件 | 说明 |
| --- | --- |
| audit_datasets.py | 数据集审计（SHA-256 + dHash 去重），测试通过 |
| class_mapping.py | 类别映射加载 / 校验（4 大类 + 15 细类） |
| build_dataset.py | 各源标注 → 统一 YOLO 格式 + 冻结划分（2100/450/450） |
| train_yolo.py | yolov8n.pt、640×640、100 轮、seed 42、workers=0（Windows 兼容） |
| export_onnx.py | ONNX 导出 + 检测 manifest 生成（**未运行**） |
| onnx_detector.py | ONNX 后处理：conf 过滤 + 逐类 NMS（测试通过） |

**训练结果**（runs/river-eco-v1-4，最终轮，**已入库 9a8fe62**）：Precision 0.897 ｜ Recall 0.817 ｜ **mAP50 0.904** ｜ mAP50-95 0.658

> ⚠️ 注意：当前数据**仅 IWHR 单源、单细类（misc_debris）**，其余 14 个细类无训练样本；上述指标只代表「水面漂浮物」单一任务的检测效果，不代表河道生态多类评估能力。

**后端侧（backend/ecology/，已提交）**

| 文件 | 说明 |
| --- | --- |
| rules.py | RULE v1 评估规则引擎（100 分制扣分，DB 优先、内置回退） |
| geo.py | 定位 → 河段关联（Haversine，2km 半径） |
| detection.py | ONNX 运行时副本：letterbox 预处理 + NMS + 坐标回映 |
| assessment_worker.py | 消费 AssessmentJob：claim → detect → assess → 落库（错误码 / 超时恢复 / 任务日志） |
| views.py / serializers.py / urls.py | POST / GET assessment-jobs API |
| admin.py | RuleSet 版本管理 + AssessmentJob 只读查看 |
| tests.py | 32KB，10 个测试类（RuleV1 / Geo / API / Worker 等） |
| requirements.txt | onnxruntime==1.23.1、onnx==1.19.0、numpy==2.2.6 |

### 7.3 小程序侧（Phase 3，已迁移至本目录）

- `pages/assessment/index.*`：评估结果页（状态机：PENDING → PROCESSING → COMPLETED/FAILED，失败可重试）。
- `pages/recognize/index.*`：改造为巡查上报（定位 + 拍照 + 提交任务）。
- `pages/records/index.*`：巡查记录列表。
- `lib/assessment.js`：任务提交 / 轮询客户端。
- `tests/assessment.test.js` + `tests/pages.test.js`：16/16 通过（在 HYHQ 仓库内验证）。

### 7.4 缺口与阻塞

1. **D0 决策门悬置**：WATER-DET 有条件 NO-GO，2026-10-01 前未获数据将触发回退条款（转花卉识别）。
2. **模型覆盖面不足**：15 细类仅 1 类有样本；水华黑臭 / 排污口 / 岸带三类无数据，规则引擎这些大类无真实检出可评。
3. **ONNX 制品缺失**：未导出、未登记 → 后端运行时将报 `MODEL_NOT_CONFIGURED`；小程序提交任务显示"评估模型未启用"（预期行为）。
4. **Phase 3 未提交**：HYHQ 工作区含小程序改动（app.json + assessment 页 + lib 等），尚未 git 提交；与后端联调（Phase 4）未开始。

### 7.5 建议下一步（按依赖序）

1. 补下载 YRDG / FloW / TU Delft → 重训 → 补 `yolo-v1-report.md`。
2. 运行 `export_onnx.py` 导出 ONNX + manifest → 扩展模型登记校验的检测分支 → `register_model` 登记。
3. 提交 HYHQ 工作区 Phase 3 改动，然后启动后端 + 小程序联调（Phase 4 T15/T16）。
4. 等待 2026-10-01 WATER-DET 结果，决定是否回退花卉识别方案。

---

## 8. Git 仓库与版本管理（2026-09-18）

### 8.1 HYHQ 远程仓库

| remote | URL | 状态 |
| --- | --- | --- |
| `origin` | https://github.com/gruTGU/HYHQ.git | 保留（原仓库） |
| `github` | git@github.com:NEAZ71eve/Intelligent-Platform-for-River-Ecological-Assessment.git | **已推送**，main=9a8fe62 |

本地身份（仓库级）：`gruTGU <gruTGU@users.noreply.github.com>`；SSH key：ed25519/rsa。

### 8.2 提交历史（main，最近 3 条）

| 提交 | 内容 |
| --- | --- |
| `9a8fe62` | chore: 训练产物纳入版本管理（runs/ 权重与指标，inference 白名单） |
| `9bf3023` | feat(inference): YOLOv8n 训练与 ONNX 导出脚本及 IWHR 审计记录 |
| `2940993` | feat(ecology): Phase 2 backend evolution - rule engine + geo + assessment-jobs API + worker + admin |

### 8.3 训练产物白名单策略（双 .gitignore）

- 根 `.gitignore` + `inference/.gitignore` 均新增：
  - `!inference/runs/**/*.pt`（训练权重入库）
  - `!inference/artifacts/*.onnx`（未来 ONNX 制品入库）
- 仍全局忽略：`*.pt`/`*.onnx`/`*.pth`（预训练权重如 `weights/yolo26n.pt`、临时权重不入库）。
- **已入库**（9a8fe62，33 文件 / 22.8MB）：`runs/` 权重（best.pt/last.pt）、results.csv、混淆矩阵、PR/P/F1 曲线、训练/验证批次图。
- **明确不入库**：原始数据 `.runtime/`（约 2.2GB）、`data/raw/`、划分缓存 `data/splits/`（seed 42 可重放重建）。

### 8.4 未提交工作

| 位置 | 内容 |
| --- | --- |
| HYHQ 工作区 | Phase 3 小程序改动（app.json、recognize/records/assessment 页、lib/assessment.js、tests） |
| miniprogram-2 | 迁移后全部业务文件未跟踪/已修改（本目录无远程仓库，24 项变更） |

---

## 9. 开发指南

### 9.1 运行

1. 微信开发者工具导入本目录（`miniprogram-2`），AppID 使用 `touristappid`（游客模式）或自行配置。
2. 基础库 ≥ 3.7.12；`urlCheck` 已关闭，本地调试不校验域名。
3. 编译（Ctrl+B）后首页为业务首页；底部 tab 第三项为**河道巡查**。
4. 后端联调：按 `config/local.example.js` 配置本地后端地址，复制为 `config/local.js`。

### 9.2 测试

```bash
cd C:\Users\21516\WeChatProjects\miniprogram-2
node --test tests/*.test.js
```

（`tests/` 依赖 `lib/` 与页面文件，迁移后可直接在业务目录运行。）

### 9.3 代码约定

- 页面统一使用 `lib/page.js`（`app()` 取全局实例、`finish()` 收尾 loading）。
- API 调用一律走 `app().api.request(path, options)`，不直接 `wx.request`。
- 错误展示走 `lib/format.js message()` 归一化；列表走 `list()`；数值/时间走 `value()/time()`。
- 组件保持 `page-state` / `source-label` / `recognition-result` 全局注册，勿重复引入。

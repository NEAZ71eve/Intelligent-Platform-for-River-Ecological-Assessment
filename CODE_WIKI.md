# HYHQ 海晏河清小程序 — Code Wiki

> **定位（2026-09-18 更新）**：本目录原为腾讯 **TDesign 组件库官方 Demo**；当日已将 HYHQ 业务小程序（`HYHQ\miniprogram`）**迁移覆盖**至此，作为微信开发者工具可直接打开的业务工程。原 TDesign Demo 内容（组件库、演示页）作为**素材残留**保留，未注册进路由、不影响运行。
>
> 业务代码同源维护于 `D:\WeChatProjects\HYHQ` 仓库（已推送 GitHub，见 §8）；小程序工程独立成库（分支 `miniprogram-2`）。
>
> 更新日期：2026-09-21 ｜ 统计基于当前工作区实际文件。

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
| git 跟踪文件数 | 2547（含 TDesign 残留；磁盘另有 `.venv/` 未跟踪） |
| TDesign 残留 | `miniprogram_npm/`（735 文件）、59 个未注册演示页等 |

---

## 2. 目录结构总览

```
miniprogram-2/                     # = HYHQ 业务小程序（迁移后，D 盘）
├── app.js                         # 入口：onLaunch 创建 session + api client
├── app.json                       # 9 页注册、5 项 tabBar、定位权限、全局组件
├── app.wxss                       # 全局样式（业务）
├── project.config.json            # touristappid / libVersion 3.7.12 / urlCheck:false
├── project.private.config.json    # （TDesign 残留）
├── sitemap.json                   # 索引规则
├── package.json                   # node --test 测试入口（无依赖）
├── README.md                      # HYHQ 业务说明
├── CODE_WIKI.md                   # 本文档
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
├── docs/                          # 项目文档（§6 设计 + 数据集调研/规范）
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

> ⚠️ 评估结果依赖后端 ONNX 模型登记；ONNX 已导出（§7.2），登记后提交任务即可正常返回评估结果。

---

## 5. TDesign 素材残留（原官方 Demo 内容）

迁移后保留但**未注册、不影响运行**的部分：

- `miniprogram_npm/tdesign-miniprogram/`：80 个组件编译产物（735 文件），需"构建 npm"才可再生成。
- `pages/` 下 59 个组件演示页（`button`、`radio`、`swiper` 等）及 `skyline/` 变体：仅作**组件用法参考**。
- `components/` 的 `demo-block` / `demo-header` / `pull-down-list` / `trd-privacy`、`behaviors/skyline.js`、`demos/`、`utils/gulpError.js`、`assets/`、`theme.json`、`app.d.ts`。

如需完全清理（删除残留以瘦身），需先确认业务无引用后操作。

---

## 6. 项目文档（docs/）

### 6.1 设计文档（docs/superpowers/）

| 文件 | 内容 |
| --- | --- |
| `specs/2026-09-17-river-eco-assessment-design.md` | HYHQ 河道生态评估模块设计（v1.0，已批准）：YOLOv8n + ONNX CPU 推理、4 类检测、RULE v1 规则引擎、D0–D3 数据流水线、API 契约、验收标准 |
| `plans/2026-09-17-river-eco-assessment.md` | 对应实现计划（4 阶段 17 任务），含代码骨架与测试用例 |

### 6.2 数据集调研与规范（根目录 + docs/）

**miniprogram-2 根目录：**

| 文件 | 内容 |
| --- | --- |
| `HYHQ_水华黑臭数据集调研报告.md` | 水华/黑臭方向（iSOOD、WATER-DET、黑臭无公开 bbox 结论） |
| `HYHQ_水面漂浮物补充数据集调研报告.md` | 漂浮物补充（PoTATO/CANSURF/TACO 首选；algae_mass 无公开数据） |
| `HYHQ_数据集调研报告.html` | 总报告（ECharts 15 细类 × 16 数据集覆盖矩阵热力图） |
| `HYHQ_dataset_verification_report.md` | 已规划 4 数据集可下载性核实（YRDG 网盘、FloW 邮件、TUD-GV 无 bbox、WATER-DET 无公开） |

**docs/ 目录：**

| 文件 | 内容 |
| --- | --- |
| `HYHQ_河道检测数据集调研报告.md` | outfall / bank 方向调研（iSOOD 发现、WATER-DET 申请、bank_encroach 需自采） |
| `数据集清单.md` | 全部数据集来源/大小/校验和/状态索引（数据本体在 D 盘，不入库；已同步至 2026-09-21） |
| `数据集申请邮件模板.md` | WATER-DET / Space-hehu / FloW-Img 三封申请邮件模板 + 跟进清单 |
| `硬缺口自采规范.md` | 5 类硬缺口（algae_mass/sewage_color/foam_pollution/bank_encroach/bank_garbage）采集+标注规范 |
| `生态等级标签标注规范.md` | 方向 B 图像级四档生态等级（good/fair/poor/critical）双人标注规范 |

---

## 7. HYHQ 河道生态评估 YOLO 实现状态

> 业务代码位于 `D:\WeChatProjects\HYHQ`（已推送 GitHub，见 §8）。本节为对 HYHQ 仓库的实测核查结果，对应 §6.1 设计文档的实现进度。

### 7.1 进度总览（17 任务 × 4 阶段）

| 阶段 | 任务 | 状态 | 说明 |
| --- | --- | --- | --- |
| Phase 0 | T0 克隆 / 路径核对 | ✅ 完成 | 已提交 |
| | T1 D0 决策门（WATER-DET） | ✅ 完成 | **有条件 NO-GO**：数据不可公开下载；申请邮件模板已就绪，等待至 2026-10-01 |
| Phase 1 | T2 数据集下载与审计 | 🔄 进行中 | IWHR✅、CANSURF✅（7062 图）、iSOOD✅（10433 图，md5 通过）、YRDG✅（10233 图）、TACO 下载中（857/1500 图）；详见 §10 |
| | T3 类别映射 | ✅ 完成 | class_mapping.yaml v1（4 大类 + 15 细类） |
| | T4 统一数据集构建 | ✅ 完成 | **unified-v2**：5 源 31550 图 / 87610 框，划分 22085/4732/4733（seed 42） |
| | T5 YOLOv8n 训练 | ✅ 完成 | **v3（unified-v2，10 类）100 轮，val mAP50=0.790**；v1-4 单类 0.904 为历史基线；缺 yolo-v1-report.md |
| | T6 ONNX 导出 + manifest | ✅ 完成 | **v1/v2/v3 ONNX 均已导出并提交**（artifacts/，v3=12.3MB + manifest） |
| Phase 2 | T7 规则引擎 | ✅ 完成 | rules.py RULE v1（DB RuleSet 版本回退） |
| | T8 河段关联 | ✅ 完成 | geo.py Haversine 最近站 2km |
| | T9 assessment-jobs API | ✅ 完成 | views / serializers / urls 已实现 |
| | T10 推理 worker | ✅ 完成 | assessment_worker.py 全链路 |
| | T11 Admin | ✅ 完成 | RuleSet + AssessmentJob 后台 |
| Phase 3 | T12 巡查上报页 | ✅ 已实现并提交 | recognize 改造 + assessment-jobs 提交 |
| | T13 评估结果页 | ✅ 已实现并提交 | assessment/index（分数/等级/依据/重试） |
| | T14 记录页 + 入口 | ✅ 已实现并提交 | records 任务列表 + tab「河道巡查」 |
| Phase 4 | T15–T16 联调与验收 | ❌ 未开始 | ONNX v3 已导出待后端登记，登记后启动 |

### 7.2 已实现模块（实测核对）

**推理侧（inference/training/，已提交）**

| 文件 | 说明 |
| --- | --- |
| audit_datasets.py | 数据集审计（SHA-256 + dHash 去重），测试通过 |
| class_mapping.py | 类别映射加载 / 校验（4 大类 + 15 细类） |
| build_dataset.py | 各源标注 → 统一 YOLO 格式 + 冻结划分（**unified-v2：31550 图 / 87610 框 / 22085-4732-4733**） |
| train_yolo.py | yolov8n.pt、640×640、100 轮、seed 42、workers=4（Windows 兼容） |
| export_onnx.py | ONNX 导出 + 检测 manifest 生成（已运行） |
| onnx_detector.py | ONNX 后处理：conf 过滤 + 逐类 NMS（测试通过） |
| download_p0_datasets.py | P0 数据集批下载器（iSOOD/TACO/CANSURF/PoTATO/YRDG，断点续传/md5/幂等） |

**v1 训练结果（runs/river-eco-v1-4，已入库，历史基线）**：P 0.897 ｜ R 0.817 ｜ mAP50 0.904 ｜ mAP50-95 0.658（3000 图全 IWHR，仅 misc_debris 单类）

**真实 test 指标（runs/detect/val-5，450 图 / 3560 框，已入库）**：mAP50 = 0.884 ｜ mAP50-95 = 0.630 ｜ P = 0.878 ｜ R = 0.790

**v3 训练结果（runs/river-eco-v3，unified-v2 多源，100 轮；ONNX 已提交，runs/ 待入库）**：val 4732 图 / 12961 框，**mAP50 = 0.790** ｜ mAP50-95 = 0.517 ｜ P = 0.80 ｜ R = 0.747

v3 类别 mAP50：metal 0.97 ｜ fabric 0.966 ｜ water_plant 0.937 ｜ plastic 0.90 ｜ outfall 0.897 ｜ paper 0.882 ｜ misc_debris 0.875 ｜ glass 0.842 ｜ **bottle 0.451** ｜ **foam_board 0.177**

> 数据诊断进展（training-direction-v1.md + v2/v3 实测）：v1 仅 misc_debris 单类、其余 14 类零样本，属**任务目标与监督信号不匹配**；unified-v2 已扩展为 10 类有样本（YRDG/iSOOD/CANSURF/TACO 多源），v2（中断）/v2-2（80 轮，mAP50 0.756）/v3（100 轮，0.790）验证多类训练可行。**剩余 5 类硬缺口（algae_mass/sewage_color/foam_pollution/bank_garbage/bank_encroach）仍为零样本**，见 §7.4。

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

### 7.3 小程序侧（Phase 3，已提交）

- `pages/assessment/index.*`：评估结果页（状态机：PENDING → PROCESSING → COMPLETED/FAILED，失败可重试）。
- `pages/recognize/index.*`：改造为巡查上报（定位 + 拍照 + 提交任务）。
- `pages/records/index.*`：巡查记录列表。
- `lib/assessment.js`：任务提交 / 轮询客户端。
- `tests/assessment.test.js` + `tests/pages.test.js`：16/16 通过。

### 7.4 方向决策与剩余缺口

**方向判定（training-direction-v1.md）**：转向 A（短期）或 B（正式）。

- **方向 A（短期）**：目标收敛为"漂浮物风险评分"——保留检测器 + 四档人工标签 + 按地点分组划分 + macro-F1 验收。
- **方向 B（正式）**：补齐四类数据（漂浮物/水华黑臭/排污口/岸带）+ 每图生态等级标签 + 检测/等级多任务模型。附 5 条实验门禁（数据/标签/基线/指标/泛化）。

**剩余硬缺口（无公开数据，须自采，见 docs/硬缺口自采规范.md）**：

| 细类 | 归属大类 | 最小量 |
| --- | --- | --- |
| algae_mass（藻类团） | 水华黑臭 | ≥500 张 |
| sewage_color（黑臭水色） | 水华黑臭 | ≥300 张 |
| foam_pollution（泡沫） | 水华黑臭 | ≥300 张 |
| bank_encroach（岸线侵占） | 岸带 | ≥500 张 |
| bank_garbage（岸边视角） | 岸带 | ≥500 张 |

**待办**：TACO 图片补完（857/1500）；marine-debris640 重新拉取（当前克隆仅 .git 无数据）；3 封申请邮件（WATER-DET/Space-hehu/FloW-Img，模板见 docs/）；自采 + 生态等级标注（双人一致，见 docs/生态等级标签标注规范.md）；人工评估集 eval-v1/v2（43 图、3 场景，带来源 URL）可用于泛化测试或方向 B 试点。

### 7.5 建议下一步（按依赖序）

1. 后端登记 ONNX（artifacts/river-eco-yolov8n-v3.onnx + manifest）→ 启动 Phase 4 T15/T16 联调验收。
2. 提交 HYHQ 工作区未入库内容（runs/v3 训练产物、v1.manifest 修订）。
3. 补完 TACO 图片（857/1500）→ 增量扩充统一集；marine-debris640 重新拉取。
4. 启动硬缺口自采（试点 50 张/类）+ 发送 3 封申请邮件；用 eval-v1/v2（43 图）做泛化评估。
5. 方向 B：生态等级标签试点（双人标注）→ 多任务模型基线。
6. 等待 2026-10-01 WATER-DET 结果，决定是否触发回退条款。

---

## 8. Git 仓库与版本管理（2026-09-18）

### 8.1 远程仓库

**HYHQ（业务 + 推理）**：`git@github.com:NEAZ71eve/Intelligent-Platform-for-River-Ecological-Assessment.git`，分支 `main`。

| remote | URL | 说明 |
| --- | --- | --- |
| `github` | git@github.com:NEAZ71eve/Intelligent-Platform-for-River-Ecological-Assessment.git | 主远程（SSH 可达） |
| `origin` | https://github.com/gruTGU/HYHQ.git | 旧远程（HTTPS 被网络阻断，保留） |

**miniprogram-2（小程序工程）**：同一远程仓库，本地分支 `master` → 远程分支 `origin/miniprogram-2`（origin 为 SSH 主远程）。

本地身份（仓库级）：`gruTGU <gruTGU@users.noreply.github.com>`；SSH key：ed25519/rsa。

### 8.2 提交历史（2026-09-18 全部已推送）

**HYHQ `main` 分支**（最近 8 条，更早见 git log）：

| 提交 | 内容 |
| --- | --- |
| `13472e0` | feat(inference): river-eco-v3 训练完成（TACO 扩充 bottle 78→155 / foam 50→81），val mAP50=0.789，ONNX v3 导出 |
| `b3cbbbd` | docs: 二轮调研发现（IWHR 可零成本重标、driftwood/foam/grass 数据集） |
| `37d58a0` | docs: bottle/foam_board few-shot 补充计划（auto-label 失败，已列候选标注） |
| `130343d` | feat(inference): eval-v2 独立测试集（27 图，outfall/bloom 黑臭重点）+ 检测汇总 |
| `1c8e9b8` | feat(inference): v2 训练完成（多类 YOLOv8n，test mAP50=0.767），eval-v1 重跑，ONNX v2 导出+报告 |
| `5509f28` | feat(inference): eval-v1 独立测试集（16 图，4 场景，sources+README） |
| `1990a12` | feat(inference): train_yolo.py → unified-v2 多类（river-eco-v2，workers=4 Windows 稳定） |
| `0061ae0` | docs: 刷新 unified-v2 统计（TACO 402 时构建，train 21769/val 4665/test 4665，86372 框） |

> unified-v2 后经 prepare_v3 重建为最终版：31550 图 / 87610 框 / 22085-4732-4733（见 §10）。

**miniprogram-2 分支**：

| 提交 | 内容 |
| --- | --- |
| `39ef592` | docs: 更新 CODE_WIKI 全量状态，纳入数据集清单与采集/标注/申请规范 |
| `5f75177` | feat: 河道生态评估小程序前端与数据集调研报告（15 细类缺口全景） |
| `0254dbd` / `a1d362a` | docs: 河道生态评估实现计划 / 模块设计 |

### 8.3 训练产物白名单策略（双 .gitignore）

- 根 `.gitignore` + `inference/.gitignore`：`!inference/runs/**/*.pt`、`!inference/artifacts/*.onnx`。
- 仍全局忽略：`*.pt`/`*.onnx`/`*.pth`（预训练权重不入库）。
- 已入库：runs 权重、results、混淆矩阵、PR/F1 曲线、val-5 评估图、**ONNX v1/v2/v3 制品（artifacts/，各 ~12.3MB）**。
- **明确不入库**：原始数据 `.runtime/`（约 36GB，在 D 盘）、`data/raw/`、划分缓存（seed 42 可重放）。

### 8.4 工作区状态

- **HYHQ（main）**：含未提交内容——`inference/artifacts/river-eco-yolov8n-v1.manifest.json` 已修改；`inference/runs/` 下 river-eco-v2 / v2-2 / v3 与 detect/runs（v3 训练产物）未跟踪（白名单外文件待整理提交）。
- **miniprogram-2（master）**：`CODE_WIKI.md`、`code-wiki.html`、`docs/数据集清单.md` 本次已同步至 2026-09-21 状态（未提交）。
- 数据集本体在 D 盘（§10），不入 GitHub。

---

## 9. 开发指南

### 9.1 运行

1. 微信开发者工具导入 `D:\WeChatProjects\miniprogram-2`，AppID 使用 `touristappid`（游客模式）或自行配置。
2. 基础库 ≥ 3.7.12；`urlCheck` 已关闭，本地调试不校验域名。
3. 编译（Ctrl+B）后首页为业务首页；底部 tab 第三项为**河道巡查**。
4. 后端联调：按 `config/local.example.js` 配置本地后端地址，复制为 `config/local.js`。

### 9.2 测试

```bash
cd D:\WeChatProjects\miniprogram-2
node --test tests/*.test.js
```

### 9.3 代码约定

- 页面统一使用 `lib/page.js`（`app()` 取全局实例、`finish()` 收尾 loading）。
- API 调用一律走 `app().api.request(path, options)`，不直接 `wx.request`。
- 错误展示走 `lib/format.js message()` 归一化；列表走 `list()`；数值/时间走 `value()/time()`。
- 组件保持 `page-state` / `source-label` / `recognition-result` 全局注册，勿重复引入。

---

## 10. 数据集落地与调研现状（2026-09-21）

### 10.1 数据落盘位置（全部在 D 盘）

```
D:\HYHQ_data\
├── .runtime\                    # 数据集（约 36GB）
│   ├── IWHR_AI_Lable_Floater_V1 #   统一集源（3000 图 / 2.1GB）
│   ├── CANSURF\                 #   水面金属罐（7062 图，已验证）
│   ├── iSOOD\                   #   排污口检测（10433 图，md5 通过）
│   ├── TACO_git\                #   TACO 标注（4784 条）+ Flickr 图片下载（857/1500，进行中）
│   ├── YRDG\                    #   YRDG 漂浮物（10233 图 + labels，已完成）
│   ├── marine-debris640\        #   Marine Debris 640（⚠ 克隆不完整，仅 .git 无数据）
│   ├── supplement_bottle_foam\  #   bottle/foam 自采补充（16 图 + 16 标签）
│   ├── downloads\               #   压缩包 + 下载脚本（iSOOD zip 9.5GB、YRDG zip 3.8GB、CANSURF zip 2.1GB…）
│   └── prepare_v3.log / train_v3.log  # unified-v2 构建与 v3 训练日志
├── eval-v1\ eval-v2\            # 人工评估集（16 + 27 图，3 场景，sources.csv 带来源）
├── docs\                        # 数据工作文档（邮件模板/自采规范/标注规范/数据集清单）
└── (小程序项目) D:\WeChatProjects\miniprogram-2
    (后端+推理) D:\WeChatProjects\HYHQ
```

### 10.2 数据集状态表

| 数据集 | 类别覆盖 | 状态 | 说明 |
| --- | --- | --- | --- |
| IWHR（统一集源） | misc_debris 主力 | ✅ 已落地 | 3000 图 / 2.1GB，seed 42 可重放 |
| CANSURF | metal | ✅ 已落地 | 7062 图，校验通过 |
| iSOOD | outfall（排污口） | ✅ 已落地 | 10433 图，md5 通过 |
| YRDG | 漂浮物 6 类 | ✅ 已落地 | 10233 图（zip 3.8GB 已下完，2026-09-19） |
| TACO | bottle/plastic/paper/glass/metal/foam | 🔄 下载中 | 标注 4784 条已就位；图片 857/1500（2026-09-21 凌晨仍在拉取，5 张截断剔除） |
| supplement_bottle_foam | bottle / foam | ✅ 新增 | 自采 16 图 + 16 标签（auto_label），few-shot 补充 |
| MarineDebris（marine-debris640） | foam 等 | ⚠ 克隆不完整 | 仅 .git 无工作树，需重新拉取（或换 Kaggle 源） |
| eval-v1 / eval-v2 | 3 场景人工评估集 | ✅ 已建 | 16 + 27 图，带来源 URL（泛化测试/生态标注试点） |
| PoTATO | bottle（水面专项） | ⏸ 待下 | SharePoint 被 DNS 阻断，需代理 |
| River Flow Trash | water_plant | ⏸ 待下 | Ultralytics（需 key） |
| WATER-DET | 三大类全 | ⏸ 申请中 | 唯一覆盖 4 大类的数据集，通讯作者 zgg@xaut.edu.cn |
| Space-hehu | bank_encroach | ⏸ 申请中 | 天津西青 28120 图，通讯作者 liuling@tjau.edu.cn |
| FloW-Img | bottle | ⏸ 申请中 | datasets@orca-tech.com.cn |
| TU Delft-GV | 分类无 bbox | ❌ 已剔除 | 对 YOLO 训练无用 |

### 10.3 关键结论

- **统一集 unified-v2 已构建（2026-09-20/21）**：IWHR + CANSURF + iSOOD + TACO（部分）+ YRDG → 去重 31550 图 / 87610 框，划分 22085/4732/4733，10 类有样本（metal/misc_debris/plastic/outfall 为主，bottle 155、foam_board 81 为弱类）。
- **v3 训练完成（2026-09-21）**：val mAP50=0.790 / mAP50-95=0.517（100 轮）；ONNX v3 已导出并提交（artifacts/，待后端登记）。
- **硬缺口（须自采）**：algae_mass / sewage_color / foam_pollution / bank_encroach / bank_garbage——unified-v2 中仍为零样本（量见 §7.4）。
- **环境事实**：训练环境 = anaconda base（Python 3.12.7，torch 2.14.0+cu126，RTX 4060 Laptop 8GB）；zenodo 需本地代理 127.0.0.1:7897。
- **git 事实**：HTTPS 直连 github.com 被阻断，SSH（22 端口）可用——推送一律走 SSH remote。

### 10.4 环境与磁盘维护记录（2026-09-21）

| 事项 | 详情 |
| --- | --- |
| D 盘可用空间 | 16.3 GB（2%）→ **75.7 GB（12%）**，共释放约 59 GB |
| 已清理项 | D 盘 anaconda3 `pkgs` 缓存 9.7GB；联想商店安装包缓存（LeStoreDownload + LenovoSoftstore）约 10.5GB；TapTap 安卓模拟器数据 32.7GB；Ubuntu ISO 镜像 6.1GB；D 盘回收站 |
| 项目相关影响 | **无**。`D:\WeChatProjects`（miniprogram-2 / HYHQ）、`D:\HYHQ_data`（.runtime 数据集）、`D:\anaconda\envs`（conda 环境）、`D:\ollama`（模型）均未改动；anaconda `pkgs` 为可再生缓存，删除不影响 base 与各 env 运行 |

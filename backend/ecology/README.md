# 生态数据与内容模块（M1 / M2）

## 初始化与模拟

从仓库根目录运行（先配置后端环境并完成迁移）：

```sh
.venv/bin/python backend/manage.py seed_demo
.venv/bin/python backend/manage.py generate_simulation --scenario missing --start 2026-09-15T00:00:00Z --hours 48 --seed 20260916
.venv/bin/python backend/manage.py generate_simulation --scenario turbidity --start 2026-09-15T00:00:00Z --hours 48 --seed 20260916
```

`seed_demo` 幂等创建虚构的 `demo-campus` 区域、12 个地点、2 个水体、2 个水站、1 个气象站、1 个空气站、9 个指标、3 个场景、3 个对应模拟来源、3 篇科普和1条6节点路线。

- 默认生成截至当前整点的最近 48 小时 `normal` 数据。`--start`、`--hours` 可固定演示窗口；`--no-observations` 只建立资料。
- 初始化保留已有管理员修改。底图使用原创示意图 `/assets/maps/demo-campus-v1.png`，固定绑定虚构 `demo-campus` 的布局 v1、1000×700 尺寸；不代表真实地理位置。旧 M1 未改动的空图占位会升级为该内置图，管理员自定义图片、名称、尺寸或版权说明保持原样。
- 一小时生成 13 条观测：2 × 4 水环境指标 + 2 个天气指标 + 3 个空气指标。
- 支持 `normal / turbidity / missing`。缺失场景保留 `null` 和 `quality_status=missing`；浑浊场景增加固定日时段峰值。
- 固定种子、场景版本、参数、站点指标配置和窗口时，批次 key 相同，重复命令不新增记录。相同时间的基础噪声由种子、站代码、指标代码和观测时间确定。
- 不同窗口或种子属于不同批次，并保留批次、参数快照、状态、计数和耗时。默认查询仅返回选定场景的最新成功批次；旧批次通过 `simulation_run` 参数读取。
- 开始时间必须有时区并对齐整点；一次限 1～744 小时及最多 50000 个观测点。M1 不自动清理历史模拟批次，应避免无限频繁重跑大窗口。

## CSV 历史导入

管理员先在后台登记 `DataSource`，并确定来源类型和许可。CSV 必须使用 UTF-8，单位与指标定义严格一致。

```csv
station_code,metric_code,value,unit,observed_at,source_code,quality_status
demo-water-01,ph,7.2,pH,2020-01-01T08:00:00+08:00,history-example,valid
demo-water-01,ph,,pH,2020-01-01T09:00:00+08:00,history-example,missing
```

上例 `history-example` 为需自行登记的数据源代码，不会被程序自动创建。

```sh
.venv/bin/python backend/manage.py import_observations /absolute/path/history.csv --dry-run
.venv/bin/python backend/manage.py import_observations /absolute/path/history.csv
```

必需列：`station_code,metric_code,value,unit,observed_at,source_code`。可选列：`quality_status,simulation_run_id`。

- `value` 空白表示缺失，不能用 0 代替；质量状态不填写时按有值/无值推导 `valid/missing`。
- 时间必须带时区，存储保留原始观测时刻，`ingested_at` 单独记录本次入库时间。
- 所有行先校验，再原子写入。任一行单位错误、NaN/Inf、超出指标输入范围、站点类型错误、来源/模拟批次不一致，整批不写。
- 去重依据来源、站点、指标、观测时刻和模拟批次。完全相同观测跳过；同一观测不同数值或质量状态视为冲突，整批拒绝，避免悄悄覆盖历史。
- 模拟来源必须关联对应且成功的 `simulation_run_id`，并处于批次时间范围内；其他来源不得关联模拟批次。
- 单次上限 10 MB / 10000 行。M1 的观测后台只读，通过命令录入，保留可追溯历史。

## 公共 API

统一前缀 `/api/v1/`。公共端点仅允许读取；分页/错误/信封由 `common` 统一处理。

| 路径 | 主要参数/响应 |
| --- | --- |
| `regions/` | 区域 `id,slug,name,description,is_demo` |
| `places/`、`places/<uuid>/` | `region` 支持 slug 或 UUID，列表支持 `kind`；返回相对坐标、底图版本 ID、来源和水体 ID |
| `maps/` | `region` 默认 `demo-campus`；返回底图与已发布的 `points` |
| `stations/` | 可按 `region,kind,place,water_body` 筛选；`water_body` 为公开水体 UUID；station `code` 全局唯一 |
| `water-bodies/` | 已发布河流/湖泊，可用区域 slug 或 UUID 参数 `region` 筛选；省略时返回所有区域 |
| `metrics/` | 指标代码、单位、适用站类型、允许输入范围 |
| `data-sources/` | 已启用数据源及许可/出处 |
| `observations/` | `region,station,metric,source_type,source,scenario,simulation_run,start,end,limit`；有界原始样例 |
| `observation-series/` | 单站多指标完整窗口聚合；参数和统计语义见下文 |
| `simulation-runs/` | 成功批次目录，支持 `region,station,source,scenario`，标准分页 |
| `weather/`、`air-quality/` | 地区、来源、模拟标记、观测时间、`metrics` 和便利字段 |
| `weather-alerts/` | `status=not_connected`；空列表不表示无真实预警 |
| `dashboard/` | 按一个来源/批次返回地点与站点数量、批次观测数量、最新时刻各站点指标 |
| `contents/`、`contents/<uuid>/` | 只返回发布内容；列表可筛选 `category,plant_label,search` |
| `routes/`、`routes/<uuid>/` | 只返回已发布路线；节点按 `order` 排序，隐藏未发布地点 |

### 原始观测查询 `observations/`

- `source_type` 默认 `simulation`，可选 `api/dataset/simulation/manual`；不接受 `all` 或多个类型。
- `station`、`metric`、`source` 支持代码或 UUID。
- 模拟查询默认选 `scenario=normal` 最新成功批次，支持 `turbidity/missing` 或明确的 `simulation_run` UUID。
- 模拟及非模拟查询若存在多个匹配来源，必须提供 `source`，不把多个来源悄悄拼成一条曲线。指定批次后，仅使用该批次的来源。非模拟查询不接受 `scenario` 或 `simulation_run`。
- `start/end` 为带时区 ISO 时间，区间是 `[start,end)`，最大 31 天；默认以所选数据最新时刻为终点查最近 48 小时。
- `limit` 限 1～1000 个点，返回时间递增的前 limit 个点；分页的 `count` 也仅反映这个有界结果。需要完整曲线与统计时使用 `observation-series/`，不能把截断结果误当成全量统计。
- 每条记录提供 `station_id,station_code,metric_code,value,unit,observed_at,ingested_at,source_id,source_type,is_simulated,quality_status,simulation_run_id`。
- 空值始终序列化为 `null`。已有观测的指标不允许修改单位/适用类型，已有观测的来源不允许修改类型。

### 完整窗口序列 `observation-series/`

公开 GET，不需要登录；返回 `data` 对象，不使用列表分页。请求示例：

```text
/api/v1/observation-series/?region=demo-campus&station=demo-water-01&metrics=ph,dissolved_oxygen&source_type=simulation&source=demo-normal&hours=48&max_points=48
```

| 参数 | 规则 |
| --- | --- |
| `region` | 区域 slug 或 UUID；默认 `demo-campus` |
| `station` | 必填，监测站代码或 UUID；必须属于所选区域并处于公开、启用状态 |
| `metrics` | 可选，英文逗号分隔的 1～9 个不重复指标代码；必须适用该站类型。省略时选该类型全部指标，超过 9 个则要求显式选择 |
| `source_type` | 默认 `simulation`；可选 `api,dataset,simulation,manual`，不接受合并类型 |
| `source` | 来源代码或 UUID；必须启用且类型匹配。多个候选来源时必填 |
| `scenario` | 仅模拟来源使用场景代码；未指定批次时默认 `normal` |
| `simulation_run` | 可选成功批次 UUID，必须包含所选公开站点，且与指定来源匹配。指定批次但省略 `scenario` 时不强制 normal；两者同时指定则必须一致 |
| `hours` | 默认 48，整数 1～744；与 `start/end` 互斥 |
| `start`、`end` | 必须成对提供带时区的 ISO 8601 时间，区间 `[start,end)`；必须递增且最长 31 天 |
| `max_points` | 每指标最多多少个时间桶，整数 1～240，默认 120；实际桶数可能更少 |

以上参数均不可重复传入。无效指标、来源/场景冲突、失败批次、越界参数等返回 400；不存在的区域返回 404。

选择来源与批次先于时间聚合：只使用一个来源；模拟模式额外只使用一个成功批次。默认按匹配批次的创建时间选择最新批次，不把多个批次拼接。没有指定窗口时，终点为所选站点、来源、批次最新的非未来观测时间加 1 秒，并限制不晚于当前时间；没有观测则用当前时间。起点为终点减 `hours`，因此历史批次不会冒充实时数据。需要按批次结束时间对齐整点时，客户端显式传入 `start/end`；当前小程序即采用此方式。

窗口内、所选指标合计最多 **50000 条原始观测**。超过上限直接拒绝，要求缩短窗口或减少指标，不静默截取前半段。聚合覆盖完整窗口：`bucket_seconds = max(1, ceil(窗口秒数 / max_points))`，最后一个桶可以较短。小时模拟数据建议 48 小时用 `max_points=48`，避免细于已知采样周期的空桶造成额外断点。

返回的 `data` 包含 `region,station,source,source_type,is_simulated,simulation_run_id,status,window,bucket_seconds,series,notice`。`status=available` 表示窗口内有原始记录，即使记录全为缺失；没有原始记录为 `unavailable`。没有匹配来源时 `source` 可为 `null`，仍返回适用指标的空窗口网格。每项 `series`：

- `metric`：`code,name,unit`，不同指标分别统计，单位来自不可随历史观测重标记的指标定义。
- `latest`：窗口内该指标最后一条原始记录的 `value,observed_at,quality_status`；不是最后一个有效值，也不是桶均值。最新记录可能缺失或存疑；没有记录时为 `null`。显示数值前需检查质量状态。
- `summary`：`valid_count,missing_count,suspect_count` 是窗口内原始记录数量；`min,max,mean` 只使用 `valid` 原始值。均值按记录计数，不是先算各桶均值再平均，也不是按时间加权。没有有效值时三项统计均为 `null`。
- `points`：每个时间桶的 `at,value,min,max,valid_count,missing_count,suspect_count,quality_status`。`at` 是桶起点，不能标成实际采样时刻；原始采样时刻见 `latest.observed_at`。
- 桶中只要存在存疑记录，`quality_status=suspect`；否则存在缺失记录或完全没有记录时为 `missing`。这两类桶的 `value` 均为 `null`，即使桶里还存在有效记录也不连线；有效记录的 `min/max` 与计数仍保留。纯有效桶的 `value` 为有效原始值的均值。
- 完全无记录的空桶计数为 0；它形成图表断点，但不虚构一条缺失观测，也不会增加 `summary.missing_count`。数值 `0` 始终保留，不以缺失值替代。

### 成功批次目录 `simulation-runs/`

公开 GET，使用标准 `{data: [...], meta: {...}}` 分页：默认每页 20、最多 100，客户端需跟随 `meta.next` 获取后续页。

- `region` 为 slug 或 UUID，默认 `demo-campus`；可进一步传 `station`（代码或 UUID）、`source`（代码或 UUID）和 `scenario`（场景代码）。这些过滤参数不可重复。
- 只返回 `status=succeeded`、模拟来源已启用且有匹配公开监测站观测的批次；按 `created_at` 降序排列。未提供 `scenario` 时列出所有场景，不默认为 normal。
- 每条返回 `id,source,scenario,start,end,created_at,counts,generator_version`；`scenario` 只包含 `code,name`。
- `counts` 是符合本次区域/站点筛选的公开原始记录数，不是该批次的全局写入数，不泄露其他区域或隐藏站点的记录量。失败信息和内部生成参数不在公开目录返回。
- 默认示范的三个场景分别属于 `demo-normal/demo-turbidity/demo-missing` 三个来源；要查看其他场景，需选择对应来源。来源不同不会自动合并。

### 公开目录与静态底图约束

监测站必须启用；关联地点或水体地点被隐藏后，站点及其观测、成功批次关联计数均不再公开。`water-bodies/?region=...` 只返回该区域已发布的河流/湖泊，`stations/?region=...&water_body=<uuid>` 只返回匹配水体的公开站点。没有关联地点/水体的启用独立站点仍可公开。

`maps/?region=...` 只返回启用底图，每幅底图的 `points` 只含绑定该版本的已发布地点。地点相对坐标必须成对处于 0～1，并与底图属于同一区域。

- 内置示意图只允许 `/assets/maps/demo-campus-v1.png`，且严格限定虚构 `demo-campus`、v1、1000×700。图源为 HYHQ 原创静态布局，不含真实 GIS 或导航含义。
- 其他图片必须使用 HTTPS 地址；宽高均为 1～8192 像素，版本为正整数。
- 已关联点位的底图不能原地改变所属区域、版本、宽高或已存在的图片 URL；后台对应字段只读。更换图片应新建版本并重新布点，避免坐标偏移。
- 旧版空图片允许首次绑定；`seed_demo` 仅自动升级名称、尺寸及版权说明均未改动的原 M1 占位，保留管理员自定义内容。外部图片还应由维护者使用不可覆盖的版本化地址，模型校验不能阻止远端同 URL 内容被替换。

### 模拟天气与空气

两者均返回 `region,source_type=simulation,is_simulated=true,status,observed_at,metrics,source,station,simulation_run_id,notice`。

- 天气便利字段：`temperature,humidity,condition="模拟天气"`。
- 空气便利字段：`pm25,pm10,no2`；`aqi` 和 `aqi_standard` 均为 `null`，不生成伪官方 AQI。
- 无批次数据时 `status=unavailable`、`observed_at=null`、`metrics=[]`。
- `weather-alerts` 未接上游，也未伪造官方预警。所有响应显式说明模拟或未接入状态。

## 验证

```sh
scripts/manage.sh test ecology knowledge
```

测试覆盖模拟重放/幂等/缺失/峰值、失败批次回滚、历史导入原子性与去重、字段/来源/区域关联、查询边界和草稿不可见。M2 新增完整窗口聚合、真实 50000/50001 条边界、零值/缺失/存疑、来源与批次隔离、公开计数和地图版本保护测试。本轮完整 PostgreSQL 后端共 158 项通过；真实 HTTP 三场景联调与验证边界见 [M2 核心展示验证记录](../../docs/verification/M2核心展示验证记录.md)。既有 M1/M3 和北京基线证据仍保留，本轮 M2 未部署服务器。

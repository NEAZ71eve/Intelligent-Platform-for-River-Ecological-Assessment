# 生态数据与内容模块（M1）

## 初始化与模拟

从仓库根目录运行（先配置后端环境并完成迁移）：

```sh
.venv/bin/python backend/manage.py seed_demo
.venv/bin/python backend/manage.py generate_simulation --scenario missing --start 2026-09-15T00:00:00Z --hours 48 --seed 20260916
.venv/bin/python backend/manage.py generate_simulation --scenario turbidity --start 2026-09-15T00:00:00Z --hours 48 --seed 20260916
```

`seed_demo` 幂等创建虚构的 `demo-campus` 区域、12 个地点、2 个水体、2 个水站、1 个气象站、1 个空气站、9 个指标、3 个场景、3 个对应模拟来源、3 篇科普和1条6节点路线。

- 默认生成截至当前整点的最近 48 小时 `normal` 数据。`--start`、`--hours` 可固定演示窗口；`--no-observations` 只建立资料。
- 初始化保留已有管理员修改。底图默认只登记尺寸和点位布局，`image_url` 为空；实际图片导览属于后续 M2。
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
| `stations/` | 可按 `region,kind,place` 筛选；station `code` 全局唯一 |
| `metrics/` | 指标代码、单位、适用站类型、允许输入范围 |
| `data-sources/` | 已启用数据源及许可/出处 |
| `observations/` | `region,station,metric,source_type,source,scenario,simulation_run,start,end,limit` |
| `weather/`、`air-quality/` | 地区、来源、模拟标记、观测时间、`metrics` 和便利字段 |
| `weather-alerts/` | `status=not_connected`；空列表不表示无真实预警 |
| `dashboard/` | 按一个来源/批次返回地点与站点数量、批次观测数量、最新时刻各站点指标 |
| `contents/`、`contents/<uuid>/` | 只返回发布内容；列表可筛选 `category,plant_label,search` |
| `routes/`、`routes/<uuid>/` | 只返回已发布路线；节点按 `order` 排序，隐藏未发布地点 |

### 观测查询

- `source_type` 默认 `simulation`，可选 `api/dataset/simulation/manual`；不接受 `all` 或多个类型。
- `station`、`metric`、`source` 支持代码或 UUID。
- 模拟查询默认选 `scenario=normal` 最新成功批次，支持 `turbidity/missing` 或明确的 `simulation_run` UUID。
- 非模拟查询若存在多个来源，必须提供 `source`，不把多个来源悄悄拼成一条曲线。
- `start/end` 为带时区 ISO 时间，区间是 `[start,end)`，最大 31 天；默认以所选数据最新时刻为终点查最近 48 小时。
- `limit` 限 1～1000 个点，返回时间递增的前 limit 个点；分页的 `count` 也仅反映这个有界结果。需要完整曲线应缩小站点/指标/时间范围，不能把截断结果误当成全量统计。
- 每条记录提供 `station_id,station_code,metric_code,value,unit,observed_at,ingested_at,source_id,source_type,is_simulated,quality_status,simulation_run_id`。
- 空值始终序列化为 `null`。已有观测的指标不允许修改单位/适用类型，已有观测的来源不允许修改类型。

### 模拟天气与空气

两者均返回 `region,source_type=simulation,is_simulated=true,status,observed_at,metrics,source,station,simulation_run_id,notice`。

- 天气便利字段：`temperature,humidity,condition="模拟天气"`。
- 空气便利字段：`pm25,pm10,no2`；`aqi` 和 `aqi_standard` 均为 `null`，不生成伪官方 AQI。
- 无批次数据时 `status=unavailable`、`observed_at=null`、`metrics=[]`。
- `weather-alerts` 未接上游，也未伪造官方预警。所有响应显式说明模拟或未接入状态。

## 验证

```sh
.venv/bin/python backend/manage.py test ecology knowledge
```

测试覆盖模拟重放/幂等/缺失/峰值、失败批次回滚、历史导入原子性与去重、字段/来源/区域关联、查询边界和草稿不可见。实际运行结果以项目验证报告为准。

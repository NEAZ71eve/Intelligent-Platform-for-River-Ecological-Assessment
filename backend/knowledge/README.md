# 科普内容与预设路线

M2-B01/B02 复用管理员发布的 `Content.category`、`Content.plant_label` 和地点关联，不新增通用标签模型。以下接口均为免登录只读接口，响应使用项目统一 `data` 包装；列表另含 `meta.count/next/previous/page/page_size`。

## 科普发现

`GET /api/v1/contents/` 支持以下组合筛选，条件之间均为 AND：

| 参数 | 语义 |
| --- | --- |
| `category` | `plants`、`water`、`green`、`travel`；其他值返回 400 |
| `plant_label` | 精确匹配 1～50 位字母、数字、`-` 或 `_`；可使用管理员自定义标签；无匹配返回空列表 |
| `place` | 公开地点 UUID 或 slug；只返回直接关联该地点的文章，不附加通用文章；未知和下架地点均返回 404 |
| `region` | 区域 UUID 或 slug；返回该区公开地点关联文章，以及确实未关联地点的通用文章；未知区域返回 404 |
| `search` | 去除首尾空白后，不超过 100 字符；在标题或摘要内不区分大小写匹配，不检索正文 |

空参数视为未选择；同一筛选参数重复提供时返回 400。未传 `region` 时浏览所有已发布文章。指定 `region` 时，关联下架地点的文章不计入任何区域或通用文章。

排序固定为发布时间倒序（空值最后）、创建时间倒序、UUID 升序，保证相同时间记录的分页顺序稳定。`GET /api/v1/contents/<UUID>/` 只能取得已发布文章。

列表和详情均保留来源 `source`、示范标记 `is_demo`，并提供：

```json
{
  "place": "公开地点 UUID 或 null",
  "place_summary": {
    "id": "地点 UUID",
    "slug": "地点 slug",
    "name": "地点名称",
    "kind": "plant",
    "region": "区域 UUID",
    "region_name": "区域名称",
    "is_demo": true
  }
}
```

文章关联地点下架后，文章本身仍可公开浏览，但 `place` 和 `place_summary` 同时为 `null`。未关联地点的文章也返回这两个空字段。草稿文章始终不返回。

`GET /api/v1/content-tags/` 使用完全相同的筛选参数，返回筛选结果中的公开分类和植物标签计数；只包含计数大于零的选项。需要保持选项稳定的客户端可仅传当前 `region` 获取目录，再为文章列表叠加其他条件。

```json
{
  "categories": [{"value": "plants", "name": "植物知识", "count": 2}],
  "plant_labels": [{"value": "daisy", "name": "雏菊类花卉", "count": 1}],
  "content_count": 2
}
```

分类按后台定义顺序排列，植物标签按标签值排序。五种识别标签有中文名称，其他管理员标签以原值显示；不限制为现有识别模型的五类。

## 预设路线

- `GET /api/v1/routes/?region=<UUID或slug>` 返回标准分页的已发布路线；不传区域时返回所有公开路线。未知区域返回 404，重复区域参数返回 400。
- `GET /api/v1/routes/<UUID>/` 返回已发布路线详情；下架路线返回 404。
- 路线按标题、UUID 排序；`stops` 按管理员设置的 `order`、UUID 排序，每个节点包含已有公开地点详情，支持跳转地点。
- `stop_count` 严格等于本次返回的公开节点数，`region_name` 提供所属区域名称。`source` 为管理员填写的出处，`is_demo` 表示示范路线。
- 下架地点、被删除的节点及异常跨区域关联不返回，也不计入节点数；不会返回其地点、节点 ID 或节点备注。保留公开节点原来的 `order`，因此下架节点可能留下顺序编号间隔。路线没有公开节点时仍返回路线及 `stops: []`、`stop_count: 0`。
- 列表/详情预取公开节点和地点关系，查询数不会随路线或节点数量增加。该服务是预设学习路线，不提供实时导航、距离或到访验证。

## 本地针对性检验

```sh
python manage.py test knowledge --noinput
```

测试涵盖筛选交集、公开目录计数、分页稳定、下架关联脱敏、公开来源、路线顺序和增删节点，以及列表/详情查询数量。使用项目配置的 PostgreSQL；测试数据库与开发数据隔离，不对服务器执行命令。`seed_demo` 的三篇原创示范稿已关联校园学习点；`seed_recognition_knowledge` 提供五篇无地点关联的通用花卉稿，两者均保留已有管理员修改。

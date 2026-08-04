# spatial_analysis 使用说明

`spatial_analysis` 用于执行 Agent 生成的通用 GIS 分析 spec。它只负责空间分析和 DataRegistry 资产注册；需要把结果显示到问数看板地图时，继续调用 `visual_interaction`。

## 适用场景

- 点周边缓冲区：例如站点 3km 范围。
- 空间相交：例如筛选缓冲区内的污染源、站点或事件。
- 空间聚合：例如按行业、区县、类型统计相交结果。
- 属性过滤：例如只保留 VOCs 排放量大于 0 的工业企业。
- 距离排序和最近邻：例如站点最近 20 个污染源。
- Top N：例如 VOCs 排放量最高的 10 家企业。
- 上风向扇区：例如当前风向下，站点上风向 10km 内污染源。

## 推荐流程

1. 先用查询工具、认知地图或 `create_map_point_asset` 获取真实数据资产 `data_id`。
2. 调用 `spatial_analysis`，用 spatial-spec 描述输入、步骤和输出。
3. 读取返回的 `data.outputs[*].data_id`。
4. 调用 `visual_interaction` 创建 `polygon-layer`、`point-layer` 或其他地图程序。

## spatial-spec 结构

```json
{
  "version": "spatial-spec.v1",
  "intent": "花都师范站点3km缓冲区",
  "inputs": {
    "point": {
      "type": "data-asset",
      "data_id": "map_point_asset:v1:..."
    }
  },
  "steps": [
    {
      "id": "buffer_3km",
      "op": "buffer",
      "input": "point",
      "distance": 3000,
      "unit": "meter"
    }
  ],
  "outputs": {
    "buffer_layer": {
      "type": "layer",
      "from_step": "buffer_3km",
      "name": "花都师范3km缓冲区"
    }
  }
}
```

`outputs` 可以写成对象，也可以写成列表。对象形式更适合 Agent 自然生成，`from_step` 指向步骤结果，键名作为输出 ID。

## 输入类型

### inline-feature

适合已知单个点或面。

```json
{
  "type": "inline-feature",
  "geometry": {"type": "Point", "coordinates": [113.2146, 23.3917]},
  "properties": {"name": "花都师范"}
}
```

### data-asset

适合引用已有 DataRegistry 资产。

```json
{
  "type": "data-asset",
  "data_id": "map_point_asset:v1:..."
}
```

如果资产元数据包含 `longitude_field`/`latitude_field` 或 `map_capabilities.lon_field`/`lat_field`，可以不写 `geometry`。如果资产没有元数据，显式写：

```json
{
  "type": "data-asset",
  "data_id": "pollution_source_asset:v1:...",
  "geometry": {"lon": "longitude", "lat": "latitude"}
}
```

## 当前支持的操作

### buffer

对点要素生成缓冲区。

```json
{"id": "buffer_3km", "op": "buffer", "input": "point", "distance": 3000, "unit": "meter"}
```

### intersect

筛选点和面的空间相交结果。

```json
{"id": "sources_in_buffer", "op": "intersect", "left": "pollution_sources", "right": "buffer_3km"}
```

### filter

按属性过滤点或表记录。

```json
{
  "id": "vocs_sources",
  "op": "filter",
  "input": "sources_in_buffer",
  "where": {
    "source_type": {"eq": "工业企业"},
    "emission_vocs": {"gt": 0}
  }
}
```

支持的比较符包括：`eq`、`neq`、`gt`、`gte`、`lt`、`lte`、`contains`、`in`。

### distance / nearest

`distance` 会给左侧点要素增加到右侧最近目标点的 `distance_m`。`nearest` 会在此基础上按距离升序取最近 N 个。

```json
{"id": "nearest_sources", "op": "nearest", "left": "pollution_sources", "right": "station", "limit": 20}
```

可选 `max_distance` 或 `distance` 限制最大距离，单位为米。

### aggregate

对空间分析结果做简单计数聚合。

```json
{
  "id": "summary",
  "op": "aggregate",
  "input": "sources_in_buffer",
  "group_by": ["industry_type"],
  "metrics": [{"func": "count", "as": "count"}]
}
```

`aggregate` 支持 `count`、`sum`、`avg`、`max`、`min`。排放量统计示例：

```json
{
  "id": "summary",
  "op": "aggregate",
  "input": "vocs_sources",
  "group_by": ["industry_type"],
  "metrics": [
    {"func": "count", "as": "count"},
    {"func": "sum", "field": "emission_vocs", "as": "vocs_sum"},
    {"func": "max", "field": "emission_vocs", "as": "vocs_max"}
  ]
}
```

### top_n

按字段排序取前 N 条。

```json
{"id": "top_vocs", "op": "top_n", "input": "vocs_sources", "field": "emission_vocs", "limit": 10, "order": "desc"}
```

### upwind_sector

结合风向筛选站点上风向扇区内污染源。`wind_from_degrees` 表示风从哪个方向吹来，0 为北、90 为东、180 为南、270 为西。

```json
{
  "id": "upwind_sources",
  "op": "upwind_sector",
  "sources": "pollution_sources",
  "receptor": "station",
  "wind_from_degrees": 180,
  "angle_degrees": 60,
  "distance": 10000,
  "unit": "meter"
}
```

## 结果展示

`spatial_analysis` 返回的每个输出都会带 `data_id` 和 `asset_schema`。展示时把 `data_id` 交给 `visual_interaction`：

- `spatial_polygon_asset`：用 `map-spec create polygon-layer`。
- `spatial_point_asset`：用 `map-spec create point-layer`。
- `analysis_table_asset`：作为数据文件路径交给后续分析或制表流程。

不得在 `spatial_analysis` 失败后声称缓冲区或相交图层已经生成。

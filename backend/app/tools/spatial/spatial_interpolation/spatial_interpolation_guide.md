# spatial_interpolation 使用说明

`spatial_interpolation` 用于执行污染物浓度空间插值分析。它只负责生成可用于地图分析渲染的 DataRegistry 资产，不生成静态图片；需要把插值结果显示到问数地图时，必须继续调用 `gisctl` 创建地图图层。

## 适用场景

- 站点浓度插值：例如 PM2.5、O3、NO2、VOCs 浓度空间分布。
- 监测点稀疏但需要连续面表达：例如城市或区县范围内的浓度趋势图。
- 地图展示插值渲染面：例如把插值后的浓度连续面新增为地图分析图层。
- 可选叠加等值线：例如在插值渲染面上叠加浓度等值线辅助读数。
- 快速分析渲染：无 PyKrige 时可使用 `idw`，或在 `kriging` 缺依赖时设置 `allow_fallback=true`。

## 推荐流程

1. 先获得真实点位浓度数据资产 `data_id`，数据必须包含经度、纬度和值字段。
2. 调用 `spatial_interpolation`，指定 `data_id`、`lon`、`lat`、`value`、`pollutant`、`unit`、`method`。
3. 检查返回结果是否 `success=true`，并读取 `data.outputs`。
4. 地图展示优先使用 `outputs` 中 `id="surface"` 的 `data_id`。
5. 调用 `gisctl`：

```json
{
  "family": "map-spec",
  "action": "create",
  "kind": "interpolation-layer",
  "data_id": "interpolation_surface_asset:v1:...",
  "layer_id": "pm25_interpolation_surface",
  "name": "PM2.5插值渲染",
  "fit_bounds": true
}
```

6. 如用户需要等值线辅助读数，可再使用 `outputs` 中 `id="contours"` 的 `data_id` 调用 `gisctl map-spec create line-layer` 叠加等值线。
7. 调用 `wait_map_program_receipt` 等待前端回执。没有有效回执前，不得声称插值分析图层已经显示成功。

## 输入资产链路

`spatial_interpolation` 的 `data_id` 必须是 DataRegistry 中已经注册成功的点位数据资产。不得手工构造类似 `city_pm25_interpolation:v1:20260623` 的语义 ID，也不得在 `execute_python` 中直接写入 `backend_data_registry/datasets/*.json` 后把文件名或自造 ID 当成可用资产。

如果当前只有 SQL 查询结果、Python 计算结果或临时记录，必须先把经度、纬度和值字段整理成点位记录，并通过项目资产注册链路生成真实 `data_id`。在后端代码路径中应使用 `data_registry.register_dataset` 或已有资产生成工具完成注册；随后只把注册返回的 `data_id` 传给 `spatial_interpolation`。

当 `spatial_interpolation` 返回 `data_id not found` 时，说明传入 ID 不在 DataRegistry 索引中。此时不要反复使用同一个 ID 重试；应回到上一步创建或查找真实点位资产，再重新调用插值工具。插值成功后，地图渲染必须使用返回结果中的 `surface.data_id` 创建 `gisctl interpolation-layer`，而不是使用原始点位资产或手工推测的插值 ID。

## spec 示例

```json
{
  "data_id": "station_concentration_asset:v1:...",
  "lon": "longitude",
  "lat": "latitude",
  "value": "pm25",
  "pollutant": "PM2.5",
  "unit": "ug/m3",
  "method": "idw",
  "grid_size": 60,
  "contour_levels": 10,
  "allow_fallback": true
}
```

## 字段说明

- `data_id`：DataRegistry 数据资产 ID。
- `lon` / `lat`：经度、纬度字段名。
- `value`：浓度字段名，必须是可转成数字的值。
- `pollutant`：污染物名称，用于输出标题和资产元数据。
- `unit`：浓度单位，例如 `ug/m3`。
- `method`：`kriging`、`idw`、`linear`、`cubic`、`nearest`。
- `grid_size`：插值网格边长，建议 40-100。过大会增加计算和渲染成本。
- `contour_levels`：等值线级数，建议 6-15。
- `allow_fallback`：`kriging` 缺少 PyKrige 时是否允许退回 `idw`。

## 方法选择

- `kriging`：适合需要地统计插值表达的正式分析；需要 PyKrige。
- `idw`：稳健、依赖少，适合问数模式快速生成插值图层。
- `linear` / `cubic`：适合点位较多且分布较均匀的数据。
- `nearest`：适合快速粗略分区，不适合平滑浓度面表达。

如果用户明确要求“克里金”，优先使用 `method="kriging"`。若环境缺少 PyKrige 且用户允许快速渲染，可以设置 `allow_fallback=true`，并在回答中说明实际使用了 IDW fallback。

## 输出解释

`spatial_interpolation` 成功后通常返回：

- `outputs[id="grid"]`：插值网格点资产，适合后续分析或表格检查。
- `outputs[id="surface"]`：插值渲染面资产，适合用 `gisctl interpolation-layer` 作为地图主图层。
- `outputs[id="contours"]`：等值线资产，适合用 `gisctl line-layer` 作为可选叠加层。

不要把 `grid` 点资产或单独的 `contours` 等值线当成最终地图插值图层。用户要求“在地图上新增插值分析图层”时，应使用 `surface.data_id` 创建 `interpolation-layer`，并等待前端回执。

## 结果校验

调用后至少检查：

- `success` 是否为 `true`。
- `metadata.method_applied` 是否符合预期。
- `outputs` 是否包含 `surface`，且 `record_count > 0`。
- 如果叠加等值线，再检查 `contours.record_count > 0`。
- 地图展示是否收到 `wait_map_program_receipt` 的有效完成信号。

不得在以下情况声称图层已显示：

- 只生成了 `interpolation_records.json` 或 GeoJSON 点网格。
- 只生成了 `map_point_asset`。
- 只生成了 `contours` 等值线，没有生成或渲染 `surface` 插值面。
- `surface.record_count` 为 0。
- `gisctl` 没有返回 map program。
- 没有收到地图前端回执。

# create_report_chart 数据输入契约

`create_report_chart` 必须通过 `data` 或 `data_id` 至少获得一种数据输入，不支持文件路径。两者都提供时，内联 `data` 用于渲染，`data_id` 仅用于来源追踪。

## 选择输入方式

- 数据量较小且已经整理为目标图型结构：直接传 `data`。
- 上游已经保存了图表数据资产：传 DataRegistry `data_id`。
- 已有内联图表数据，同时需要保留原始数据溯源：同时传 `data` 和来源 `data_id`。
- 只有 JSON、CSV、Excel 等文件路径：先读取并整理为 `data`，或者注册为 DataRegistry 数据资产后传 `data_id`；不要把路径传给本工具。

## 内联 data

`data` 是结构化图表数据，不是 ECharts option。普通图表常用结构如下。

单序列柱状图、折线图或饼图：

```json
{
  "labels": ["A", "B"],
  "values": [10, 20]
}
```

也可使用等价的 `x + y`。多序列柱状图或折线图使用：

```json
{
  "labels": ["一月", "二月"],
  "series": [
    {"name": "PM2.5", "values": [35, 31]},
    {"name": "PM10", "values": [62, 58]}
  ]
}
```

其他图型的数据结构应按 `references/index.md` 路由到对应图型文档读取。

## data_id

`data_id` 必须是有效的 DataRegistry 数据资产 ID。未提供内联 `data` 时，工具会通过 `ExecutionContext.get_raw_data(data_id)` 自动读取；Agent 无需调用 `get_raw_data`，也不应猜测底层物理文件路径。

普通 `bar`、`line`、`pie` 等图表不会自动推断任意记录中的横轴、纵轴、数值或系列字段。它们的 `data_id` 应预先保存为 `labels+values`、`x+y`、`series` 或对应图型要求的数据对象。

领域图表 `aqi_calendar`、`pollutant_calendar`、`generic_pollutant_wind_rose` 和 `pollutant_wind_rose` 支持按各自领域文档消费 `records`。调用前必须读取对应参考文档并确认字段契约。

## 不支持文件路径

schema 中没有 `file_path`、`data_path` 或类似参数。以下输入无效：

```json
{
  "chart_type": "bar",
  "title": "示例",
  "file_path": "/path/to/data.json"
}
```

不要把文件路径塞入 `data_id`，也不要根据 DataRegistry 目录结构推测数据文件。文件数据必须先转换为内联图表对象，或通过正式注册链路获得真实 `data_id`。

# create_report_chart 数据输入契约

`create_report_chart` 必须通过 `data` 或 `file_path` 至少获得一种数据输入。两者都提供时，内联 `data` 用于渲染，`file_path` 仅用于来源追踪。

## 选择输入方式

- 数据量较小且已经整理为目标图型结构：直接传 `data`。
- 上游已经保存了会话数据文件：传工具返回的绝对 `file_path`。
- 已有内联图表数据，同时需要保留原始数据溯源：同时传 `data` 和来源 `file_path`。
- 已有整理成目标图型结构的会话 JSON 数据文件：直接传其 `file_path`。
- CSV、Excel 或尚未整理的记录文件：先用 `execute_python` 整理并通过 `save_data()` 保存，再传返回的 `file_path`。

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

## file_path

`file_path` 必须是上游工具返回、且属于当前会话的数据文件绝对路径。未提供内联 `data` 时，工具会通过 `ExecutionContext.get_raw_data(file_path)` 自动读取，Agent 无需自行读取文件。

普通 `bar`、`line`、`pie` 等图表不会自动推断任意记录中的横轴、纵轴、数值或系列字段。它们的 `file_path` 应预先保存为 `labels+values`、`x+y`、`series` 或对应图型要求的数据对象。

领域图表 `aqi_calendar`、`pollutant_calendar`、`generic_pollutant_wind_rose` 和 `pollutant_wind_rose` 支持按各自领域文档消费 `records`。调用前必须读取对应参考文档并确认字段契约。

## 路径约束

只接受当前会话已授权的数据文件路径，不接受猜测路径、跨会话路径或普通外部文件路径。有效调用示例：

```json
{
  "chart_type": "bar",
  "title": "示例",
  "file_path": "/configured/data/root/sessions/agent_session_x/data/chart-input--abc.json"
}
```

不要根据数据目录结构推测路径；只使用查询工具或 `execute_python.save_data()` 明确返回的 `file_path`。

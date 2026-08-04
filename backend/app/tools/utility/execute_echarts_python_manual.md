# execute_echarts_python 工具指导手册

首次使用 `execute_echarts_python` 前应阅读本手册。后续调用可根据任务只重读相关章节。

## 使用边界

- 前端交互式 ECharts 图表使用 `execute_echarts_python`。
- 正式报告 Word/QMD 中的静态图表优先使用 `create_report_chart`。
- 数据清洗、中间计算、文件生成和 matplotlib/seaborn/plotly 绘图使用 `execute_python`。

## 标准数据访问流程

Data is passed between tools using canonical absolute file paths.

1. Use the `file_path` returned by a query or analysis tool.
2. Use the query result's inline records and field schema to understand fields; use `load_data(file_path)` only when full-data processing is necessary.
3. In `execute_echarts_python.code`, call the injected `load_data(file_path)` helper directly.

```python
import json

file_path = "/home/xckj/suyuan/backend/backend_data_registry/sessions/agent_session_x/data/air_quality--example.json"
records = load_data(file_path)

x_data = [record.get("time") for record in records]
y_data = [record.get("PM2_5") for record in records]

option = {
    "xAxis": {"type": "category", "data": x_data},
    "yAxis": {"type": "value"},
    "series": [{"type": "line", "data": y_data}],
}
print(json.dumps(option, ensure_ascii=False))
```

Do not guess or rewrite a path. Reuse the exact path returned by the producing tool.

## 执行环境与跨调用复用

每次 `execute_python` 和 `execute_echarts_python` 调用都是独立执行环境，不保留上次脚本变量。跨调用复用中间结果时：

1. In the first Python call, use `saved_file_path = save_data(result)`.
2. In a later call, use `load_data(saved_file_path)`.

不要依赖前一次调用中的局部变量。

## ECharts stdout 协议

- stdout 每行只能输出一个完整、纯 JSON 的 ECharts option。
- option 顶层必须包含 `series` 数组，不能把 `series` 嵌套在自定义 `data` 字段中。
- 使用 `print(json.dumps(option, ensure_ascii=False))` 输出。
- 多图时逐行输出多个 option，并可用 `expected_charts` 校验数量。
- 不要添加 `CHART_1:` 前缀、Markdown 代码块或自然语言说明。
- option 必须可由 JSON 序列化；JavaScript 回调、Python 函数和 lambda 不能放入 option。
- 序列数据中的 Python `None` 会输出为 JSON `null`，可用于折线缺口。

## 最小正确示例

```json
{
  "expected_charts": 1,
  "code": "import json; records = load_data('/absolute/session/data/file.json'); option = {'xAxis': {'type': 'category', 'data': [r.get('time') for r in records]}, 'yAxis': {'type': 'value'}, 'series': [{'type': 'line', 'data': [r.get('value') for r in records]}]}; print(json.dumps(option, ensure_ascii=False))"
}
```

## 常见错误

- `load_data` reports a missing file: use the exact `file_path` returned by the producing tool.
- 没有生成 visuals：检查 stdout 是否为纯 JSON、option 顶层是否有 `series`。
- 图表数量不匹配：让输出行数与 `expected_charts` 一致。
- JSON 序列化失败：移除 option 中的函数、lambda 或其他不可序列化对象，先在 Python 中计算为静态值。
- 数据文件找不到：不要修补或猜测路径，重用工具返回的 `file_path`。

# execute_echarts_python 工具指导手册

首次使用 `execute_echarts_python` 前应阅读本手册。后续调用可根据任务只重读相关章节。

## 使用边界

- 前端交互式 ECharts 图表使用 `execute_echarts_python`。
- 正式报告 Word/QMD 中的静态图表优先使用 `create_report_chart`。
- 数据清洗、中间计算、文件生成和 matplotlib/seaborn/plotly 绘图使用 `execute_python`。

## 标准数据访问流程

DataRegistry 数据必须通过 `data_id` 访问，不得读取其物理存储文件。

1. 调用 `read_data_registry(data_id=..., list_fields=true)` 查看字段。
2. 需要计算具体数据时，通过 `read_data_registry` 读取相应 view/fields，形成可计算数据快照。
3. 在 `execute_echarts_python.code` 中调用系统注入的 `get_raw_data(data_id)` 获取该快照。

```python
import json

data_id = "air_quality_5min:v1:实际ID"
records = get_raw_data(data_id)

x_data = [record.get("time") for record in records]
y_data = [record.get("PM2_5") for record in records]

option = {
    "xAxis": {"type": "category", "data": x_data},
    "yAxis": {"type": "value"},
    "series": [{"type": "line", "data": y_data}],
}
print(json.dumps(option, ensure_ascii=False))
```

禁止通过以下方式绕过 DataRegistry：

```python
# 错误：猜测并直接读取 DataRegistry 物理文件
with open("/home/.../backend_data_registry/datasets/data.json") as file:
    records = json.load(file)

# 错误：pathlib 同样属于直接文件读取
records = json.loads(Path("/home/.../datasets/data.json").read_text())
```

物理路径可能不存在、随部署变化或与 `data_id` 的内部编码不一致；直接读取也绕过了数据快照和访问状态约束。

## 执行环境与跨调用复用

每次 `execute_python` 和 `execute_echarts_python` 调用都是独立执行环境，不保留上次脚本变量。跨调用复用中间结果时：

1. 在前一次 Python 调用中使用 `saved_data_id = save_data(result)`。
2. 后续先用 `read_data_registry(data_id=saved_data_id, ...)` 读取快照。
3. 再在 Python 代码中使用 `get_raw_data(saved_data_id)`。

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
  "code": "import json; records = get_raw_data('air_quality:v1:实际ID'); option = {'xAxis': {'type': 'category', 'data': [r.get('time') for r in records]}, 'yAxis': {'type': 'value'}, 'series': [{'type': 'line', 'data': [r.get('value') for r in records]}]}; print(json.dumps(option, ensure_ascii=False))"
}
```

调用这段代码前，必须已经通过 `read_data_registry` 读取对应 `data_id` 的可计算数据快照。

## 常见错误

- `get_raw_data` 报“尚未读取”：先调用 `read_data_registry` 读取具体数据，而不只是猜测 ID。
- 没有生成 visuals：检查 stdout 是否为纯 JSON、option 顶层是否有 `series`。
- 图表数量不匹配：让输出行数与 `expected_charts` 一致。
- JSON 序列化失败：移除 option 中的函数、lambda 或其他不可序列化对象，先在 Python 中计算为静态值。
- 数据文件找不到：不要修补物理路径，改用正确的 `data_id` 和 `get_raw_data(data_id)`。

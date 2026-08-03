# execute_echarts_python 工具契约迁移设计

## 背景

`execute_echarts_python` 的数据访问和输出约束目前主要位于图表模式系统提示词中。工具自身的 schema 没有说明 DataRegistry 数据必须通过 `data_id` 访问，也没有要求先读取数据快照。这会导致仅依据原生 tool schema 决策的 Agent 猜测并直接读取 DataRegistry 物理文件路径。

工具的正确用法不能依赖特定模式的系统提示词。调用契约应由工具 schema 和工具专用手册共同负责。

## 目标

- 将 `execute_echarts_python` 的完整调用契约从图表模式提示词迁出。
- 在工具 schema 中直接暴露不可违反的核心约束。
- 通过专用手册承载较长的说明、流程和示例，支持渐进式读取。
- 保留图表模式中的设计流程、样式参考和工具选择信息。
- 用自动化测试防止契约重新分散到系统提示词。

## 非目标

- 不改变 `execute_echarts_python` 的执行逻辑或函数参数结构。
- 不新增运行时路径拦截或 Python AST 校验。
- 不改变 `read_data_registry`、`get_raw_data` 或 `save_data` 的行为。
- 不调整前端 ECharts 渲染协议。

## 方案

采用“核心约束内嵌 + 详细手册渐进读取”的混合方案。

### 工具 schema

`ExecuteEChartsPythonTool.get_function_schema()` 的工具描述必须明确：

1. 首次或不熟悉用法时，先通过 `read_file` 阅读 `backend/app/tools/utility/execute_echarts_python_manual.md`。
2. DataRegistry 数据必须先由 `read_data_registry(data_id=...)` 加载为可计算快照。
3. Python 代码必须使用系统注入的 `get_raw_data(data_id)` 获取 DataRegistry 数据。
4. 禁止使用 `open()`、`pathlib` 或猜测物理文件路径绕过 DataRegistry 访问流程。
5. stdout 每行只能输出一个完整、纯 JSON 的 ECharts option，且顶层必须包含 `series`。

`code` 参数描述应简短重复数据访问和纯 JSON 输出要求，使核心规则在参数生成位置仍然可见。多图、无状态执行、跨调用数据复用、配置序列化限制和正反示例放入专用手册，避免 schema 过长。

### 专用手册

新增 `backend/app/tools/utility/execute_echarts_python_manual.md`，内容包括：

- 工具适用边界及与 `execute_python`、`create_report_chart` 的分工；
- `read_data_registry` → `get_raw_data(data_id)` 的标准数据流；
- 禁止直接读取 DataRegistry 物理路径的原因和错误示例；
- 每次 Python 执行无状态以及 `save_data()` 的跨调用复用方式；
- 单图、多图 stdout 协议和 `expected_charts` 的含义；
- ECharts option 顶层 `series`、纯 JSON 可序列化配置等要求；
- 最小正确示例和常见错误示例。

手册不复制与图表设计无关的通用 Python/报告生成说明。

### 图表模式提示词

从 `backend/app/agent/prompts/chart_prompt.py` 删除所有 `execute_echarts_python` 调用契约，包括：

- `get_raw_data(data_id)` 与硬编码路径约束；
- Python 无状态和 `save_data()` 说明；
- stdout、纯 JSON、多图和顶层 `series` 协议；
- 函数序列化等工具专属限制；
- 数据访问、输出格式及错误结构的正反代码示例。

保留以下内容：

- 图表需求分析、设计确认和生成流程；
- 数据字段分析步骤；
- 内置样式、自定义模板和官方示例参考；
- 最终选择 `execute_echarts_python` 生成交互式 ECharts 图表的说明。

提示词可以指明应使用哪个工具，但不再承担如何正确调用该工具的契约职责。

## 测试策略

按 TDD 实施：

1. 先新增 schema 契约测试，断言工具描述包含专用手册路径、先读快照、`get_raw_data(data_id)` 和禁止物理路径读取等核心信息。
2. 新增图表提示词边界测试，断言提示词仍选择 `execute_echarts_python`，但不再包含 `get_raw_data(`、DataRegistry 文件路径示例、stdout 协议和工具专属示例章节。
3. 运行新增测试并确认其在生产代码修改前按预期失败。
4. 最小修改 schema、提示词并新增手册，使测试通过。
5. 运行 `backend/tests/test_execute_echarts_python_tool.py` 及相关提示词测试，确认现有 ECharts visuals 行为未发生回归。

## 成功标准

- Agent 仅查看原生工具 schema 即可识别核心数据访问与输出约束。
- Agent 可按 schema 指引渐进读取专用手册获取完整示例。
- 图表模式提示词不再重复承载工具调用契约。
- 现有图表生成、静态预览和工具注册测试继续通过。

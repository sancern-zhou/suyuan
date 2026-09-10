# 研判结果提交协议

分析完成后调用通用工具 `submit_task_review`。工具校验保存成功后才生成待人工确认或处置事项；最终回复仅用三至四句报告结论与提交结果，不输出用于系统解析的 JSON 代码块。

## 通用字段

- `subject_id` 与 `event_id`：均为当前智能事件的 `event_id`。重新研判和增量研判沿用同一业务编号。
- `category`：`智能事件`。
- `title`：站点名称 + 研判事件类型 + 数据影响。
- `summary`：三至四句纯文本结论，涵盖现象、核心事实、数据影响和人工核查事项。
- `decision`：需处置时 `needs_action`，证据不足需人工补证时 `needs_evidence`，需人工确认正常结论时 `approve`。
- `comment`：人工复核建议及需要核验的证据。
- `checks`：至少一个核验项。包含 `name`、`status`（`pass/fail/uncertain/not_applicable`）、非空 `basis`；可选 `scope`（`core/supporting/rebuttal`）和 `missing_evidence`。
- `review_basis`：本次判断依据。
- `actions`：处置建议数组。
- `evidence`：证据包或图表等文件，格式 `{"label":"证据说明","path":"已存在的数据目录文件路径"}`。
- `data_impact`：有明确污染物数据处置建议时填写。每项包含 `pollutant`、`decision`、`basis`；需要时间区间时提供含时区且开始不晚于结束的 `start/end`。剔除建议额外提供 `boundary_sources`、`reasonableness_status` 和 `reasonableness_basis`。尚不能确定区间时用 `needs_evidence`，不要捏造时间。

## 详情区块

`sections` 使用统一的 `title` 与 `fields`。字段格式为 `{"key":"稳定标识","label":"中文名称","value":"文字值"}`。事件页面从这些键读取展示内容，不解析最终回复。

“事件结论”区块必须填写：

| key | value |
| --- | --- |
| event_type | 当前 AI 事件类型字典中的值 |
| data_impact | 有数据影响、无数据影响或待确认 |
| suggested_level | P0、P1、P2、P3 或待确认 |
| compliance_explanation_result | 完全解释、部分解释、不能解释或无合规记录 |

有数据影响时，“数据分析”区块必须包含以下四个 key：
`station_series_analysis`、`regional_comparison_analysis`、`data_impact_assessment`、`logic_direction_check`。
每项填写实际分析，包括本站时序、区域背景、受影响污染物与时段，以及事件与数据变化方向是否一致。

主要与辅助证据标签可另建区块，沿用事件线索的展示文本，不能把线索名称直接当成最终事件类型。

## 增量与反馈

输入含 `continuity_context` 时，先读取上一轮结论与新增线索或现场反馈。输出覆盖全部已核验线索的新版完整结论，不丢弃历史事实。

新增线索场景在“连续性判断”区块中提供 `key="same_cause"`，`value` 为 `"true"` 或 `"false"`；说明同一原因延续或新原因的事实依据。不同原因的旧结论保留在审核版本历史中。反馈场景核验反馈对上一轮结论的补充和修正。

不输出连续性标记行，不声称已经归档、派单或恢复告警。只有通用工具返回 `success=true` 才能声称“已提交人工审核”。

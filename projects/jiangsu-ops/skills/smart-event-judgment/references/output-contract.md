# 研判结果提交协议

分析完成后调用通用工具 `submit_task_review`。工具校验保存成功后才生成待人工确认或处置事项；最终回复仅用两至三句报告结论与提交结果，不输出用于系统解析的 JSON 代码块。

输出口径与故障工单审核一致：用户首屏只读 `summary`，归档弹窗只读 `comment`，两者必须简洁；详细分析全部沉淀在 `checks`、`sections` 与 `actions`。但智能事件只研判事件类型、原因与数据影响，不输出剔除时间段建议。

## 通用字段

- `subject_id` 与 `event_id`：均为当前智能事件的 `event_id`。重新研判和增量研判沿用同一业务编号。
- `category`：`智能事件`。
- `title`：站点名称 + 研判事件类型 + 数据影响。
- `summary`：一句话纯文本结论，按"研判结论 + 数据影响 + 核心原因"组织，面向列表和详情首屏快速阅读；不复述证据过程，不罗列核验项。
- `decision`：需处置时 `needs_action`，证据不足需人工补证时 `needs_evidence`，需人工确认正常结论时 `approve`。
- `comment`：人工复核建议，面向人工快速研判，固定两段：第一段写明研判结果与处置意见（如"建议确认为疑似仪器故障，按 P1 处置并现场核查仪器""建议确认为外界环境影响，无数据影响，归档即可"）；第二段用一句话说明核心原因。现象复述、四段分析、核验过程、证据缺口与历史案例对照一律写入 `checks`、`sections` 与 `actions`，不得塞进 `summary` 或 `comment`。
- `checks`：至少一个核验项。包含 `name`、`status`（`pass/fail/uncertain/not_applicable`）、非空 `basis`；可选 `scope`（`core/supporting/rebuttal`）和 `missing_evidence`。
- `review_basis`：本次判断依据。
- `actions`：处置建议数组。
- `evidence`：证据包或图表等文件，格式 `{"label":"证据说明","path":"已存在的数据目录文件路径"}`。
- 不提交顶层 `data_impact` 数组，也不输出剔除时间段建议：剔除时段属工单审核职责，智能事件的数据影响结论只用 `sections.data_impact`（有数据影响、无数据影响、待确认）和"数据分析"区块表达。

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

“证据标签”区块必须提供 `primary_evidence_tags`（主要证据）和 `supporting_evidence_tags`（辅助证据）。沿用实际线索的展示文本，多项用顿号分隔；没有支持证据填“无”，不能编造标签或把线索名称直接当成最终事件类型。

## 增量与反馈

输入含 `continuity_context` 时，先读取上一轮结论与新增线索或现场反馈。输出覆盖全部已核验线索的新版完整结论，不丢弃历史事实。反馈触发的轮次以反馈确认的结论为基准重新选择事件类型并更新各字段，不得仅因证据缺口维持待定类型。

新增线索场景在“连续性判断”区块中提供 `key="same_cause"`，`value` 为 `"true"`、`"false"` 或 `"待确认"`；另填 `continuity_basis` 说明同因、不同原因或无法确认的依据。同站点同自然日仍为一个事件。不同原因的旧结论保留在审核版本历史中。反馈场景核验反馈对上一轮结论的补充和修正。

不输出连续性标记行，不声称已经归档、派单或恢复告警。只有通用工具返回 `success=true` 才能声称“已提交人工审核”。

提交失败时根据工具返回的字段错误修正后重提，不声称已生成待办。仅允许字典中的固定类型；具体仪器名称放在 `title` 和分析中。四段分析中证据不足的项应说明已核验事实和缺口，不能用“正常”代替缺失数据。

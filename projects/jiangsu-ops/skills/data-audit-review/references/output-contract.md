# 数据审核复核提交协议

分析完成后调用通用工具 `submit_task_review`。工具校验保存成功后才生成待人工确认事项；最终回复仅用三至四句报告结论与提交结果，不输出用于系统解析的 JSON 代码块。

## 通用字段

- `subject_id` 与 `event_id`：均为事件 payload 的 `subject_id`（`站点编码:审核日`）。增量复审沿用同一业务编号。
- `category`：`数据审核`。
- `title`：站点名称 + 审核日 + 复核结论概要。
- `summary`：给审核员看的业务结论，**50 字以内**，只说四件事：数据是否有效、有效的原因、无效的原因、无效时建议剔除的时间段（精确到小时区间，如“9月14日02—03时SO2无效，质控期间数据，建议剔除”）。禁止接口名、字段名、页签代码、schema、证据缺口等 IT 术语和过程性描述；技术细节写入 `checks` 和 `comment`，不得挤占 summary。
- `decision`：初审操作总体有证据支撑时 `approve`；存在应处理未处理或过度处理等实质问题时 `reject`；关键页签取证失败且无法依据其余证据判断时 `needs_evidence`。
- `comment`：人工复核建议，包含分歧数据点定位与需人工核查的事项；取证失败、记录截断等技术性说明也放在这里。
- `checks`：按页签/数据点填写核验项。每项包含 `name`、`status`（`pass/fail/uncertain/not_applicable`）、非空 `basis`；可选 `scope`（`core/supporting/rebuttal`）。
- `review_basis`：本次判断依据。
- `actions`：处置建议数组（如建议人工复核某时段某因子）。
- `evidence`：证据包文件，格式 `{"label":"证据说明","path":"事件 payload.evidence_pack_path"}`；可补充其他真实存在的数据目录文件。
- 顶层 `data_impact`（数组）：仅当对具体污染物数据处置有明确建议时填写。每项包含 `pollutant`、`decision`、`basis`；需要时间区间时提供含时区且开始不晚于结束的 `start/end`。剔除建议额外提供 `boundary_sources`、`reasonableness_status` 和 `reasonableness_basis`。不能确定区间时用 `needs_evidence`，不要捏造时间。

## 详情区块

`sections` 使用统一的 `title` 与 `fields`。字段格式为 `{"key":"稳定标识","label":"中文名称","value":"文字值"}`。

必填字段：

| key | value |
| --- | --- |
| station_code | 站点编码 |
| audit_day | 审核日（YYYY-MM-DD） |
| initial_review_summary | 初审结果页签摘要：记录数、初审操作分布、复核一致性 |
| anomaly_summary | 恒值/离群页签摘要：记录数、命中规则、是否应处理未处理 |

建议字段：

| key | value |
| --- | --- |
| station_name | 站点名称 |
| city_name | 城市名称 |
| tab_record_counts | 三页签记录数（初审/恒值/离群） |
| data_points_of_concern | 分歧或需人工关注的数据点（时间+因子+原因） |
| evidence_gaps | 页签取证失败或截断说明 |
| overall_conclusion | 整站整日整体结论 |

## 增量轮次

输入含 `continuity_context`（`reason=platform_audit_feedback`）时，先读取上一轮结论与平台人工日志摘要，逐项对照分歧后输出覆盖全部事实的新版完整结论；人工日志口径优先，除非有确凿矛盾证据并在 `comment` 中逐条列明。同一轮复审只提交一次，以工具返回结果判断是否创建待办。

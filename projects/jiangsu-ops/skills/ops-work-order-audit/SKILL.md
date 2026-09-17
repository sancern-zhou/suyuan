---
name: ops-work-order-audit
description: 例行工单审核、例行运维工单审核、巡检工单审核。审核江苏运维平台非故障例行工单（巡检/现场检查/校准/质控/质量保证/数据录入）并生成可追溯的问题清单与审核报告。用于指定时间、状态或工单范围的规则筛查、命中解释和报告生成；普通工单查询不使用本技能，故障工单审核请使用 fault-work-order-review。
---

# 江苏例行运维工单审核

## 适用范围

- 只审核**非故障**工单：巡检单 `Check`、现场检查单 `SECCheck`、校准单 `Calibration`、质控检查单 `QC`、质量保证单 `QA`、数据录入 `DataEntry`。
- 故障工单 (`Fault`) 不适用本技能，走 `fault-work-order-review`。
- 数据全部来自江苏运维平台真实接口，不回写平台、不修改工单状态。

## 工作流

### 1. 明确范围

- 与用户确认工单类型、创建时间范围、节点状态/工单状态、工单号或站点编码。
- 用户未给范围时，先取最近一批（`limit` 默认 50）并说明范围。
- 关键字映射：巡检/例行 → `Check`；现场检查 → `SECCheck`；校准 → `Calibration`；质控 → `QC`；质量保证 → `QA`；数据录入 → `DataEntry`。

### 2. 取数

调用 `jiangsu_ops_audit_fetch_dataset`，传入范围条件。工具会：

- 通过平台清单接口筛选工单，再按工单号逐个读取详单（含检查项、`rFCommon` 表单项、附件元数据、流程节点）；
- 用本地字段字典把 `stringN/bool_N/timeN/remarkN` 翻译成具名业务字段与行式检查行；
- 落盘数据集并返回 `dataset_path`、覆盖统计（工单/检查项/附件/未匹配字段字典数）。

取数后先检查覆盖统计；`unmapped_task_count` 不为 0 或 `detail_error_count` 不为 0 时，先说明审核覆盖不足的部分。

### 3. 执行审核

将上一步的 `dataset_path` 原值传给 `jiangsu_ops_audit_run_rules`（参数 `enable_semantic` 默认 true，对候选问题执行 LLM 语义复核；用户要求只跑规则时传 false，但此时 `report_ready=false`，不能生成正式报告）。工具执行确定性规则并生成：

- `issues_path`：问题清单（规则命中原始条目，含 `issue_id`）；
- `report_input_path`：报告输入——已按共享版口径把同一工单、同一检查项、同一异常字段的命中合并为一行，每行含 `rf_form_name`（检查项中文名）、`display_evidence`（面向用户的可核查事实）、`remark_context`（原始备注/说明及状态）、`rule_ids`、`source_issue_ids`、`severity`、语义复核结论；
- `data.summary.report_ready`：正式报告门禁。`false`（存在未复核候选）时**只交付待核验清单，不得生成正式报告**，并说明 `pending_semantic_reviews` 条数与原因。

当前规则：

| 规则 | 含义 |
| --- | --- |
| `FLOW_TIME_ORDER` | 流程节点完成时间早于开始时间 |
| `FLOW_FINISH_INCOMPLETE` | 工单已完成但存在未提交节点 |
| `TASK_ABNORMAL_NO_REMARK` | 行式检查项结论异常但未填写异常处理记录 |
| `TASK_VALUE_OUT_OF_RANGE` | 行式检查项实际值疑似超出参考范围（待人工复核） |
| `TASK_FIELD_MISSING` | 检查项已完成但时间字段为空（待人工复核） |
| `TASK_DEVICE_INCOMPLETE` | 检查项已完成但设备品牌/型号/编号不完整 |
| `FORM_UNMAPPED` | 该检查项表单未匹配字段字典，未纳入规则审核 |

**语义复核**对上述四类 `TASK_*` 候选逐条判定：`unresolved`（问题成立）、`not_applicable`（规则不适用，可能误报）、`valid_explanation`（异常已有合理解释）、`needs_verification`（证据不足）。被判 `not_applicable/valid_explanation` 的问题降级为"低"并在 `semantic_note` 记录理由；`unreviewed` 表示模型不可用或批次未覆盖，会使 `report_ready=false`。语义结果只是降级建议，**不删除问题**；`severity_counts` 反映降级后的报告行分布。

### 4. 组织结论

- 只依据本轮工具返回的问题清单与证据组织结论，不重新发明问题。
- 明确区分“接口事实”“规则命中”“待人工复核候选”。
- 规则命中是审核线索，不等于违规认定；涉及数值、责任或数据处置的结论必须标注待人工确认。

### 5. 生成报告

用户要求正式报告时：

1. 先检查 `data.summary.report_ready`。为 `false` 时**不生成正式报告**，只交付待核验清单（问题明细、未复核条数与原因），并说明补齐方式。
2. 为 `true` 时，完整读取 `report_input_path`。
3. 参考 [报告输出规范](projects/jiangsu-ops/skills/ops-work-order-audit/references/report-format.md) 组织报告正文——正文只有"审核范围"和"问题工单明细"两个章节，证据与语义结论写入明细行，不设统计/总结章节，不生成统计图表。
4. 调用 `create_report_package` 生成报告包，按交付要求用 `render_report_package` 渲染 HTML/Word，并用 `validate_report_package` 验收后 `publish_report`。

## 数据真实性

- 报告、表格和统计只能使用本轮接口返回的数据。
- 接口失败、详单缺失、字段未映射或字段为空时必须明确说明影响。
- 不创建、派发、修改或关闭工单；如需工单操作转对应流程并由人工确认。
- **交互式对话中不要调用 `submit_task_review`**：该工具依赖定时任务执行上下文（task_id/execution_id），聊天内调用必然失败。人工确认通过报告交付与对话回复完成；只有作为定时任务执行时才允许提交待办。
- 例行审核只使用本技能工具链取证，不要调用 `jiangsu_fetch_fault_work_orders` 等故障工单工具补证。

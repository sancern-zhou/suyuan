---
name: ops-work-order-audit
description: 审核运维工单并生成可追溯的最终问题清单或正式审核报告。用于指定时间或范围内工单的规则筛查、抽样复核、语义复核、命中解释、问题清单整理和审核报告生成；普通工单查询不使用本技能。
---

# 运维工单审核分析技能

## 概述

组合专用审核工具完成取数、规则与语义复核、证据解释和正式报告交付。工具负责批量判断，Agent 负责确认范围、消费最终清单和组织输出。

## 工作流

### 1. 明确范围

- 将时间字段与完成状态分开解释。`已完成`只对应 `order_statuses=["Finish"]`，不决定使用哪个时间字段。
- 用户说创建、发起或生成的工单时，使用 `create_time_start`、`create_time_end`；说完成、办结或结束的工单时，使用 `finish_time_start`、`finish_time_end`。
- 用户只说“某时间段已完成工单”且未说明时间字段时，先确认；必须自行假设时，明确说明假设。
- 仅在用户明确要求周期审核或周审核窗口时使用 `audit_window_preset="weekly_created"`。

### 2. 取数

调用 `ops_audit_fetch_dataset`。按用户要求传入状态、时间、站点、工单类型或维护类型；工具 schema 是参数定义的权威来源。

- 检查工单、流程、RF 表、附件和设备历史覆盖情况。关键数据覆盖异常时，先说明影响。
- 保存工具返回的 `data.dataset_path` 原值，不拼接、不猜测路径。
- 该步骤只取数，不形成审核结论。

### 3. 执行审核

将上一步的 `data.dataset_path` 原值传给 `ops_audit_run_rules`。

- 默认执行流量或读数图片视觉识别；用户要求关闭视觉识别或排查图片误判时传 `enable_visual=false`。
- 工具会执行确定性规则、适用的视觉比对和语义辅助复核，并生成 `final_issue_list_path` 等结果文件。
- `semantic_candidates` 是候选，`semantic_review_tasks` 是待执行任务，`semantic_review_results` 是语义辅助结果；三者都不是正式报告的问题清单。
- 只有本轮 `final_issue_list.items` 可以成为正式问题明细。若 `final_issue_list_path` 缺失或不可读，不得声称完整审核已完成。

### 4. 按需解释

仅在用户追问命中原因、需要抽样校准或结果文件不可读时调用 `ops_audit_inspect`：

- `mode="rules"`：查看规则目录。
- `mode="review_samples"`：查看校准样本。
- `mode="sample_rule"`：按规则抽样。
- `mode="order"`：查看单个工单证据。
- `mode="risk"`：按风险等级抽样。
- `mode="semantic_candidates"` 或 `mode="semantic_review_results"`：区分候选与已完成语义结果。

不要用 `ops_audit_inspect` 的抽样结果、旧报告、历史输出或 SQL 查询拼接正式问题清单。

### 5. 生成正式报告

用户要求正式报告、QMD 报告或报告包时：

1. 完整读取 [最终问题复核协议](backend/docs/skills/ops_work_order_audit/references/final-review.md)，复核本轮 `final_issue_list.items`。
2. 完整读取 [审核报告输出规范](backend/docs/skills/ops_work_order_audit/references/report-format.md)，严格按其中结构和字段约束组织报告。
3. 使用 `create_report_package` 生成报告包，再用 `validate_report_package` 验收；有渲染或资源错误时先修复。

报告阶段不得重新发现问题。除结果文件缺失或用户明确要求补查外，不再调用审核分析工具或 SQL。

## 审核边界

- 确定性规则处理字段存在性、枚举、公式、数值、流程和时间关系；语义层处理说明是否相关、充分且与证据一致。
- 规则目录、审核阶段和排除项以当前工具及配置返回为准，不在技能中复制易过时的规则清单。
- LLM 缺失、失败或低置信时，将相关项保留为待复核候选，不用关键词兜底生成最终问题。
- 具体结论必须来自工具结果、结果文件或用户提供的证据；数据缺失时明确说明缺口和影响。


---
name: ops-work-order-audit
description: 审核运维工单并生成可追溯的最终问题清单或正式审核报告，正式报告仅输出审核范围和问题工单明细。用于指定时间或范围内工单的规则筛查、抽样复核、语义复核、命中解释、问题清单整理和审核报告生成；普通工单查询不使用本技能。
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
- 默认执行流程、表单、数值、附件和跨工单等非视觉规则；用户明确要求仅做视觉审核时传 `enable_visual=true, enable_non_visual=false`。
- 工具会执行确定性规则、适用的视觉比对和语义复核，并直接生成 `final_issue_list_path`、`report_input_path` 和 `report_ready`。
- `semantic_candidates` 是候选，`semantic_review_tasks` 是任务记录，`semantic_review_results` 是语义复核证据；正式报告问题只使用本轮 `report_input.items`。
- `report_ready=false` 时，`pending_review_items` 或 `pending_semantic_reviews` 中仍有待核验项，不得生成正式报告；工具结果会同时返回 `human_feedback`，主助手将其转交右侧“待确认”面板。
- 面板要求用户逐项选择纳入或排除正式问题清单，并可填写审核意见；提交后调用 `/api/agent/{session_id}/human-feedback`，服务端以来源哈希校验并重建 `report_input`，随后续跑主助手。
- 人工反馈原文会进入续跑上下文；报告完成后，记忆整合 Agent 自主判断是否把经验写入对应模式的长期记忆和案例库，审核接口不硬编码导入任何案例。

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

正式报告正文仅包含“审核范围”和“问题工单明细”两个章节，不增加其他章节、附录或独立统计汇总；必要证据随对应问题明细展示。

1. 检查 `report_ready`；为 false 时先交付待核验清单，不生成正式报告。
2. 为 true 时只使用本轮 `report_input_path`；每个条目已合并同一异常的事实与说明，不得将 `components` 拆行。
3. `report_input.items[].display_evidence` 是所有规则统一的报告证据接口；问题描述只从该字段取值，不要解析或复制 `evidence_facts`。
4. 报告输入已经由后端完成筛选和分组。优先读取 `ops_audit_run_rules` 返回的 `report_context_path`；它是已注册的精简报告上下文。禁止调用 `execute_python`、`read_file`、`list_directory` 重建、筛选或复制报告输入，也不要创建 `report_input_filtered` 等中间文件。
5. 完整读取 [审核报告输出规范](backend/docs/skills/ops_work_order_audit/references/report-format.md)，严格按其中结构和字段约束组织报告。
4. 只调用一次 `create_report_package` 生成报告包、渲染 HTML/Word 并完成验收；有渲染或资源错误时修复后重新调用。

报告阶段不得重新发现问题。除结果文件缺失或用户明确要求补查外，不再调用审核分析工具或 SQL。

报告面向环境管理用户和运维管理人员：使用中文业务名称和可直接核对的表单值、附件值、范围或缺失项；不要假设读者了解数据库字段、规则 ID 或程序内部证据结构。遇到附件比对问题，参照报告规范中的推荐示例组织句子。

## 审核边界

- 确定性规则处理字段存在性、枚举、公式、数值、流程和时间关系；语义层处理说明是否相关、充分且与证据一致。
- 规则目录、审核阶段和排除项以当前工具及配置返回为准，不在技能中复制易过时的规则清单。
- LLM 缺失、失败或低置信时，将相关项保留为待复核候选，不用关键词兜底生成最终问题。
- 具体结论必须来自工具结果、结果文件或用户提供的证据；数据缺失时明确说明缺口和影响。

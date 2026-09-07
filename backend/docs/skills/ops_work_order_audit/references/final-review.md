# 最终问题复核协议

仅在生成正式报告前读取并执行本协议。目标是基于本轮 `review_input` 对全量问题逐条做出结构化复核决定并持久化；复核产物是报告问题明细的唯一数据来源；不得发现或新增问题。

## 调用要求

调用 `call_sub_agent(target_mode='ops')`，并提供：

- `goal`：按 `issue_id` 对本轮 `review_input.items` 全量条目逐一给出 retain/exclude/manual_review 决定，并调用 `ops_audit_submit_review` 持久化，返回工具结果中的产物路径。
- `context_str`：包含本轮 `ops_audit_run_rules` 返回的 `final_issue_list_path`、`review_input_path` 原值、下列判定标准、执行步骤和工具参数要求。不得构造固定路径。

## 判定标准

- `retain`：证据充分、问题成立，进入报告。
- `exclude`：仅在逐条证据满足以下任一条件时排除：
  1. 对“异常说明不足”项，备注与当前检查项相关且不与证据矛盾即可排除，不强制同时包含原因、措施、结果。异常已有处置说明不等于异常事实不存在。
  2. 命中来自已证实的规则配置缺陷，例如单位或品牌范围配置错误。
  3. 属于已证实的精度取舍或临界值口径问题。
  4. 属于已证实的工具或系统读取异常。
  5. 正常运维操作已有充分、具体且一致的说明。
- `manual_review`：证据不足以判断且影响结论时标记，等待人工处理；不得默认保留或默认排除。
- 厂家参数范围、单位口径或设备无此功能等说明质疑的是规则适用性；核验依据前不得确认违规。不能仅因发生V/mV换算就认定单位配置错误，须核对换算后单位和设备适用范围。
- 每条决定（包括retain）均须提供针对当前字段的具体reason。needs_manual_review项若要retain，还须在evidence_refs提供补充核验证据。
- 按issue_group_id检查关联：异常事实排除后，依赖它的“异常说明不足”同步排除；异常事实待核验时，关联说明问题不得独立保留。

## 子 Agent 执行步骤

将以下要求明确写入 `context_str`：

1. 用 `read_file` 完整读取 `review_input_path`，取得全量 `items` 与 `source.sha256`；`review_input.items` 已按 `issue_id` 对齐并精简，禁止改读其他文件替代。
2. 逐条阅读 `issue_id`、`working_order_code`、`rule_id`、`message` 和 `evidence_facts`。
3. 对照判定标准逐条决策；每个 `issue_id` 必须且只能出现一次，缺项视为复核未完成。
4. 调用 `ops_audit_submit_review`，参数使用本轮原值：`final_issue_list_path`、`expected_source_sha256`（取 `review_input.source.sha256`）、全量 `decisions` 和 `reviewer_name`。
5. 同一工单同一规则存在多条问题时逐项判断；排除一条不得连带排除另一条。

禁止不读文件直接提交、按 `rule_id` 批量排除、把 `needs_followup` 等状态当成排除理由、使用未引用具体证据的模板化理由，或修改原始 `final_issue_list`。

## 工具拒绝与重试

`ops_audit_submit_review` 在缺项、重复 `issue_id`、未知 `issue_id`、`reason` 缺失或源文件哈希不匹配时整体拒绝。收到失败时修正 `decisions` 后整份重提，不得部分提交或绕过工具手工写文件。

## 主 Agent 校验

1. 只消费 `ops_audit_submit_review` 返回的 `reviewed_issue_list_path` 与 `report_input_path`；禁止重新读取原始 `final_issue_list` 拼装问题明细。
2. `report_ready=false`（存在 manual_review 项或 pending_semantic_reviews）时不得生成正式报告。语义响应缺失或失败须补跑对应审核后重新提交复核，不能把未完成审核当作没有问题。
3. 抽查排除项 `reason` 是否引用具体证据；发现按规则批量排除、理由完全相同或模板化理由时，要求子 Agent 重新复核。
4. 报告明细和所有统计只使用 `report_input.items`。

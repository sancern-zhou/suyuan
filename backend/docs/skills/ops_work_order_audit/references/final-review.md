# 最终问题复核协议

仅在生成正式报告前读取并执行本协议。目标是逐条复核 `final_issue_list.items`，只排除有具体证据支持的误判；不得发现或新增问题。

## 调用要求

调用 `call_sub_agent(target_mode='ops')`，并提供：

- `goal`：复核 `final_issue_list` 全量问题，逐条判断是否排除，只返回 `excluded_items`。
- `context_str`：包含本轮 `ops_audit_run_rules` 返回的 `final_issue_list_path` 原值、下列排除标准、执行步骤和输出格式。不得构造固定路径。

## 排除标准

仅在逐条证据满足以下任一条件时排除：

1. 备注已经具体说明当前异常的原因、措施和结果，且与其他证据一致。
2. 命中来自已证实的规则配置缺陷，例如单位或品牌范围配置错误。
3. 属于已证实的精度取舍或临界值口径问题。
4. 属于已证实的工具或系统读取异常。
5. 正常运维操作已有充分、具体且一致的说明。

## 子 Agent 执行步骤

将以下要求明确写入 `context_str`：

1. 先用 `read_file` 完整读取 `final_issue_list_path`，取得全量 `items`。
2. 逐条阅读 `working_order_code`、`rule_id`、`category`、`message` 和 `evidence`。
3. 对照排除标准逐条判断，只返回应排除的条目；其余默认保留。
4. 同一工单同一规则存在多条问题时，逐项判断并为每个被排除项单独输出一条记录。

禁止不读文件直接返回、按 `rule_id` 批量排除、把 `needs_followup` 等状态当成排除理由，或使用未引用具体证据的模板化理由。

## 子 Agent 输出格式

只返回 JSON 数组 `excluded_items`。每项必须包含：

```json
{
  "working_order_code": "工单号",
  "rule_id": "规则ID",
  "exclude_reason": "引用本条具体 message 或 evidence 的排除理由"
}
```

不得返回保留条目，不得改变字段名。

## 主 Agent 校验

1. 检查是否存在同一规则批量排除、理由完全相同或未引用具体证据的情况。
2. 拒绝以语义复核状态、笼统标签或工具未执行作为排除理由。
3. 对可疑排除项自行读取原条目复核，或要求子 Agent 重新复核。
4. 按 `working_order_code` 与 `rule_id` 匹配；存在重复键时，结合 `exclude_reason` 引用的具体证据逐项匹配，不扩大排除范围。
5. 得到 `retained_items = final_issue_list.items - validated_excluded_items`。报告明细和所有统计只使用 `retained_items`。


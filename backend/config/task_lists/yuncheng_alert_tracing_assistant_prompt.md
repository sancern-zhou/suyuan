# 运城市告警溯源报告生成任务

你正在助手模式中执行运城市第三方驻场团队试用场景。不要切换或创建新的 Agent 模式。

## 场景流程和职责边界

- 社交模式定时任务从运城证据根目录中定位最近证据目录，并读取其中的告警 JSON。
- 社交模式调用助手模式执行溯源分析技能。
- 助手模式调用 expert 模式子 Agent 完成气象分析和常规分析草稿。
- 助手模式在同一证据目录生成报告、Word 文件和微信摘要。
- 助手模式不直接推送微信；社交模式收到回复后推送报告给微信用户。

## 输入

- alert_json_path: `{alert_json_path}`
- tracing_context_manifest_path: `{tracing_context_manifest_path}`
- report_dir: `{report_dir}`（证据目录；报告、Word 和专家草稿均写入此目录）
- evidence_dir: `{report_dir}`
- weather_draft_path: `{report_dir}/weather_analysis_draft.md`
- routine_draft_path: `{report_dir}/routine_analysis_draft.md`
- report_qmd_path: `{report_dir}/report.qmd`
- report_docx_path: `{report_dir}/report.docx`
- skill_file: `backend/docs/skills/yuncheng_alert_tracing_skill.md`
- weather_expert_skill_file: `backend/docs/skills/weather_analysis_expert.md`
- routine_expert_skill_file: `backend/docs/skills/routine_monitoring_analysis_expert.md`

## 执行要求

1. 阅读 skill 文件。
2. 校验 `{report_dir}`、`{alert_json_path}`、`{tracing_context_manifest_path}` 均存在，且 `report_dir` 就是证据目录。
3. 阅读告警 JSON：`{alert_json_path}`。只做输入一致性校验，不重新判断告警是否成立；若不是 `has_alert=true` 且 `status=pending_trace`，返回失败 JSON。
4. 阅读 tracing_context_manifest.json 和其中列出的资产。
5. 使用同步 `call_sub_agent(target_mode="expert")` 调用 expert 模式子 Agent 作为气象分析专家，要求其先阅读 `weather_expert_skill_file`，生成 `{report_dir}/weather_analysis_draft.md`，并仅返回包含 `expert_type` 和 `draft_path` 的 JSON。禁止使用 `spawn`、`wait_task` 或后台任务方式。
6. 使用同步 `call_sub_agent(target_mode="expert")` 调用 expert 模式子 Agent 作为常规分析专家，要求其先阅读 `routine_expert_skill_file`，生成 `{report_dir}/routine_analysis_draft.md`，并仅返回包含 `expert_type` 和 `draft_path` 的 JSON。禁止使用 `spawn`、`wait_task` 或后台任务方式。
7. 读取两个专家草稿，审核是否存在越界结论、AQI 口径错误、缺失资产未说明、驻场建议不可执行等问题。
8. 将告警 JSON 的 `rule_hits` 作为告警触发依据，将 `supporting_rule_hits` 作为辅助证据写入监测事实和初步溯源研判。
9. 按 skill 的报告结构整合生成 `{report_dir}/report.qmd`。
10. 使用标准报告包能力导出 `{report_dir}/report.docx`：读取 `backend/app/tools/report/report_package/references/index.md`，调用 `create_report_package` 保存报告包，调用 `render_report_package(format="docx")` 导出 Word，并用 `validate_report_package(require_docx=true)` 验收。
11. 验收 `{report_dir}/report.docx` 必须存在；不存在时返回失败 JSON，不允许返回成功。
12. 生成微信摘要，摘要必须短于 500 字。
13. 返回报告路径、Word 路径和微信摘要给社交模式，由社交模式负责微信推送。

## 返回格式

成功时仅返回：

```json
{
  "success": true,
  "evidence_dir": "{report_dir}",
  "alert_json_path": "{alert_json_path}",
  "tracing_context_manifest_path": "{tracing_context_manifest_path}",
  "report_qmd_path": "{report_dir}/report.qmd",
  "report_docx_path": "{report_dir}/report.docx",
  "wechat_summary": "500字以内微信摘要"
}
```

失败时仅返回：

```json
{
  "success": false,
  "evidence_dir": "{report_dir}",
  "error": "失败原因"
}
```

## 结论边界

- 区分监测事实、气象提示、溯源推断、需本地数据核实。
- 没有本地污染源、门禁、卡口、移动源轨迹、执法巡查数据时，不得确认具体污染源。
- 第一版未接入站点小时数据，不得输出站点质控结论。
- 缺失的图像或数据必须写入“数据缺口与不确定性”。
- 报告产物必须写回同一证据目录，便于后续 Agent 回顾检索。

# 运城市告警溯源报告生成任务

你正在助手模式中执行运城市第三方驻场团队试用场景。不要切换或创建新的 Agent 模式。

## 场景流程和职责边界

- 社交模式定时任务启动运城小时盯守并发现告警时间。
- 社交模式调用助手模式执行溯源分析技能。
- 助手模式调用 expert 模式子 Agent 完成气象分析和常规分析草稿。
- 助手模式生成报告、Word 文件和微信摘要。
- 助手模式不直接推送微信；社交模式收到回复后推送报告给微信用户。

## 输入

- latest_alert_path: `{latest_alert_path}`
- tracing_context_manifest_path: `{tracing_context_manifest_path}`
- report_dir: `{report_dir}`
- skill_file: `backend/docs/skills/yuncheng_alert_tracing_skill.md`
- weather_expert_skill_file: `backend/docs/skills/weather_analysis_expert.md`
- routine_expert_skill_file: `backend/docs/skills/routine_monitoring_analysis_expert.md`

## 执行要求

1. 阅读 skill 文件。
2. 阅读 latest_alert.json。
3. 阅读 tracing_context_manifest.json 和其中列出的资产。
4. 调用 expert 模式子 Agent 作为气象分析专家，要求其先阅读 `weather_expert_skill_file`，生成 `{report_dir}/weather_analysis_draft.md`，并仅返回包含 `expert_type` 和 `draft_path` 的 JSON。
5. 调用 expert 模式子 Agent 作为常规分析专家，要求其先阅读 `routine_expert_skill_file`，生成 `{report_dir}/routine_analysis_draft.md`，并仅返回包含 `expert_type` 和 `draft_path` 的 JSON。
6. 读取两个专家草稿，审核是否存在越界结论、AQI 口径错误、缺失资产未说明、驻场建议不可执行等问题。
7. 将 `rule_hits` 作为告警触发依据，将 `supporting_rule_hits` 作为辅助证据写入监测事实和初步溯源研判。
8. 按 skill 的报告结构整合生成 `{report_dir}/report.qmd`。
9. 使用现有 Quarto 报告渲染能力导出 `{report_dir}/report.docx`。
10. 生成微信摘要，摘要必须短于 500 字。
11. 返回报告路径、Word 路径和微信摘要给社交模式，由社交模式负责微信推送。

## 结论边界

- 区分监测事实、气象提示、溯源推断、需本地数据核实。
- 没有本地污染源、门禁、卡口、移动源轨迹、执法巡查数据时，不得确认具体污染源。
- 第一版未接入站点小时数据，不得输出站点质控结论。
- 缺失的图像或数据必须写入“数据缺口与不确定性”。

---
name: smart-event-judgment
description: Analyze Jiangsu smart-event clue bundles and evidence packages, define the final event type and name after evidence review, assess data impact and level, and produce a human-confirmable judgment. Use for the unified Jiangsu smart-event AI task; do not use for direct station-fault diagnosis or work-order review.
---

# 江苏智能事件研判

读取可信任务上下文中的 `payload.evidence_package_path`（或 `evidence_package_path`），用 `read_file` 查看完整证据包，核对事件编号与站点。告警是线索，不是最终事件类型或根因。

- 按 [证据契约](projects/jiangsu-ops/skills/smart-event-judgment/references/evidence-contract.md) 解释窗口、来源状态与缺口。线索含义不清时查 [线索分类](projects/jiangsu-ops/skills/smart-event-judgment/references/event-clue-taxonomy.md)。
- 按 [研判规则](projects/jiangsu-ops/skills/smart-event-judgment/references/judgment-rules.md) 核验数据影响、等级、合规解释与增量连续性；按 [类型字典](projects/jiangsu-ops/skills/smart-event-judgment/references/event-type-dictionary.md) 选择类型。
- 按 [提交协议](projects/jiangsu-ops/skills/smart-event-judgment/references/output-contract.md) 调用 `submit_task_review`。所有结论均须提交，包括 P3 和待确认；工具成功保存后才生成待办并供系统回填。最终回复仅报告结论与提交状态。

系统初判不是 AI 结论，队列优先级不是事件等级。取数失败、空结果或超限不能直接证明数据异常；视频标签由专业算法识别，直接采信为行为事实，不做重新识别；缺失视频不得描述画面。历史案例与记忆只用于提出待核验假设。需要补证时可调用已配置的江苏只读工具，记录仍未解决的缺口。

事件始终按同站点、同自然日归并，不同原因分项解释，保留全部已核验事实。不得自动关闭告警、派单、归档、修改监测数据或执行设备控制。

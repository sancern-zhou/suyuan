---
name: smart-event-judgment
description: Analyze Jiangsu smart-event clue bundles and evidence packages, define the final event type and name after evidence review, assess data impact and level, and produce a human-confirmable judgment. Use for the unified Jiangsu smart-event AI task; do not use for direct station-fault diagnosis or work-order review.
---

# 江苏智能事件研判

读取可信任务上下文中的 `payload.evidence_package_path`（或 `evidence_package_path`），它指向证据包 `index.json`；先用 `read_file` 读 index，核对事件编号与站点，并据其 `sources.<name>`（status/summary/record_count/metadata）判断需要哪些来源明细，再按需 `read_file` 同目录 `sources/<name>.json` 的 `data` 字段，不要一次性读取全部来源。告警是线索，不是最终事件类型或根因。

证据可得性采用“先取证、再判断”原则：对当前类型相关的来源，先调用已配置的江苏只读接口尝试获取；根据来源的 `success`、`status`、`record_count` 和实际 `data` 区分成功、空结果、失败和未接入。失败、未接入、不可用或确实为空的来源从本次必需证据集合中移除，只记录为非阻断性缺口；不得把缺失来源当作反证，也不得仅因为缺少一个来源就选择“数据异常待研判”。在其余可用证据已经支持某一类型、且没有可用反证时，应完成该类型判断，并在结论中说明未获取来源及其置信度影响。

- 按 [证据契约](projects/jiangsu-ops/skills/smart-event-judgment/references/evidence-contract.md) 解释窗口、来源状态与缺口，先尝试接口取数再判定哪些证据可用。线索含义不清时查 [线索分类](projects/jiangsu-ops/skills/smart-event-judgment/references/event-clue-taxonomy.md)。
- 按 [研判规则](projects/jiangsu-ops/skills/smart-event-judgment/references/judgment-rules.md) 核验数据影响、等级、合规解释与增量连续性；按 [类型字典](projects/jiangsu-ops/skills/smart-event-judgment/references/event-type-dictionary.md) 选择类型。没有视频识别结果或图片时跳过视频证据，不把视频缺失作为阻断条件；只要其他证据满足类型条件，仍应完成定类。
- 按 [提交协议](projects/jiangsu-ops/skills/smart-event-judgment/references/output-contract.md) 调用 `submit_task_review`。所有结论均须提交，包括 P3 和待确认；工具成功保存后才生成待办并供系统回填。最终回复仅报告结论与提交状态。

系统初判不是 AI 结论，队列优先级不是事件等级。取数失败、空结果或超限不能直接证明数据异常；视频标签由专业算法识别，直接采信为行为事实，不做重新识别。没有视频结果或图片时只记录为非阻断性证据缺口，不得描述或推断画面，也不得把视频缺失当作相关行为未发生。历史案例与记忆只用于提出待核验假设。需要补证时可调用已配置的江苏只读工具，记录仍未解决的缺口。

事件始终按同站点、同自然日归并，不同原因分项解释，保留全部已核验事实。不得自动关闭告警、派单、归档、修改监测数据或执行设备控制。

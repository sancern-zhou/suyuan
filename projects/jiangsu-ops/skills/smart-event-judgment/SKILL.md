---
name: smart-event-judgment
description: Analyze Jiangsu smart-event clue bundles and evidence packages, define the final event type and name after evidence review, assess data impact and level, and produce a human-confirmable judgment. Use for the unified Jiangsu smart-event AI task; do not use for direct station-fault diagnosis or work-order review.
---

# 江苏智能事件研判

本技能处理“告警线索已经生成、最终事件类型尚未确定”的事件。系统生成的供电、数采网络、站房环境、仪器、异常数据、断数、超限、视频和合规内容都是线索，不能直接当作最终事件类型或根因。最终事件类型、正式名称、数据影响和建议等级必须由本次证据分析得出，并交由人工确认。

## 输入和取证

1. 先从可信事件上下文读取 `payload.evidence_package_path`；如果只有 `evidence_package_path`，使用该字段。用 `read_file` 读取完整证据包，不依据被截断的内联 payload 下结论。
2. 核对 `event_id`、站点编码、事件时间、`primary_clue_tag`、`clue_tags` 和证据包的 `event_context`。`clue_tags` 必须完整保留，不能只分析主线索。
3. 阅读 `projects/jiangsu-ops/skills/smart-event-judgment/references/event-clue-taxonomy.md` 判断线索含义，再按 `projects/jiangsu-ops/skills/smart-event-judgment/references/evidence-contract.md` 解释 `sources`、状态、时间窗口和数据缺口。
4. 只能从 `projects/jiangsu-ops/skills/smart-event-judgment/references/event-type-dictionary.md` 选择最终事件类型，再根据 `projects/jiangsu-ops/skills/smart-event-judgment/references/judgment-rules.md` 核验支持证据。证据缺失时可以调用已配置的江苏只读工具补查最小时间窗口，但不能把空结果解释为“没有异常”。
5. 同时检查监测、仪器状态、站房报警、数采报警、动环、质控、工单、气象、片区对比和合规记录；视频接口当前未接入时明确记录缺口，不描述未看到的画面。

## 研判边界

- 区分“事实、推断、待核实”；规则命中是研判入口，不是根因结论。
- 合规记录只能作为线索和证据，不能自动把事件定为“合规运维核查”。
- 供电、网络、环境和仪器线索不能直接替代最终事件类型；要结合数据影响、持续时间、关联设备和其他来源证据。
- 只有证据支持时才判断“有数据影响”或给出 P0–P3；否则使用“待确认”。
- 历史案例和任务长期记忆只用于提出待核验假设，不能替代本次证据。
- 不关闭告警、不修改监测数据、不执行设备控制、不直接归档事件或声称已经派单。

## 输出

按 `projects/jiangsu-ops/skills/smart-event-judgment/references/output-contract.md` 调用 `submit_task_review` 提交结构化结果。最终回复仅简述结论和提交状态；不得输出“已修复”“已派单”等未经证据确认的状态。

任务完成后由系统把结果回写事件和证据包。人工确认仍是最终事件类型、等级和归档状态的最终依据。

## 提交与待办

完成分析后必须按 [提交协议](projects/jiangsu-ops/skills/smart-event-judgment/references/output-contract.md) 调用 `submit_task_review`。不再输出或依赖最终回复末尾的 JSON 回填块。工具成功保存的结构化记录是研判结果与待办的唯一来源。

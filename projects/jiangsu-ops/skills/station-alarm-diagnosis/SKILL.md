---
name: station-alarm-diagnosis
description: Analyze Jiangsu air-monitoring station platform alarms, device alarms, monitoring-data anomalies, quality-control faults, communication faults, and environment/power faults from an event evidence package. Use when a station fault event needs evidence-based diagnosis, remediation steps, verification criteria, and a review-ready work-order draft.
---

# 江苏站点告警诊断

## 概述

基于自动采集的事件证据包，对江苏空气监测站告警和数据异常进行分型诊断，并生成可供人工审核派单的处置方案。

## 工作流

1. 从可信事件上下文取得 `payload.evidence_pack_path`，先用 `read_file` 完整读取证据包。再读取 [证据契约](projects/jiangsu-ops/skills/station-alarm-diagnosis/references/evidence-contract.md) 校验事件、站点、时间和采集状态；路径缺失或无法读取时停止下结论，报告输入不完整。
2. 根据 `trigger.alarm_type`、`trigger.summary`、`trigger.source_type` 和异常 `findings` 判定告警族。用 `read_file` 读取 [分类型诊断手册](projects/jiangsu-ops/skills/station-alarm-diagnosis/references/alarm-playbooks.md) 中对应章节；告警跨多个类型时可读取多个章节。
3. 建立时间线，至少串联触发记录、小时监测值、站房告警、自动巡检和历史工单。时间、站点或设备标识无法对齐的数据只能列为旁证。
4. 先验证直接证据，再提出原因假设。仅在证据包不足时调用当前模式的只读工具补查；查询必须限定事件站点和最小必要时间窗。
5. 给出按置信度排序的原因。每个原因都列出支持证据、冲突证据、置信度和进一步确认动作。不得把相关性写成已证实因果。
6. 形成处置方案与工单草案。当前流程只生成待审核内容，不调用设备控制、不关闭告警、不声称已经派单。

## 取证规则

- 优先使用同站点、同设备、同污染物、同时间窗的证据。
- 区分三种表述：`已证实`、`推断`、`待核实`。
- 某补充接口返回 `success=false` 时，明确记录数据缺口，不把“未查到”解释为“没有异常”。
- 监测突变、恒值或断数是症状，不自动等同于仪器故障；同时排查质控、采样、通信、供电和环境因素。
- 历史工单只能提高相似原因的优先级，不能独立证明本次根因。
- 安全、供电、气路泄漏、设备高温等风险优先给出现场隔离和人工确认措施。

## 输出格式

按以下结构返回：

1. `事件摘要`：事件 ID、站点、时间、告警族、严重程度、当前状态。
2. `证据时间线`：按时间排序并注明证据文件或工具来源。
3. `诊断结论`：原因排序、置信度、支持/冲突证据、待核实项。
4. `处置方案`：立即动作、现场检查、修复动作、恢复验证和升级条件。
5. `工单草案`：标题、站点、故障类别、优先级、故障描述、证据摘要、建议人员/专业、处理步骤、验证标准、建议时限、附件路径。
6. `审核建议`：明确写出“待人工审核后派单”，列出审核者必须确认的风险和缺失信息。

不要输出已派单、已修复或已恢复，除非证据中存在对应的明确状态记录。

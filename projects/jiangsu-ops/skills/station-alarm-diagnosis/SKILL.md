---
name: station-alarm-diagnosis
description: Analyze Jiangsu air-monitoring station platform alarms, device alarms, monitoring-data anomalies, quality-control faults, communication faults, and environment/power faults from an event evidence package. Use when a station fault event needs evidence-based diagnosis, remediation steps, verification criteria, and a review-ready work-order draft.
---

# 江苏站点告警诊断

## 概述

基于自动采集的事件证据包，对江苏空气监测站告警和数据异常进行分型诊断，并生成可供人工审核派单的处置方案。

## 工作流

1. 从可信事件上下文取得 `payload.evidence_pack_path`，先用 `read_file` 完整读取证据包。再读取 [证据契约](projects/jiangsu-ops/skills/station-alarm-diagnosis/references/evidence-contract.md) 校验事件、站点、时间和采集状态；路径缺失或无法读取时停止下结论，报告输入不完整。
2. 根据 `trigger.alarm_type`、`trigger.summary`、`trigger.source_type` 和异常 `findings` 判定告警族。只读取 [分类型诊断手册](projects/jiangsu-ops/skills/station-alarm-diagnosis/references/alarm-playbooks.md) 中对应章节；告警跨多个类型时最多读取两个章节，不重复复述手册内容。
3. 建立时间线，至少串联触发记录、小时监测值、站房告警、自动巡检和历史工单。时间、站点或设备标识无法对齐的数据只能列为旁证。
4. 图谱只作辅助线索：证据不足且可能改变排查方向时，最多调用一次 `knowledge_graph_query`，使用系统注入的知识库 ID、`depth=1`、`top_k<=5`。图谱结果必须回到事件证据、告警/监测/巡检/质控接口核验；无结果、超时或不可用时立即跳过，不得在图谱检索上投入多轮迭代。
5. 先验证直接证据，再提出原因假设。仅在证据包存在明确缺口且补查能改变判断时调用只读工具；查询必须限定事件站点和最小必要时间窗，同一事实不得重复查询或重复引用。
6. 只保留最多三个有证据支撑的候选原因；没有支持证据的常规可能性合并为“待现场排除项”，不得逐项罗列。
7. 调用 `submit_task_review` 提交待人工处置事项。`subject_id` 与 `event_id` 填事件 ID，`category` 填“故障诊断”，`title/summary/comment` 填标题、结论及人工核查意见，`decision` 填 `needs_action` 或 `needs_evidence`。`checks` 至少包含一项有名称、状态和依据的证据核验；`actions` 列处置建议；`sections` 用标题与 label/value 字段展示故障事实、候选原因、设备信息、验证标准与时限；`evidence` 引用实际证据包文件。提交成功后等待人工处理，不自动派单、反控或关闭告警。

## 取证规则

- 优先使用同站点、同设备、同污染物、同时间窗的证据。
- 区分三种表述：`已证实`、`推断`、`待核实`。
- 某补充接口返回 `success=false` 时，明确记录数据缺口，不把“未查到”解释为“没有异常”。
- 监测突变、恒值或断数是症状，不自动等同于仪器故障；同时排查质控、采样、通信、供电和环境因素。
- 历史工单只能提高相似原因的优先级，不能独立证明本次根因。
- 安全、供电、气路泄漏、设备高温等风险优先给出现场隔离和人工确认措施。
- 对浓度偏高、偏低、恒值或站点趋势与城市不一致事件，必须用一行说明小时气象对“真实局地污染/扩散条件变化”的支持、反证或数据缺口；不要逐小时抄录气象序列。
- 证据状态只引用一次；长列表、原始记录和重复字段留在证据包路径，不复制到结论正文。

通用工具的详情区块必须包含 `key="fault_facts"`（已核验的故障事实）与 `key="verification_standard"`（人工处置后的验证标准），对应任务配置中的必填字段。校验失败时修正后重新提交。

## 输出格式

按以下紧凑结构返回，目标控制在 1500–2500 个中文字符，确有多告警交叉影响时最多 3000 个字符；不填空章节，不重复同一事实：

1. `一句话结论`：症状、当前判断、置信边界和是否建议派单。
2. `关键证据`：最多 5 条，按“时间｜来源｜事实”写；只保留改变判断的证据。相关事件补充一行 `气象判断`。
3. `候选原因`：最多 3 条，每条一行，格式为“原因｜置信度｜支持证据｜缺口/确认动作”。
4. `处置与验证`：立即/现场动作合并列出最多 5 条，验证标准最多 3 条。
5. `待办事项`：报告通用工具提交结果与待人工处置状态，不重复提交。
6. `审核建议`：明确写出“待人工确认与处置”，只列审核者必须确认的风险或缺失信息，最多 3 条。

不要输出已派单、已修复或已恢复，除非证据中存在对应的明确状态记录；也不要声称已经创建工单。

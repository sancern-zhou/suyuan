---
name: fault-work-order-review
description: 审核江苏省中心故障工单事件。用于从审核事件证据包读取工单详单、质控、5 分钟宽表监测、小时数据、动环、告警、同城确定性摘要、传输缺失和附件线索，按证据包 sop_id 渐近读取对应 SOP 手册，生成可人工确认归档的结构化审核结论。
---

# 江苏故障工单审核

## 触发场景

本技能用于处理 `jiangsu.fault_work_order.review_requested` 事件。事件 payload 必须提供 `evidence_pack_path`，证据包内必须包含 `sop_id`、`work_order_code`、`evidence_time_window` 和已抓取的证据组。

## 渐近读取流程

1. 先用 `read_file` 完整读取事件 `payload.evidence_pack_path`。无法读取证据包时停止审核，不得猜测结论。
2. 读取 [输出契约](projects/jiangsu-ops/skills/fault-work-order-review/references/output-contract.md)，明确提交字段、核验项字段、数据处置和剔除区间要求。
   - 读取 [记忆维护规范](projects/jiangsu-ops/skills/fault-work-order-review/references/memory-maintenance.md)，区分固定 SOP 与任务长期记忆/案例库内容；长期记忆只作为参考，不替代本次证据。
3. 从证据包读取 `sop_id`：
   - `SOP-01`：读取 [SOP-01 质控/校准/仪器测量链异常](projects/jiangsu-ops/skills/fault-work-order-review/references/sop-01-qc.md)。
   - `SOP-02`：读取 [SOP-02 监测数据与采样、供电、站房环境异常](projects/jiangsu-ops/skills/fault-work-order-review/references/sop-02-env.md)。
   - `SOP-03`：读取 [SOP-03 数据传输、平台离线与数据缺失](projects/jiangsu-ops/skills/fault-work-order-review/references/sop-03-transmission.md)。
   - 缺少 `sop_id` 或不属于已支持 SOP 时，停止提交并说明路由缺失，不得套用相近 SOP。
4. 只读取本次 `sop_id` 对应的 SOP 手册。证据冲突或跨类时，可读取另一个 SOP 手册用于边界判断，但必须说明触发原因。
5. 基于证据包形成工单审核结论和数据处置结论。各 SOP 先核验事实一致性，再进行数据影响逻辑判断；SOP-01 使用 M1–M6，SOP-02 使用 E1–E8，SOP-03 使用 T1–T7，不设置流程类核验项。处置、恢复、补传和时间戳相关附件或回执并入对应事实核验项。执行细则见对应手册。运维提交的详细工单、处置说明、附件照片、平台截图、补传回执和影响边界是核心材料，系统主动抓取的监测、质控、告警、动环、同城对比和传输辅助数据用于核验一致性。辅助证据缺失只说明“辅助核验未覆盖”，不得机械把结论降成 `needs_evidence`。
6. 判断时遵循证据闭环优先：附件、截图、监测/审核标识、处置记录和边界可以相互补足时，应直接给出审核结论；不要为了寻找工单文字里的非实质性瑕疵而退回。只有冲突会影响异常事实、对象、数据分类、处置对应性、恢复状态或剔除边界，且无法由其他核心证据补足时，才使用 `needs_evidence`。
7. 调用 `jiangsu_submit_fault_work_order_review` 提交结构化结论并生成右侧人工确认归档卡片。所有 SOP 分支都使用这一个提交工具。

审核完成后，任务级历史学习可将本次审核沉淀为案例，并从多次案例中更新长期记忆。不要把单次案例、临时边界或未经人工确认的推断回写到 SOP 手册。

## 总体约束

- 审核对象仅为小时数据：`data_impact` 与剔除区间的 `granularity` 固定为 `hour`。5分钟数据仅用于定位异常、核验处置和恢复，不输出分钟级有效性或剔除建议；小时有效性及起止须结合小时记录和有效性规则独立判断，不把分钟异常简单向整小时取整。

- 证据包是事实边界；补查只在能够改变结论时进行，且必须限定同站点、同设备、同污染物和最小必要时间窗。
- 工单文字、`已处理`、`已恢复正常`、`申请剔除 X 至 Y`、`未受影响` 只能作为待核验声明，不能替代附件照片、平台截图、补传回执或其他运维核心材料。
- 不把工单措辞不严谨自动等同于核心证据不足。若可核验附件、平台截图、监测/审核标识和边界已经形成闭环，文字瑕疵写入备注或人工关注即可；不得单独作为退回补材料理由。
- 取证窗口只用于抓取数据，不能自动作为异常或剔除边界。
- 当证据包 `input_profile` 为 `agent_slim_v1` 时，优先阅读主包中的确定性摘要、核验项锚点和 `raw_resources` 索引；不要在首轮审核中读取同城全量原始资源，除非摘要显示缺失、冲突或需要复核边界来源。
- 5 分钟监测证据按宽表整行抓取，不按 `pollutantCodes` 过滤；PM2.5/PM10 读取 `pM2_5`/`pM10` 字段，审核 5 分钟为空不代表原始 5 分钟不可查。
- 不使用兜底逻辑掩盖运维核心材料缺字段、接口失败或边界不明；问题要显式暴露为 `needs_evidence` 或审核意见中的退回补材料原因。
- 核验项按核心闭环判断：工单、站点、污染物、异常事实、处置、恢复、传输/补传状态、附件/截图/回执和边界属于核心；系统主动抓取的同城对比、监测、质控、告警、动环等证据属于辅助核验，缺失时要说明，但不要默认阻断结论；若辅助核验发现核心材料矛盾，可作为退回依据。
- 当前阶段禁止自动回写江苏平台工单状态，禁止自动剔除、修改或重算监测数据。

## 输出基准

最终提交前必须确认：

- `work_order_decision` 只表达工单是否建议通过、退回或补充证据。
- `data_impact` 单独表达站点、设备、污染物、粒度、时间段和数据处置建议。
- `review_summary` 必须是一句话用户摘要，优先写成“结论 + 数据处置 + 核心原因”，不要罗列核验项编号和长证据清单；详细依据放入 `review_comment`、`gates` 和 `evidence_refs`。
- 涉及 `partial_exclude` 或 `exclude` 时，必须在对应 `data_impact` 中写明污染物、粒度、明确 start/end；每个剔除类 `data_impact` 都必须有 `exclusion_intervals` 条目通过 `data_impact_index` 引用，并提供边界来源和合理性判断；不需要提交 `exclusion_required`，系统按 data_impact 自动判定。
- 无测量、平台缺失或暂时不可见不等于可剔除，应优先判断 `missing_no_delete` 或 `needs_evidence`。
- SOP-03 必须区分设备未测量、本地已测量未上传、平台暂时不可见、补传成功和时间戳/重复记录异常；不能把“离线”“无数据上传”直接写成剔除候选。

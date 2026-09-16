---
name: data-audit-review
description: 复核江苏省审核平台已完成初审的站点-审核日数据准确性。从平台证据包读取初审结果、恒值、离群值三页签审核记录及其监测、仪器、设备、质控、工单、门禁、动环、气象证据链，判断平台初审操作是否有证据支撑，生成可人工确认的 AI 审核结论；平台人工审核日志回流后按人工口径增量修正。
---

# 江苏数据审核 AI 复核

## 触发场景

本技能用于处理 `jiangsu.data_audit.review_requested` 事件。事件对应一个平台站点-审核日（`subject_id` 形如 `3001A:2026-09-14`），事件 payload 必须提供 `evidence_pack_path` 与 `subject_id`。

## 审核流程

1. 先用 `read_file` 完整读取事件 `payload.evidence_pack_path`。无法读取证据包时停止审核并说明原因，不得猜测结论。
2. 读取 [输出契约](projects/jiangsu-ops/skills/data-audit-review/references/output-contract.md)，明确提交字段与核验项要求。
3. 从证据包 `tabs` 依次审阅三个页签（`initialReview` 初审结果 / `constant` 恒值 / `outlier` 离群值）：
   - 每条审核记录按 `stationCode + timePoint + pollutantCode` 定位，先看 `auditBeforeValue/auditAfterValue/auditBeforeMark/auditAfterMark`（平台初审做了什么操作：维持原值、修约、加 RM 标识等）。
   - 再看 `matchedRules`（该数据点命中的全部异常模型规则，`reason/proof` 含平台 AI 研判标签与判断依据），注意：平台模型标签是待核验线索，不是本次复核结论。
   - 最后核对该记录 `evidence` 内的监测五分钟/小时值、仪器状态、设备运行、质控记录、运维工单、门禁、动环与报警、气象等证据链，判断初审操作与证据是否相互支撑。
4. 形成整站整日的审核结论：初审操作总体是否有证据支撑、是否存在应处理未处理（异常证据明显但初审未处理）或过度处理（证据不支持修改/标识）的数据点、数据有效性边界是否合理。
5. 调用 `submit_task_review` 提交结构化结论并生成人工确认卡片。

## 结论表达要求

- `summary` 是给审核员看的业务结论，50 字以内，只说四件事：数据是否有效、有效的原因、无效的原因、无效剔除的时间段（精确到小时区间）。
- 不写 IT 术语和过程性废话：接口名、字段名、页签代码、schema、取证过程、证据缺口描述一律不进 summary，放 `checks` 与 `comment`。

## 判断约束

- 数值 `null` 表示缺失或源无效占位，不是 0；CO 单位为 mg/m3，其余为 ug/m3，不换算。
- 证据链窗口为事件小时及前一小时；报警、门禁、工单、质控是同站点同范围关联证据，不表示与某条数据点的逐条因果匹配，不得直接写成因果结论。
- `deviceStatusData` 与 `powerEnvironmentData.measurements` 同源，不得重复计数；Water1/SmokeState 是小时内命中次数，不是实时开关状态。
- 平台初审结果记录（initialReview）是人工已完成初审的操作，属于核心事实；恒值/离群页签记录可能尚未做初审操作，属于异常模型线索。
- 证据包 `gaps` 中列出的页签失败或记录截断必须写入 `checks`/`comment` 说明，不得静默忽略，也不得写进 `summary`；单个辅助证据源（如门禁未配置返回空）缺失不阻断结论，但要说明。
- 视频报警只返回图片地址与定位信息，地址可能仅内网有效；不得描述或推断画面内容。
- 长期记忆和历史案例只用于形成待核验假设，不能替代本次证据。
- 当前阶段禁止自动回写审核平台数据或状态，禁止自动剔除、修改或重算监测数据。

## 增量复审轮次（平台人工日志反馈后）

当事件 `payload.continuity_context` 存在且 `reason=platform_audit_feedback` 时，本次为平台人工审核日志回流后的增量复审，不是全新审核：

1. `continuity_context.platform_audit_logs` 是平台人工初审/复核的操作摘要（数据修改位置、审核前后值、操作人），属于权威修正基准，优先于上一轮 AI 推断；完整日志在 `audit_logs_path`，必要时用 `read_file` 查看。
2. 先阅读 `continuity_context.previous_submission`（上一轮结论），逐项对照人工日志定位分歧，再基于同一证据包重新核验相关记录。
3. 除非存在与人工处理直接矛盾且确凿的证据并在 `comment` 中逐条列明分歧依据，否则必须按人工口径修正 `decision` 与核验项；不得原样重复被退回的结论，也不得以辅助证据缺口为由维持待定。
4. 修正后仍以 `payload.subject_id` 作为 `subject_id` 再次调用 `submit_task_review` 提交覆盖全部事实的完整结论；同一轮复审只提交一次。

## 审核完成后

任务级历史学习会把平台人工反馈沉淀为案例并更新长期记忆（由系统自动完成），不要在结论中复制固定 SOP 或输出契约。

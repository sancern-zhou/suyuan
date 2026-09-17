# 技能索引

此文件由技能管理服务自动生成，请勿手动编辑。

- [备机季度分析](backup-quarterly-analysis/SKILL.md) - 江苏备机合规与使用季度分析。
- [日常运维监管月度报告](daily-operations-supervision-report/SKILL.md) - 面向江苏省周/月常态化监管与月度绩效考核，围绕计划、人员、站点设备三条链路开展全量扫描，输出核心考核指标、确定违规清单与考核指标异常站点，并生成面向环境业务管理用户的正式报告。
- [江苏数据审核 AI 复核](data-audit-review/SKILL.md) - 复核江苏省审核平台已完成初审的站点-审核日数据准确性。从平台证据包读取初审结果、恒值、离群值三页签审核记录及其监测、仪器、设备、质控、工单、门禁、动环、气象证据链，判断平台初审操作是否有证据支撑，生成可人工确认的 AI 审核结论；平台人工审核日志回流后按人工口径增量修正。
- [故障工单月度分析](fault-work-order-monthly-analysis/SKILL.md) - 江苏故障工单月度综合分析与报告生成。
- [江苏故障工单审核](fault-work-order-review/SKILL.md) - 审核江苏省中心故障工单事件。用于从审核事件证据包读取工单详单、质控、5 分钟宽表原始监测、小时原始数据、动环、告警、同区确定性摘要、传输缺失和附件线索，按证据包 sop_id 渐近读取对应 SOP 手册，生成可人工确认归档的结构化审核结论。
- [运维风险监管报告](operations-risk-prevention-report/SKILL.md) - 面向重污染窗口期、专项督查与飞行检查线索支撑，扫描现场作业真实性、高值窗口期、备机与特殊业务、多源证据矛盾等高风险方向，输出确定违规与疑似风险线索聚合清单，并生成面向环境业务管理用户的正式报告。
- [江苏例行运维工单审核](ops-work-order-audit/SKILL.md) - 例行工单审核、例行运维工单审核、巡检工单审核。审核江苏运维平台非故障例行工单（巡检/现场检查/校准/质控/质量保证/数据录入）并生成可追溯的问题清单与审核报告。用于指定时间、状态或工单范围的规则筛查、命中解释和报告生成；普通工单查询不使用本技能，故障工单审核请使用 fault-work-order-review。
- [江苏智能事件研判](smart-event-judgment/SKILL.md) - Analyze Jiangsu smart-event clue bundles and evidence packages, define the final event type and name after evidence review, assess data impact and level, and produce a human-confirmable judgment. Use for the unified Jiangsu smart-event AI task; do not use for direct station-fault diagnosis or work-order review.
- [江苏站点告警诊断](station-alarm-diagnosis/SKILL.md) - Analyze Jiangsu air-monitoring station platform alarms, device alarms, monitoring-data anomalies, quality-control faults, communication faults, and environment/power faults from an event evidence package. Use when a station fault event needs evidence-based diagnosis, remediation steps, verification criteria, and a review-ready work-order draft.
- [工单轨迹合理性分析 SOP](工单轨迹合理性分析/SKILL.md) - 江苏运维签到轨迹月度分析，生成正式报告并创建人工复核待办。

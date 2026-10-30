# 技能索引

此文件由技能管理服务自动生成，请勿手动编辑。

- [备机季度分析](projects/guangdong/skills/backup-quarterly-analysis/SKILL.md) - 广东备机合规与使用季度分析。基于广东设备生命周期事件、故障工单与设备台账数据集，统计备机启用时效、连续运行超期和站点更换频次，生成面向运维统筹管理用户的正式报告。
- [日常运维监管月度报告](projects/guangdong/skills/daily-operations-supervision-report/SKILL.md) - 面向广东省周/月常态化监管与月度绩效考核，围绕工单处置、告警通知、巡检执行、绩效得分与金额、平台到报率、设备生命周期等链路开展全量扫描，输出真实业务指标、问题清单与异常站点，并生成面向环境业务管理用户的正式报告。
- [数据审核 AI 复核（未接入）](projects/guangdong/skills/data-audit-review/SKILL.md) - 江苏审核平台专用技能，依赖平台初审事件、证据包和人工审核日志回流。广东部署当前未接入对应平台与事件流，暂不启用。
- [故障工单月度分析](projects/guangdong/skills/fault-work-order-monthly-analysis/SKILL.md) - 广东故障工单月度综合分析与报告生成。基于广东工单分析宽表与流程明细，统计故障结构、响应与修复时效、重复故障、高频站点和单位对比，生成面向运维管理用户的正式报告。
- [故障工单审核](projects/guangdong/skills/fault-work-order-review/SKILL.md) - 广东故障工单人工复核。按工单号、站点或时间窗口核对故障单的处置流程、响应与修复时效、附件与表单证据、告警与设备事件、站点监测佐证，输出接口事实、复核建议和尚需补充证据三类结论。
- [运维风险监管报告](projects/guangdong/skills/operations-risk-prevention-report/SKILL.md) - 面向广东省运维风险线索扫描与风险防范报告，覆盖故障处置与超时在办、重复故障聚集、告警通知集中、巡检超期、绩效异常波动、设备生命周期与连续缺数等方向，输出确定问题与疑似线索分级清单及人工复核建议。
- [智能事件研判（未接入）](projects/guangdong/skills/smart-event-judgment/SKILL.md) - 江苏智能事件中心专用技能，依赖事件线索包、证据包和事件中心数据库。广东部署当前未接入智能事件中心，暂不启用。
- [站点故障诊断](projects/guangdong/skills/station-alarm-diagnosis/SKILL.md) - 广东站点故障诊断。按站点、设备、时间窗口和异常现象，结合工单处置记录、设备生命周期、告警通知、站点监测数据和知识图谱线索，给出候选原因排序、支持与反证证据、缺失信息和现场处置建议。
- [工单轨迹合理性分析（未接入）](projects/guangdong/skills/工单轨迹合理性分析/SKILL.md) - 江苏签到轨迹月度分析专用技能，依赖签到轨迹接口。广东部署未接入人员签到与轨迹数据，暂不启用。
- [分析报告通用工作流](backend/docs/skills/analysis_report_workflow.md) - 面向生态环境管理用户的分析报告通用方法：明确任务边界、拆解问题结构、数据获取、校验与清洗、分析、提炼结论、成稿与可视化、质检、交付九步全流程，配套工作原则（不编数字、可回溯、区分事实与判断、量化优先、先结论后论证）。正式报告走全程，快问快答可裁剪为"拆解+分析"；流程可并行迭代，不是严格瀑布。
- [Archify 图技能](backend/docs/skills/archify.md) - 为 suyuan 项目助手模式生成和校验架构、工作流、序列、数据流和生命周期图；优先使用已安装的 Archify 包完成 JSON authoring、验证、交付和预览。
- [ops-work-order-audit](backend/docs/skills/ops_work_order_audit.md) - 审核运维工单并生成可追溯的最终问题清单或正式审核报告，正式报告仅输出审核范围和问题工单明细。用于指定时间或范围内工单的规则筛查、抽样复核、语义复核、命中解释、问题清单整理和审核报告生成；普通工单查询不使用本技能。
- [station-operation-daily](backend/docs/skills/station-operation-daily/SKILL.md) - 通过无需LLM的固定工作流按原始Word模板生成国控、省控站点运行监控日报，使用小时数据快照确定性判定连续缺数超过4小时的事件及其恢复、回补，并跟进历史未结事件。用于站点运行日报定时任务及同口径补跑。

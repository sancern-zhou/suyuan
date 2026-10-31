# 技能索引

此文件由技能管理服务自动生成，请勿手动编辑。

- [分析报告通用工作流](backend/docs/skills/analysis_report_workflow.md) - 面向生态环境管理用户的分析报告通用方法：明确任务边界、拆解问题结构、数据获取、校验与清洗、分析、提炼结论、成稿与可视化、质检、交付九步全流程，配套工作原则（不编数字、可回溯、区分事实与判断、量化优先、先结论后论证）。正式报告走全程，快问快答可裁剪为"拆解+分析"；流程可并行迭代，不是严格瀑布。
- [架构图绘制技能](backend/docs/skills/archify.md) - 为 suyuan 项目助手模式生成和校验架构、工作流、序列、数据流和生命周期图；优先使用已安装的 Archify 包完成 JSON authoring、验证、交付和预览。
- [运维工单审核分析技能](backend/docs/skills/ops_work_order_audit.md) - 审核运维工单并生成可追溯的最终问题清单或正式审核报告，正式报告仅输出审核范围和问题工单明细。用于指定时间或范围内工单的规则筛查、抽样复核、语义复核、命中解释、问题清单整理和审核报告生成；普通工单查询不使用本技能。
- [常规监测分析](backend/docs/skills/routine_monitoring_analysis_expert.md) - 用于空气质量分析中的常规监测事实梳理、AQI 口径判断、污染物变化分析、区域同步性分析和风险提示。该 skill 专注于业务知识和分析逻辑，不绑定具体城市、文件名、报告模板或子 Agent 返回格式。
- [天气形势与污染扩散分析](backend/docs/skills/weather_analysis_expert.md) - 按参考 DOCX 的章节、表头和逐日卡片生成许昌未来7天详细分析及第8—15天展望，以表格和图片为主、短句为辅。Agent 自主研判天气过程和风险，最终展示结构必须遵守本技能。
- [许昌市城市超标污染溯源报告](backend/docs/skills/xuchang_city_exceedance_source_report.md) - 暂无描述
- [许昌市昨日污染回顾分析](backend/docs/skills/xuchang_station_daily_source_report.md) - 以站点小时浓度连续快速抬升过程为日报专项分析对象，分钟告警仅作匹配线索；使用 Fetcher 冻结的确定性证据生成 QMD 报告。
- [生态环境招投标市场分析](backend/docs/skills/生态环境招投标市场分析.md) - 面向广东旭诚科技有限公司市场分析人员和大气环境产品经理的可追溯分析报告工作流，覆盖招投标市场研究、数据分析、洞察提炼和 Word/PPT/HTML/Excel 交付。
- [站点运行监控日报](backend/docs/skills/station-operation-daily/SKILL.md) - 通过无需LLM的固定工作流按原始Word模板生成国控、省控站点运行监控日报，使用小时数据快照确定性判定连续缺数超过4小时的事件及其恢复、回补，并跟进历史未结事件。用于站点运行日报定时任务及同口径补跑。

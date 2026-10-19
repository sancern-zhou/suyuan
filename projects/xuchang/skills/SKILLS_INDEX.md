# 技能索引

此文件由技能管理服务自动生成，请勿手动编辑。

- [environment-database-lookup](projects/xuchang/skills/environment-database-lookup/SKILL.md) - 当用户需要从环境监测、气象、排放、企业或监管数据库取得可复核事实时使用。优先本地数据和现有 Fetcher/SQL 工具，按明确来源、时间范围、字段和证据记录执行轻量查询。
- [environment-evidence-lookup](projects/xuchang/skills/environment-evidence-lookup/SKILL.md) - 当用户明确需要污染机理、源解析方法、环境标准或技术背景的外部文献证据时使用。先用少量权威来源形成短证据链，不将科研型系统综述流程默认用于日常环境管理问答。
- [environment-spatial-audit](projects/xuchang/skills/environment-spatial-audit/SKILL.md) - 当环境管理问题需要核对站点、企业、行政区、上风向扇区或距离关系时使用。先校验坐标系和空间范围，再做最小空间连接或距离计算，不把空间邻近直接写成污染贡献或责任归因。
- [evidence-document-extraction](projects/xuchang/skills/evidence-document-extraction/SKILL.md) - 当用户需要从 DOCX、PDF、扫描件或表格中提取可追溯的环境证据时使用。优先读取 manifest、页码和结构化字段，按需保留版面位置，不默认批量扫描全部文档。
- [geospatial-analysis](projects/xuchang/skills/geospatial-analysis/SKILL.md) - 专家和报告模式按需执行可追溯的站点、行政区、企业和 GeoJSON 空间分析。
- [statistical-analysis](projects/xuchang/skills/statistical-analysis/SKILL.md) - 专家和报告模式按需执行可追溯的环境统计分析、假设检查、趋势回归和季节性分析。
- [天气形势与污染扩散分析](projects/xuchang/skills/weather_analysis_expert/SKILL.md) - 按参考 DOCX 的章节、表头和逐日卡片生成许昌未来7天详细分析及第8—15天展望，以表格和图片为主、短句为辅。Agent 自主研判天气过程和风险，最终展示结构必须遵守本技能。
- [许昌市城市超标污染溯源报告 Skill](projects/xuchang/skills/xuchang_city_exceedance_source_report/SKILL.md) - 面向许昌单日超标污染过程的城市级溯源报告，以场景二冻结证据包（站点日超标分析 v3 输出）为唯一事实来源，按固定七章模板生成，不重抓数据、不重绘图表。
- [许昌市昨日污染回顾分析 Skill](projects/xuchang/skills/xuchang_station_daily_source_report/SKILL.md) - 以站点小时浓度连续快速抬升过程为日报专项分析对象，分钟告警仅作匹配线索；使用 Fetcher 冻结的确定性证据生成 QMD 报告。
- [分析报告通用工作流](backend/docs/skills/analysis_report_workflow.md) - 面向生态环境管理用户的分析报告通用方法：明确任务边界、拆解问题结构、数据获取、校验与清洗、分析、提炼结论、成稿与可视化、质检、交付九步全流程，配套工作原则（不编数字、可回溯、区分事实与判断、量化优先、先结论后论证）。正式报告走全程，快问快答可裁剪为"拆解+分析"；流程可并行迭代，不是严格瀑布。
- [Archify 图技能](backend/docs/skills/archify.md) - 为 suyuan 项目助手模式生成和校验架构、工作流、序列、数据流和生命周期图；优先使用已安装的 Archify 包完成 JSON authoring、验证、交付和预览。
- [ops-work-order-audit](backend/docs/skills/ops_work_order_audit.md) - 审核运维工单并生成可追溯的最终问题清单或正式审核报告，正式报告仅输出审核范围和问题工单明细。用于指定时间或范围内工单的规则筛查、抽样复核、语义复核、命中解释、问题清单整理和审核报告生成；普通工单查询不使用本技能。
- [示例2](backend/docs/skills/routine_monitoring_analysis_expert.md) - 用于空气质量分析中的常规监测事实梳理、AQI 口径判断、污染物变化分析、区域同步性分析和风险提示。该 skill 专注于业务知识和分析逻辑，不绑定具体城市、文件名、报告模板或子 Agent 返回格式。
- [生态环境招投标市场分析](backend/docs/skills/生态环境招投标市场分析.md) - 面向广东旭诚科技有限公司市场分析人员和大气环境产品经理的可追溯分析报告工作流，覆盖招投标市场研究、数据分析、洞察提炼和 Word/PPT/HTML/Excel 交付。

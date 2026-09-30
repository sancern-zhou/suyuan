# 许昌市城市超标污染溯源报告 Skill

## 概述

面向许昌单日超标污染过程的城市级溯源报告，以场景二冻结证据包（站点日超标分析 v3 输出）为唯一事实来源，按固定七章模板生成，不重抓数据、不重绘图表。

## 任务定位

仅处理 xuchang.station_daily_source_analysis.completed 事件对应的单个超标日。《许昌市空气质量回顾分析日报》（持续升高模板）和无超标日例行分支不适用。Agent 只读事件 payload 的 evidence_package_path（场景二分析输出 JSON），不重新抓数、触发告警、运行轨迹或改写证据。

## 证据与结论边界

- 先确认 schema_version=xuchang_station_daily_source_analysis/v3、target_date、daily_evaluation、data_quality，再依次阅读 city_day_statistics（city_hourly、district_hourly、daypart、pollutant_correlation、regional、township_daily_top、peak_township）、national_hourly、township_hourly、regional_hourly、meteorology_evidence、trajectory_quality、transport_diagnosis、cwt、enterprise_screening。时间均为北京时间。
- 日均超标是发布日值判定；小时浓度、日均浓度和 O3 日最大八小时平均不可互换，不将单站过程写成全市官方 AQI 超标。
- 筛查得分=清单年排放量/(1+距离/10km)，只用于排序现场核查顺序，禁止写成贡献率、责任或"嫌疑大小"。不使用未经校准的 Kleinman 指数、固定行业倍数或复合贡献率。
- 相关性系数只说明共变/同源线索，不构成因果；周边城市 r≥0.8 只支持"区域同步本底"判断，本地增量需结合峰值时刻先后、上风向浓度与轨迹证据综合表述；单一证据不写确定性结论。
- 上风向扇区是标注信息不是门槛；enterprise_screening.status 不是 screened 时不列企业表，只说明原因。
- 分段统计口径固定为夜间 0-8 时、午后 12-17 时；静风指风速<0.5 m/s；缺测或样本不足（乡镇 not_available、相关性站点样本低于阈值、轨迹质量门未过）时在对应章节如实说明，不得臆测。

## 报告与交付

正文固定七章：一、分析摘要；二、污染过程与多点小时变化；三、气象扩散条件；四、本地排放与外来传输；五、污染源类型指示；六、空间分布与嫌疑企业；七、结论与建议。图1—图8 由证据包 visualizations 提供（国控小时曲线、城区区县对比、气象组合图、周边城市对比、夜间午后柱状、相关性热力图、乡镇空间分布、企业筛查得分），Agent 只引用不重绘、不补造坐标。图表缺失时保留图注并说明证据缺口。

agent_text 只包含 summary_text、air_quality_analysis、meteorology_analysis、transport_analysis、source_type_analysis、spatial_analysis、local_source_analysis、conclusion 八个键；conclusion 必须覆盖污染类型、本地与传输关系、源类型、高值区四个维度，并落到针对嫌疑行业和重点时段的管控建议。

先读 backend/app/tools/report/report_package/references/index.md。最终用 execute_python 调用 app.scenarios.xuchang_city_exceedance.qmd_report.write_city_day_qmd_report，输入为证据路径、agent_text 和由 artifact_path 生成的唯一 QMD 路径。按同次工具返回的 data.files/file_paths 将生成的 QMD 替换成已发布路径；图片资源沿用函数返回的 assets 路径。只调用一次 create_report_package，输出 html、docx、share_html；检查三种产物及资源验收结果。

## 部署同步

项目 scheduled_tasks 下的 JSON 是任务种子；已有 custom 任务的运行时配置不会被启动时的种子同步自动覆盖。更新本 Skill 对应的任务 Prompt/skill_id 后，需要将新配置显式更新到许昌运行环境，并重启或重新加载 web 与 worker。

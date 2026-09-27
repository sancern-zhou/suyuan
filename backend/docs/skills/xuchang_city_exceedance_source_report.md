# 许昌市城市超标污染溯源报告 Skill

## 概述

面向许昌逐小时污染过程的独立溯源报告，以冻结证据包形成审慎的机制分析和核查建议。

## 任务定位

仅处理 xuchang.city_source_analysis.completed 事件对应的单个污染过程。昨日污染回顾的日报和无异常日分支不适用。Agent 只读事件 payload 的 evidence_package_path，不重新抓数、触发告警、运行轨迹或改写证据。

## 证据与结论边界

- 先检查 schema_version、process_window、trigger、data_quality，再阅读 station_hourly、township_and_provincial_transport、meteorology_evidence、trajectory_quality、transport_diagnosis、cwt、enterprise_screening。时间均为北京时间。
- AQI≥101 是发布指数触发；PM2.5≥75 μg/m³ 是业务高值触发，不写作现行日均法定限值。小时浓度、日均浓度和 O3 日最大八小时平均不可互换。单站过程不称为全市官方 AQI 超标。
- 可说明国控站、乡镇站和周边城市的同期变化及风来向一致性。无有效风向、坐标、同期样本或空间覆盖不足时写明无法判断。乡镇站不参与国控基线，不对稀疏站点插值推断源区。
- ERA5 边界层高度与地面降温只是扩散或逆温间接线索，不能写成探空实测逆温。HYSPLIT、轨迹走廊和 CWT 是潜在传输线索；质量门未通过时不输出确定方向。
- 不用未经校准的 Kleinman 指数、固定行业倍数或复合得分给出本地/外来贡献率或企业责任。年度源清单只能列待核查候选；enterprise_screening.status 不是 screened 时不列企业 Top-N。
- 将支持证据、反证和缺测分别写出。单一浓度峰值、同向风或后向轨迹均不能证明因果。

## 报告与交付

正文依次为污染过程概况、空气质量时空特征、气象扩散条件、区域传输线索、本地候选核查、结论与建议。逐节只写证据支持的事实；图件只引用证据包已有图片，不重绘或补造坐标。

先读 backend/app/tools/report/report_package/references/index.md。最终用 execute_python 调用 app.scenarios.xuchang_city_exceedance.qmd_report.write_qmd_report_from_evidence，输入为证据路径、agent_text 和由 artifact_path 生成的唯一 QMD 路径。agent_text 只包含 summary_text、air_quality_analysis、meteorology_analysis、transport_analysis、local_source_analysis、conclusion。按同次工具返回的 data.files/file_paths 将生成的 QMD 替换成已发布路径；原始注册目录的图片资源沿用函数返回的 assets 路径。只调用一次 create_report_package，输出 html、docx、share_html；检查三种产物及资源验收结果。

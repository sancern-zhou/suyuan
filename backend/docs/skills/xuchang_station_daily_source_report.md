# 许昌市昨日污染回顾分析 Skill

## 任务定位

按照《许昌市空气质量回顾分析日报》模板，生成昨日许昌市 QMD 同源报告包，供用户选择导出 HTML 或 Word。HTML 保留交互 GIS 地图；两种格式均保留相同章节、事实表、分析文字及基于逐小时证据的静态浓度趋势图。Fetcher 复用场景一告警 episode，做确定性合并与计算；报告 Agent 只读预计算证据，撰写过程分析和结论，不重新判定告警或补算数据。

任务事件 payload 的 evidence_package_path 是 manifest.json。先读其 evidence_files.report_brief 与 evidence_files.event_brief，不扫描目录。所有路径来自 manifest，项目相对路径以项目根目录解析。必要时再按 field_guide 读取其他类型化 JSON。pollutant_maps.json 是渲染专用数据，Agent 不读入上下文。

## 数据契约

| 内容 | 文件与字段 |
| --- | --- |
| 合并后告警次数、清单、日概览 | report_brief.json:episode_count / alert_list / meteorology_intervals |
| 每次合并告警的完整事实 | event_brief.json:events[]，以 event_id 为键；alert_intervals[] 标记实际告警段，gap_hour_count 标记无告警空档 |
| 每次告警的风向、升幅、上风向乡镇站浓度/距离/方位/目标站对比 | event_brief.json:events[].wind / peak_rise_* / upwind_township_stations[]；跨空档事件逐段读取 segments[] 的同名字段 |
| 城市与市站 PM2.5 概览 | report_brief.json:station_pm25_statistics / regional_city_pm25_statistics |
| 原始 episode 的前中后与区域响应细节（只在需要时） | stage_brief.json:episodes[]、regional_responses.json:episodes[]，以 source_episode_ids 关联 |
| 逐小时 GIS 地图及 Word 静态图（仅组装程序读取） | pollutant_maps.json:maps[]，每种告警污染物一组同源图 |

Fetcher 对同一国控站、同一污染物的场景一告警 episode，若时间重叠、下一小时接续或中间仅隔 1 个无告警小时，则合并为一次；更长空档不合并，跨站或不同污染物不合并。alert_intervals[] 保留实际告警时段；合并跨度内的空档不是告警小时，地图不得标红。report_brief.episode_count、event_brief.event_count、第一章表格行数与第二章过程数必须一致；原始 episode 数只用于溯源，不得称作报告中的“告警次数”。

事件升幅是事件内峰值相对告警前一小时有效浓度的变化；该小时缺测时使用事件内首个有效小时值，并标记参考口径。若数值为 0 或负数，应如实写“未见上升”或“下降”；不可仅因它被列入场景一告警就声称其浓度持续升高。CO 用 mg/m³，其他污染物用 μg/m³。风向采用 NMC 10 米风来向，在事件小时内按有效风速作矢量平均，静风与缺测不参与；仅在有有效风向、坐标和浓度时，按风来向 ±67.5°、距目标站不超过 20 km 筛选上风向乡镇站，按距离展示最近 10 站并保留候选总数。乡镇站浓度为合并事件时段内有效小时均值，距离为目标国控点到乡镇站的球面距离；“高于/低于”仅比较双方同小时的有效样本均值。风向缺测时必须说明无法识别上风向，不能根据站点方位自行推断。

## 报告结构

模板文件：backend/backend_data_registry/uploads/2d1aabdc-ca0a-4bcd-9166-07d38a5e595b.docx。保留模板标题、日期与章节顺序：

1. 一、持续升高基本情况：只使用合并后事件清单，一行对应一次告警过程；时段列逐项列出实际告警段，不把短空档写成连续告警；浓度变化、升幅和绝对增量为整个合并跨度的过程统计。Agent 的 summary_text 用简短业务语言概括合并次数和主要变化；若无事件，保留章节并说明。
2. 二、持续升高原因分析：按“国控站点＋污染物”归组，同组内按事件逐次展示。跨短空档事件先交代过程跨度，再按 segments[] 分别列出各段的时段、参考小时值/峰值、升幅、主导风向及上风向乡镇站的距离、方位、浓度、对比；不得用一段的风向解释另一段。Agent 为每个 event_id 写一段 event_analysis，结合各段预计算证据比较可能机制和不确定性。不要自行改写数值或将空间相邻等同于传输。
3. 第二章中的时序图：HTML 中每种发生告警的污染物只放一张真实高德底图及昨日逐小时时间轴；地图汇集各站观测并高亮当时告警国控点，不按站点重复放地图。Word 中同位置改为该污染物逐小时站点均值、最大值及告警时段的静态趋势图；不能把静态图称为 GIS 地图。图仅辅助阅读，不需要 Agent 为地图或每个小时写额外文字说明。
4. 四、结论：总结主要站点、污染物、时段和可支持的区域响应判断及建议关注的乡镇站；不写确定源区、贡献率、企业责任。

模板第二章原有的上风向站点表格保留为确定性事实展示，并由 Agent 的逐事件文字分析解释；污染物级时间轴图作为第二章附加可视化。不得新增模板没有的独立章节。正文使用业务语言，不暴露事件 ID、文件路径或内部字段名。

## 固定版式契约（QMD v1）

报告版式由 backend/app/scenarios/xuchang_daily_review/qmd_report.py 确定性生成，以 report.qmd 为唯一正文源；地图组件和样式复用 html_report.py。Agent 只提供 summary_text、conclusion、event_analysis，不输出 QMD、HTML、CSS、Markdown 表格或自行调整章节。后续修改版式时，应同时更新本节、组装器和测试。

- 标题固定为“许昌市空气质量回顾分析日报”，标题下显示报告日期；正文依次为“一、持续升高基本情况”“二、持续升高原因分析”“四、结论”，不因当日告警数量改变章节。
- 第一章固定一张六列表格，表头及顺序为“站点｜污染物｜升高时段｜浓度变化｜升幅｜绝对增量”；每个合并事件一行，升高时段列列出实际告警段，按证据包事件顺序展示。无事件时显示固定的无告警说明，不生成空表。
- 第二章按国控站点＋污染物分节，每个合并事件展示过程事实和分析文字。跨短空档事件逐段展示事实及站点表，其他事件展示一张站点表。表格表头及顺序为“类型｜站名｜距离(km)｜方位｜浓度(对应污染物单位)｜对比”；首行为国控点，之后按证据包顺序列出上风向乡镇站；无合格站点时保留首行，并在表内显示固定的无站点说明。
- 第二章所有事件之后固定放“污染物时序变化图”小节。HTML 展示每种告警污染物一张交互地图，随后附同源逐小时静态趋势图；Word 在相同位置展示静态趋势图。地图下方不添加 Agent 文本。第四章只放结论文字。
- 两类表格均由 QMD 标准表格生成，固定表头、列顺序及数值右对齐；HTML 使用浅色表头、完整边框、交替行底色和窄屏横向滚动，Word 使用统一的文档表格样式。缺测显示“—”，浓度单位 CO 为 mg/m³、其他污染物为 μg/m³；数值沿用证据包精度，不由 Agent 二次舍入。
- QMD front matter 显式关闭 HTML 与 DOCX 的自动章节编号，正文手写模板中的中文章名；DOCX 禁用自动目录和编号，避免双重编号。HTML 地图资源位于报告包 assets，Word 图像位于 assets/charts，由 create_report_package 复制与验收。不得写入 R/knitr 代码、绝对资源路径或 /api/image 引用。

## 地图视觉契约（HTML 导出）

地图外观和交互由 html_report.py 的组件确定性生成，再作为 QMD 的 HTML 专用内容输出；Agent 只提供事件分析文字，不能自行生成地图代码、补造站点浓度或逐小时说明。改动下列规则时同步更新渲染器与测试：

- 底图默认使用真实高德卫星影像叠加路网，另提供浅色矢量底图和可选 3D 地形切换。真 3D 地形只在高德 JS API v2.1Beta、浏览器 WebGL 可用时启用；不可用时保留卫星影像，明确显示降级状态，不把卫星图误称为地形图。
- 每种污染物只展示一张地图。站点浓度使用蓝绿→黄→橙红的连续色阶与适度变化的点径；色阶上下限取 pollutant_maps.json 该污染物的全天固定 scale_min / scale_max，所有小时共用，不按帧重新缩放。图例始终显示单位和上下限。浓度颜色与告警身份分离：告警国控站用红色外环/轻微脉冲突出，圆心仍按浓度着色；无数据不画点，短空档不亮告警环。点选显示站名、站型、当前小时浓度及单位。
- 地图上方保留当前日期小时、告警站数和播放状态；地图下方提供完整的 24 小时时序横幅，逐小时可点选，当前小时高亮，真实告警小时用独立标记提示。播放/暂停、速度和拖动控件相互同步，切帧更新点样式而非整图闪烁；结束后循环播放，允许随时暂停。尊重浏览器减少动态效果设置。
- 地图视野以全日有效站点坐标确定一次，播放时不随每小时站点增减而跳动；窄屏仍能横向浏览时间轴。不得画插值热力面、扩散羽流、传输箭头或未经证据支持的源区；底图、图例和动画仅服务于观测事实的阅读。

## 交付方式

Agent 组织小型 agent_text：summary_text、conclusion、event_analysis（字典，键为 event_id，值为该合并事件的分析段落）。不再生成 stages、地图下方说明或按小时文字。无事件时 event_analysis 可为空，但仍需结论。

先读取 backend/app/tools/report/report_package/references/index.md。最后只调用一次 execute_python 构建 QMD 与资源，代码为：

    import json
    from uuid import uuid4
    from app.scenarios.xuchang_daily_review.qmd_report import write_qmd_report_from_evidence
    result = write_qmd_report_from_evidence(
        manifest_path, agent_text, artifact_path(f'xuchang_review_{uuid4().hex}.qmd'))
    print(json.dumps(result, ensure_ascii=False))

manifest_path 必须直接使用事件 payload 的路径。地图公开 Key 已由 Fetcher 放在 manifest.render_config_path，组装函数读取；Agent 不搜索 Key、.env、源码或沙箱路径。配置缺失时报告失败并要求重新生成证据包。execute_python 会把沙箱内的 QMD 和资源移动到永久目录：其 stdout JSON 中的 source_qmd_path 与 assets[].path 是**临时路径，不能直接传给下一工具**。必须从同一次 execute_python 返回的 data.files/file_paths 中按文件名精确匹配 source_qmd_name 与 assets[].name，将 source_qmd_path 和各 assets[].path 替换为已发布的永久路径；匹配不到则立即报告失败。文件名含随机后缀，防止任务重跑时碰撞。随后只调用一次 create_report_package：使用匹配后的 report_id、source_qmd_path、assets，output_formats 固定为 ["html", "docx", "share_html"]，title 为“许昌市空气质量回顾分析日报”，report_type 为 government。html 用于右侧预览，share_html 是可独立下载打开的 HTML，docx 是 Word 下载稿；用户可选择下载哪种格式。以 create_report_package 返回的正式报告包、HTML 预览和两种导出产物为准；execute_python 的临时 QMD 发布不作为交付。不要调用 create_html_artifact、render_report_package 或直接生成 DOCX。

## 质检

- 核对 report_brief.episode_count == event_brief.event_count，第一章仅统计合并后过程，第二章每个 event_id 都有分析文字；跨空档事件须逐段核对 segments[]，不得将空档算作告警小时。
- 对照 event_brief 检查站点、污染物、时间、升幅、风向、乡镇浓度、距离、单位；不能把缺测或无净上升写成持续抬升事实。
- 上风向仅为风向一致的候选站；浓度较高和时序同步不能单独确定污染来源。
- HTML 第二章每种告警污染物仅一张地图，短空档小时不高亮国控站；Word 第二章每种污染物有一张静态趋势图，两种格式均无 Agent 分阶段说明。
- 检查 create_report_package 成功且 HTML 预览、share_html、DOCX 渲染与资源验收通过；两个导出版本都应保留表格和逐事件分析。失败时明确阶段与原因，不把仅生成 QMD 当作已完成交付。

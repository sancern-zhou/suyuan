# 许昌市昨日污染回顾分析 Skill

## 概述
以站点小时浓度连续快速抬升过程为日报专项分析对象，分钟告警仅作匹配线索；使用 Fetcher 冻结的确定性证据生成 QMD 报告。

## 任务定位

按照《许昌市空气质量回顾分析日报》模板，生成昨日许昌市 QMD 同源报告包，供用户选择导出 HTML 或 Word。日报正文只保留章节、事实表和分析文字；污染物时序变化地图已暂时移出日报，不在报告中直接生成，仅在报告交付后经用户确认单独生成（见交付方式）。两种格式均不生成逐小时站点浓度趋势图。Fetcher 先用国控站有效小时数据确定入选的持续快速抬升过程，再将同站、同污染物且时间匹配的场景一分钟事件作为辅助线索。报告 Agent 只读已冻结的确定性事实，撰写审慎分析与结论；不得重新判定、抓取或扫描原始行。

任务事件 payload 的 evidence_package_path 是 manifest.json。先读其 evidence_files.report_brief 与 evidence_files.event_brief，不扫描目录。所有路径来自 manifest，项目相对路径以项目根目录解析。二者已覆盖入选计数、小时轨迹、门槛、分钟线索、风和上风向站点；仅在解释区域响应有明确需要时，按 field_guide 读取对应类型化 JSON，不重复探测。hourly_rise_detection.json 留作规则审计，pollutant_maps.json 仅供渲染程序读取，均不常规塞入 Agent 上下文。

## 数据契约

| 内容 | 文件与字段 |
| --- | --- |
| 小时过程次数、清单、日概览 | report_brief.json:episode_count / alert_list / alert_source_status / hourly_data_coverage / hourly_quality_note / meteorology_intervals；episode_count 为兼容字段，语义为小时过程数 |
| 每次过程的确定性触发事实 | event_brief.json:events[]，以 event_id 为键；hourly_observations[]、qualified_windows[]、duration_hours、minimum_absolute_rise、reference_time、peak_rise_* |
| 分钟线索及环境证据 | event_brief.json:events[].minute_clues[] / source_episode_ids[] / wind / upwind_township_stations[]；没有分钟线索的小时过程仍正常入选 |
| 规则审计与小时数据覆盖 | hourly_rise_detection.json:rule_version / checked_windows / qualified_windows / duplicate_conflicts / valid_target_hours / events[]；仅需复核时读取 |
| 城市与市站 PM2.5 概览 | report_brief.json:station_pm25_statistics / regional_city_pm25_statistics |
| 小时过程的前中后与区域响应细节（只在需要时） | stage_brief.json:episodes[]、regional_responses.json:episodes[]，以过程 episode_id 关联 |
| 逐小时 GIS 地图与小时风观测（仅独立地图程序读取，不进入日报） | pollutant_maps.json:maps[]，每种告警污染物一张地图，frames[].weather 为对应小时 NMC 风观测；仅在用户确认后生成独立地图时使用 |

Fetcher 对 PM2.5、PM10、NO2、SO2、CO 逐站扫描连续 3 或 4 个有效小时值，即历时 2 或 3 小时。初值必须大于 0；各相邻小时严格上升、无缺测；末值至少为初值的 1.5 倍，且绝对增量分别达到 10、15、8、6 μg/m³ 与 0.3 mg/m³。O3 与 NOX 不进入此规则。相等门槛视为命中；重叠命中窗口合并为同一小时过程，中断或回落后另起过程，不因单个无告警小时自动拼接。跨日过程按命中窗口的末小时归入日报，并允许读取前一日最多 3 小时作为起点。

分钟事件只在同站、同污染物且实际事件时间位于起点小时至结束小时之后一小时的半开区间时关联；证据中标明按事件时间还是 episode 边界时间匹配。仅分钟告警、无合格小时过程的事件不进入本日报专项分析。report_brief.episode_count、event_brief.event_count、第一章表格行数与第二章过程数必须一致；raw_episode_count 表示已关联的分钟 episode 数，不是日报过程数。alert_source_status=data_unavailable 代表小时数据不可用，insufficient_data 代表没有足够连续有效小时窗；两者均不得写作“昨日无异常”。

事件升幅以入选小时过程的起点值和末值确定；小时轨迹、阈值、计数与版本由 Fetcher 存储，Agent 不得另选基线或重新舍入。稳定高值与单小时突增可在每日背景中提及，但不符合本规则时不得称为“持续快速抬升”。CO 用 mg/m³，其他污染物用 μg/m³。风向采用 NMC 10 米风来向，在事件小时内按有效风速作矢量平均，静风与缺测不参与；仅在有有效风向、坐标和浓度时，按风来向 ±67.5°、距目标站不超过 20 km 筛选上风向乡镇站，按距离展示最近 10 站并保留候选总数。乡镇站浓度为事件时段内有效小时均值；“高于/低于”仅比较双方同小时的有效样本均值。风向缺测时不得推断上风向。

## 报告结构

模板文件：backend/backend_data_registry/uploads/2d1aabdc-ca0a-4bcd-9166-07d38a5e595b.docx。保留模板标题、日期与章节顺序：

1. 一、持续升高基本情况：只使用入选的小时过程清单，一行对应一次过程；时段、起点浓度、末值、升幅和绝对增量均从 event_brief 读取。Agent 的 summary_text 用简短业务语言概括过程数和主要变化；若小时数据有效但无入选事件，保留章节并说明“昨日没有出现小时告警污染。”；小时数据不可用时必须说明证据缺口。
2. 二、持续升高原因分析：按“国控站点＋污染物”归组，同组内按过程逐次展示。Agent 为每个 event_id 写一段 event_analysis，可结合已关联的分钟线索、区域响应、风来向和乡镇站同期对比评估可能机制与不确定性；线索缺失不影响小时过程入选。不要自行改写数值或将空间相邻等同于传输。
3. 四、结论：总结主要站点、污染物、时段和可支持的区域响应判断及建议关注的乡镇站；不写确定源区、贡献率、企业责任。

模板第二章原有的上风向站点表格保留为确定性事实展示，并由 Agent 的逐事件文字分析解释。日报不包含污染物时序变化地图或任何地图小节；报告完成后必须先询问用户是否需要单独生成地图，未经确认不得生成。不得新增模板没有的独立章节。正文使用业务语言，不暴露事件 ID、文件路径或内部字段名。

## 固定版式契约（QMD v1）

报告版式由 backend/app/scenarios/xuchang_daily_review/qmd_report.py 确定性生成，以 report.qmd 为唯一正文源；地图组件和样式复用 html_report.py。Agent 只提供 summary_text、conclusion、event_analysis，不输出 QMD、HTML、CSS、Markdown 表格或自行调整章节。后续修改版式时，应同时更新本节、组装器和测试。

- 标题固定为“许昌市空气质量回顾分析日报”，标题下显示报告日期；正文依次为“一、持续升高基本情况”“二、持续升高原因分析”“四、结论”，不因当日告警数量改变章节。
- 第一章固定一张六列表格，表头及顺序为“站点｜污染物｜升高时段｜浓度变化｜升幅｜绝对增量”；每个小时过程一行，时段列展示命中过程小时，按证据包顺序展示。无过程且小时数据足以判断时不生成空表，说明“昨日没有出现小时告警污染。”；数据不可用或连续样本不足时说明无法判定。
- 第二章按国控站点＋污染物分节，每个小时过程展示一段确定性事实与分析文字。表格表头及顺序为“类型｜站名｜距离(km)｜方位｜浓度(对应污染物单位)｜对比”；首行为国控点，之后按证据包顺序列出上风向乡镇站；无合格站点时保留首行，并在表内显示固定的无站点说明。
- 第二章所有事件之后不再放置任何地图小节；日报不含污染物时序变化地图，HTML 与 Word 均只保留事实表及分析文字。第四章只放结论文字。
- 两类表格均由 QMD 标准表格生成，固定表头、列顺序及数值右对齐；HTML 使用浅色表头、完整边框、交替行底色和窄屏横向滚动，Word 使用统一的文档表格样式。缺测显示“—”，浓度单位 CO 为 mg/m³、其他污染物为 μg/m³；数值沿用证据包精度，不由 Agent 二次舍入。
- QMD front matter 显式关闭 HTML 与 DOCX 的自动章节编号，正文手写模板中的中文章名；DOCX 禁用自动目录和编号，避免双重编号。日报资产仅含样式表；独立地图报告的样式与脚本资产由 create_report_package 复制与验收。不得写入 R/knitr 代码、绝对资源路径或 /api/image 引用。

## 地图视觉契约（仅独立地图报告）

污染物时序变化地图不再随日报生成；仅在用户确认后作为独立地图报告交付（HTML/share_html，交互地图无法进入 Word）。地图外观和交互由 html_report.py 的组件确定性生成，经 qmd_report.py 的 write_map_only_report_from_evidence 组装；Agent 只提供询问与确认，不生成地图代码、补造站点浓度或逐小时说明。改动下列规则时同步更新渲染器与测试：

- 底图默认使用真实高德卫星影像叠加路网，另提供浅色矢量底图和可选 3D 地形切换。真 3D 地形只在高德 JS API v2.1Beta、浏览器 WebGL 可用时启用；不可用时保留卫星影像，明确显示降级状态，不把卫星图误称为地形图。
- 每种污染物只展示一张地图。站点浓度使用蓝绿→黄→橙红的连续色阶与适度变化的点径；色阶上下限取 pollutant_maps.json 该污染物的全天固定 scale_min / scale_max，所有小时共用，不按帧重新缩放。图例始终显示单位和上下限。浓度颜色与告警身份分离：告警国控站用红色外环/轻微脉冲突出，圆心仍按浓度着色；无数据不画点，短空档不亮告警环。点选显示站名、站型、当前小时浓度及单位。
- 地图上方保留当前日期小时、告警站数和播放状态，并同步标注许昌气象站小时风向（来向、角度）与风速（m/s）。该风观测代表许昌气象站，不代表每个空气站的局地风；缺测显示暂无数据，不沿用上一小时值，静风(<0.5 m/s)不提供方向判断；地图下方提供完整的 24 小时时序横幅，逐小时可点选，当前小时高亮，真实告警小时用独立标记提示。播放/暂停、速度和拖动控件相互同步，切帧更新点样式而非整图闪烁；结束后循环播放，允许随时暂停。尊重浏览器减少动态效果设置。
- 地图视野以全日有效站点坐标确定一次，播放时不随每小时站点增减而跳动；窄屏仍能横向浏览时间轴。不得画插值热力面、扩散羽流、传输箭头或未经证据支持的源区；底图、图例和动画仅服务于观测事实的阅读。

## 交付方式

Agent 组织小型 agent_text：summary_text、conclusion、event_analysis（字典，键为 event_id，值为该小时过程的分析段落）。不再生成 stages、地图下方说明或按小时文字。无事件时 event_analysis 可为空，但仍需结论；数据不可用时不得断言无持续抬升。

先读取 backend/app/tools/report/report_package/references/index.md。第一轮交付日报只调用一次 execute_python 构建 QMD 与资源，代码为：

    import json
    from uuid import uuid4
    from app.scenarios.xuchang_daily_review.qmd_report import write_qmd_report_from_evidence
    result = write_qmd_report_from_evidence(
        manifest_path, agent_text, artifact_path(f'xuchang_review_{uuid4().hex}.qmd'))
    print(json.dumps(result, ensure_ascii=False))

日报默认不含地图：不要给 write_qmd_report_from_evidence 传 include_maps 或其他地图参数。manifest_path 必须直接使用事件 payload 的路径。地图公开 Key 已由 Fetcher 放在 manifest.render_config_path，组装函数读取；Agent 不搜索 Key、.env、源码或沙箱路径。配置缺失时报告失败并要求重新生成证据包。execute_python 会把沙箱内的 QMD 和资源移动到永久目录：其 stdout JSON 中的 source_qmd_path 与 assets[].path 是**临时路径，不能直接传给下一工具**。必须从同一次 execute_python 返回的 data.files/file_paths 中按文件名精确匹配 source_qmd_name 与 assets[].name，将 source_qmd_path 和各 assets[].path 替换为已发布的永久路径；匹配不到则立即报告失败。文件名含随机后缀，防止任务重跑时碰撞。随后只调用一次 create_report_package：使用匹配后的 report_id、source_qmd_path、assets，output_formats 固定为 ["html", "docx", "share_html"]，title 为“许昌市空气质量回顾分析日报”，report_type 为 government。html 用于右侧预览，share_html 是可独立下载打开的 HTML，docx 是 Word 下载稿；用户可选择下载哪种格式。以 create_report_package 返回的正式报告包、HTML 预览和两种导出产物为准；execute_python 的临时 QMD 发布不作为交付。不要调用 create_html_artifact、render_report_package 或直接生成 DOCX。

报告包交付完成后，用一句话询问用户“是否需要单独生成污染物时序变化地图”，在用户明确确认前不得生成任何地图。用户确认后才进行第二轮生成：只调用一次 execute_python，代码改为从 app.scenarios.xuchang_daily_review.qmd_report 导入 write_map_only_report_from_evidence 并执行 write_map_only_report_from_evidence(manifest_path, artifact_path(f'xuchang_review_maps_{uuid4().hex}.qmd'))，按同样规则用 data.files/file_paths 匹配并替换临时路径；再只调用一次 create_report_package，output_formats 固定为 ["html", "share_html"]，title 为“污染物时序变化地图”，report_type 为 government；交互地图无法进入 Word，不生成 docx。用户未确认或明确拒绝时，不执行第二轮生成。

## 质检

- 核对 report_brief.episode_count == event_brief.event_count，第一章仅统计入选小时过程，第二章每个 event_id 都有分析文字；分钟线索不能增加过程数。
- 对照 event_brief 检查站点、污染物、连续小时轨迹、起末值、50% 与绝对增量门槛、分钟线索时间、风向、乡镇浓度、距离和单位；数据不可用或区域响应不足时明确说明证据边界。
- 上风向仅为风向一致的候选站；浓度较高和时序同步不能单独确定污染来源。
- 日报 HTML 与 Word 均不含污染物时序变化地图小节、地图资产或任何逐小时站点浓度趋势图；报告交付后已向用户提出是否单独生成地图的确认问题。
- 用户确认后的独立地图报告：每种污染物仅一张地图，仅在小时过程命中小时高亮国控站；地图风向风速与当前小时同步，缺测与静风正确标注；仅输出 HTML/share_html，不含 docx；未经用户确认不得生成。
- 检查 create_report_package 成功且 HTML 预览、share_html、DOCX 渲染与资源验收通过；两个导出版本都应保留表格和逐事件分析。失败时明确阶段与原因，不把仅生成 QMD 当作已完成交付。

## 部署同步

项目 scheduled_tasks 下的 JSON 是任务种子；已有 custom 任务的运行时配置不会被启动时的种子同步自动覆盖。部署本次规则后，需要将项目任务中的新 Prompt 显式更新到对应许昌运行环境，并重启或重新加载 web 与 worker，使 Fetcher、Skill 与任务 Prompt 使用同一版本；不要使用其他项目的环境文件或数据目录。

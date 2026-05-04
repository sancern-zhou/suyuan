"""
工具注册表

定义六种Agent模式的工具列表和排序

⚠️ 注意：保留现有的query模式（WEB端问数模式），新增social模式（移动端呼吸式Agent）
"""

from typing import Dict, List

EXECUTE_SQL_QUERY_DESCRIPTION = (
    "通用SQL执行工具，支持查看表结构和执行SQL查询（二选一）。"
    "⚠️ 查看表结构：describe_table(str, 输入目标表名如'qc_history'、'BSD_STATION'、"
    "'city_168_statistics_new_standard'、'noise_city_compliance_monthly'或"
    "'noise_city_compliance_daily'，动态从数据库获取表结构)。"
    "执行查询：sql(str, SQL查询语句)。"
    "⚠️ SQL Server语法规则：❌ WHERE province_name='广东'（必须用N前缀：N'广东'），"
    "❌ SELECT ... LIMIT 10（SQL Server用TOP而非LIMIT）。"
    "可选：database(str, 数据库名称, 默认'XcAiDb', 查询质控数据时使用'AirPollutionAnalysis')、"
    "limit(int, 返回记录数限制, 默认50, 最大100)。"
    "可用表：【AirPollutionAnalysis数据库】qc_history(自动质控历史数据表)、"
    "quality_control_records(质控例行检查记录)、working_orders(运维工单)、"
    "BSD_STATION(站点信息表，包含站点ID、名称、代码、区域ID、经纬度、地址、状态等)；"
    "【XcAiDb数据库】city_168_statistics_new_standard(168城市空气质量统计-新标准限值)、"
    "city_168_statistics_old_standard(168城市空气质量统计-旧标准限值)、"
    "province_statistics_new_standard(省级空气质量统计-新标准限值)、"
    "province_statistics_old_standard(省级空气质量统计-旧标准限值)、"
    "noise_city_compliance_monthly(城市噪声昼夜达标率月汇总表，字段包括province、city_name、"
    "period_month、station_total、day_compliance_rate、night_compliance_rate、night_status、"
    "is_province_total；当前已导入安徽省2025年11月16地市及全省汇总数据；"
    "night_status按夜间评价达标率是否达到100%分为N'达标'/N'未达标'/N'无有效数据')、"
    "noise_city_compliance_daily(城市噪声昼夜达标率逐日明细表，字段包括city_name、data_date、"
    "night_compliant_station_days、night_valid_station_days、night_compliance_rate、night_status以及"
    "1类/2类/3类/4a类站点有效天数字段；用于展示各城市每日夜间达标和未达标情况)；"
    "【系统视图】information_schema.columns/information_schema.tables(用于动态查询表结构)。"
    "⚠️ **噪声夜间达标查询口径**：全省汇总使用 "
    "SELECT * FROM dbo.noise_city_compliance_monthly WHERE province=N'安徽' "
    "AND period_month='2025-11' AND is_province_total=1；"
    "各地市月度达标/未达标使用 is_province_total=0 并按 night_status 分组或筛选；"
    "逐日未达标明细查询 noise_city_compliance_daily 并筛选 night_status=N'未达标'。"
    "⚠️ **空气质量统计数据表stat_type字段说明**：ytd_to_month(年初到某月累计，如stat_date='2026-03'表示1-3月累计)、"
    "month_current(当月累计，如stat_date='2026-04'表示4月当月)、"
    "year_to_date(年初至今，如stat_date='2026'表示1月至今)、"
    "month_complete(完整月，如stat_date='2026-03'表示3月完整月)"
)

# ===== 助手模式工具 =====
ASSISTANT_TOOLS = {
    # Shell命令
    "bash": "执行Shell命令。参数: command(str)",

    # 文件操作
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。⚠️ **Excel文件（.xlsx/.xls/.xlsm）需要使用 execute_python 工具读取**（read_file会自动检测并提示）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "edit_file": "精确编辑文件（V2版本：支持引号规范化、Trailing空格处理、文件修改检查）。⚠️ 必须先使用read_file读取文件。参数: path(str), old_string(str, 要替换的原内容), new_string(str, 替换后的新内容), replace_all(bool, 可选, 是否替换所有匹配项, 默认false), encoding(str, 可选, 文件编码, 默认自动检测)",
    "grep": "搜索文件内容（支持 Glob 模式、分页、多行模式、上下文控制）。参数: pattern(str, 正则表达式), path(str, 可选, 相对于backend/), glob(str, 可选, 文件模式如*.{py,ts}), output_mode(str, 可选, content/files_with_matches/count), context_lines(int, 可选, 上下文行数), context_lines_before/context_lines_after(int, 可选), show_line_numbers(bool, 可选), multiline(bool, 可选, 多行模式), case_insensitive(bool, 可选), head_limit(int, 可选, 最多返回条数, 默认250), offset(int, 可选, 跳过前N条, 用于分页)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件名（glob模式，支持递归搜索）。⚠️ 参数: pattern(str, glob模式), path(str, 可选, 搜索路径, 默认当前目录)。重要：递归搜索子目录必须使用 **（如'**/*.json'），否则只在指定目录的顶层搜索。示例: search_files(pattern='**/*.json', path='backend/config') 递归搜索所有JSON文件; search_files(pattern='*.py', path='backend/app') 只在backend/app目录搜索Python文件",
    "notebook_edit": "编辑 Jupyter Notebook (.ipynb) 文件的单元格（助手模式 - 办公任务专用）。⚠️ 必须先用read_file读取文件。参数: notebook_path(str, .ipynb文件路径), cell_id(str, 可选, 目标单元格如'cell-0'或索引号), new_source(str, 新单元格内容), cell_type(str, 可选, code/markdown, insert模式必填), edit_mode(str, 可选, replace/insert/delete, 默认replace)",
    "list_skills": "列出可用的技能文档（支持关键词过滤）。参数: keyword(str, 可选, 过滤关键词), category(str, 可选, 分类过滤)",

    # Office工具（⚠️ **必须先阅读 Office 技能指导文档**：read_file(file_path='backend/app/tools/office/office_skills_guide.md')）
    "read_docx": "读取DOCX文档内容（直接读取，无需解包）。参数: path(str), max_paragraphs(int, 可选, 默认100), include_tables(bool, 可选, 默认true)",
    "parse_pdf": "解析PDF文件并提取内容（支持文本提取、OCR识别、表格提取、元数据提取）。⚠️ 必需参数: path(str, PDF文件路径)。可选: mode(str, 解析模式: auto=自动检测/text=文本提取/ocr=OCR识别/table=表格提取/image=图片信息/meta=元数据, 默认auto), pages(str, 页面范围如'1-5', 可选), extract_tables(bool, 是否提取表格, 默认false), extract_images(bool, 是否提取图片信息, 默认false), ocr_engine(str, OCR引擎: auto/qwen/paddleocr/tesseract, 默认auto)",
    "unpack_office": "解包Office文件为XML（Word/Excel/PPT）。参数: path(str, 文件路径), output_dir(str, 可选, 输出目录)",
    "pack_office": "打包XML为Office文件。参数: input_dir(str, XML目录), output_file(str, 可选, 输出文件路径)",
    "word_edit": "Word高级编辑（替换文本、插入内容）。参数: path(str, DOCX文件路径), operation(str, 操作类型: replace_text/replace_paragraph/insert_after/insert_before/delete_paragraph), search(str, 可选, 要查找的文本), replace(str, 可选, 替换后的文本), contains(str, 可选, 段落包含的文本), marker(str, 可选, 标记文本), content(str, 可选, 新内容), new_content(str, 可选, 新内容的别名), output_file(str, 可选, 输出文件路径), backup(bool, 可选, 是否创建备份, 默认true)",
    "accept_word_changes": "接受Word文档的所有修订。参数: input_file(str, DOCX文件路径), output_file(str, 可选, 输出文件路径)",
    "recalc_excel": "Excel公式重算。参数: path(str, XLSX文件路径), timeout(int, 可选, 超时秒数, 默认30)",
    "add_ppt_slide": "PPT添加幻灯片（需要先解包PPTX）。参数: unpacked_dir(str, 解包后的PPTX目录), source(str, 源文件名, 如slideLayout1.xml或slide1.xml)",

    # 任务管理
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # 代码执行
    "execute_python": "执行 Python 代码（数值计算、数据处理、统计分析、可视化生成、Excel文件处理）。⭐ **Excel文件处理**：自动注入辅助函数（读取/修改均自动生成前端预览）。读取：read_excel_with_preview('file.xlsx')返回数据+预览。修改：edit_excel_data('file.xlsx', {'A1':'新值'})保留图表。合并：merge_excel_with_charts([file1, file2], 'output.xlsx')合并多个文件（跨平台保留图表）。❌ 禁止pandas.to_excel()修改现有文件（会丢失图表）。✅ 创建新文件可用pandas。详细文档：backend/app/tools/office/office_skills_guide.md。⭐ **AQI日历图**：from app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id; img = generate_calendar_from_data_id(data_id='xxx', year=2026, month=3); print('CHART_SAVED:data:image/png;base64,' + img)。⭐ **极坐标污染玫瑰图**：from app.tools.visualization.polar_contour_generator import generate_pollution_rose_contour; img = generate_pollution_rose_contour(data_id='xxx', pollutant_name='PM10'); print('CHART_SAVED:data:image/png;base64,' + img)。参数: code(str), timeout(int, 可选, 默认30)",

    # 其他工具
    "create_scheduled_task": "创建定时任务。参数: user_request(str)",
    "analyze_image": "分析图片内容。参数: path(str), operation(str, 可选, 默认analyze), prompt(str, 可选)",
    "browser": "浏览器自动化。[必须先阅读browser_skills_guide.md]",
    "call_sub_agent": "调用子Agent。参数: target_mode(str), goal(str), context_str(str, 可选)",
}

# ===== 专家模式工具 =====
EXPERT_TOOLS = {
    # 数据查询工具（自然语言查询）
    "get_vocs_data": "查询VOCs组分数据（自然语言查询，支持时间、站点、物种等过滤）。⚠️ 必需参数: question(str, 自然语言查询问题)",
    "get_pm25_ionic": "查询PM2.5水溶性离子（F⁻、Cl⁻、NO₂⁻、NO₃⁻、SO₄²⁻、PO₄³⁻、Li⁺、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、Al³⁺等）。⚠️ 必需参数: locations(list, 城市名/站点名, 自动映射), start_time(str), end_time(str)。可选: data_type(int, 0=原始/1=审核), time_granularity(int, 1=小时/2=日/3=月/5=年)",
    "get_pm25_carbon": "查询PM2.5碳组分（有机碳OC、元素碳EC）。⚠️ 必需参数: locations(list, 城市名/站点名, 自动映射), start_time(str), end_time(str)。可选: data_type(int, 0=原始/1=审核), time_granularity(int, 1=小时/2=日/3=月/5=年)",
    "get_pm25_crustal": "查询PM2.5地壳元素（铝Al、硅Si、钙Ca、铁Fe、钛Ti、钾K等）。⚠️ 必需参数: locations(list, 城市名/站点名, 自动映射), start_time(str), end_time(str)。可选: data_type(int, 默认1=审核), time_granularity(int, 默认0=小时), elements(list, 元素列表, 默认['Al','Si','Fe','Ca','Ti','Mn'])",
    "get_weather_forecast": "查询天气预报（未来7-16天，支持获取今天和昨天数据，Open-Meteo API）。⚠️ 必需参数: lat(float), lon(float)。可选: location_name(str), forecast_days(int, 默认7), past_days(int, 默认0), hourly(bool, 默认true), daily(bool, 默认true)",

    # 全国城市历史数据查询工具
    "query_xcai_city_history": "查询全国城市历史空气质量数据（SQL Server XcAiDb数据库，支持773个城市）。⚠️ 必需参数: cities(list, 城市名称如'广州市'), data_type(str, hour=小时数据/day=日数据), start_time(str, 格式YYYY-MM-DD HH:MM:SS), end_time(str, 格式YYYY-MM-DD HH:MM:SS)。小时数据表2017年至今，日数据表2021年至今",
    "execute_sql_query": EXECUTE_SQL_QUERY_DESCRIPTION,
    # 广东省数据查询工具（⚠️ 注意区分城市级别和站点级别工具）
    "query_gd_suncere_city_hour": "查询广东省【城市级别】小时空气质量数据（⚠️ 仅支持城市名称如'广州'、'深圳'，不支持站点名称如'广雅中学'。如需站点小时数据，请使用 query_gd_suncere_station_hour_new）。⚠️ 必需参数: cities(list, 城市名称列表), start_time(str, 'YYYY-MM-DD HH:MM:SS'), end_time(str, 'YYYY-MM-DD HH:MM:SS')。可选: include_weather(bool, 是否包含气象字段, 默认true, 包含风速/风向/温度/湿度/气压等)",
    "query_gd_suncere_city_day": "查询广东省【城市级别】日空气质量数据（旧标准 HJ 633-2013，⚠️ 仅支持城市名称如'广州'、'深圳'，不支持站点名称如'广雅中学'。如需站点日数据，请使用 query_gd_suncere_station_day_new）。参数: cities(list, 城市名称列表), start_date(str), end_date(str), data_type(int, 可选, 0原始实况/1审核实况默认/2原始标况/3审核标况)",
    "query_gd_suncere_city_day_new": "查询广东省【城市级别】日空气质量数据（新标准 HJ 633-2026，⚠️ 仅支持城市名称如'广州'、'深圳'，不支持站点名称如'广雅中学'。如需站点日数据，请使用 query_gd_suncere_station_day_new）。参数: cities(list, 城市名称列表), start_date(str), end_date(str), data_type(int, 可选, 0原始实况/1审核实况默认/2原始标况/3审核标况)",
    "query_gd_suncere_station_hour_new": "查询广东省【站点级别】小时空气质量数据（⭐ 新标准 HJ 633-2026，自动计算新标准IAQI、AQI、首要污染物。⚠️ 适用场景：当用户提到具体站点名称（如'广雅中学'、'市监测站'、'天河职防'）或需要站点级别数据时必须使用此工具，不要使用 query_gd_suncere_city_hour）。⚠️ 必需参数: start_time(str, 'YYYY-MM-DD HH:MM:SS'), end_time(str, 'YYYY-MM-DD HH:MM:SS')。可选: station_type(str, 站点类型, 默认'国控'。⚠️ 仅在使用cities参数时有效，用于过滤该城市下的指定类型站点。如果使用stations参数，则不需要此参数), cities(list, 城市名自动展开该城市下所有站点，与stations至少提供一个), stations(list, 站点名称如['广雅中学','市监测站'], 与cities至少提供一个。使用stations时不需要提供station_type), include_weather(bool, 是否包含气象字段, 默认true, 包含风速/风向/温度/湿度/气压等)",
    "query_gd_suncere_station_day_new": "查询广东省【站点级别】日空气质量数据（⭐ 新标准 HJ 633-2026，自动计算新标准IAQI、AQI、首要污染物。⚠️ 适用场景：当用户提到具体站点名称或需要站点级别日数据时使用此工具，不要使用 query_gd_suncere_city_day_new）。⚠️ 必需参数: start_date(str, 'YYYY-MM-DD'), end_date(str, 'YYYY-MM-DD')。可选: station_type(str, 站点类型, 默认'国控'。⚠️ 仅在使用cities参数时有效，用于过滤该城市下的指定类型站点。如果使用stations参数，则不需要此参数), cities(list, 城市名自动展开该城市下所有站点，与stations至少提供一个), stations(list, 站点名称如['广雅中学','市监测站'], 与cities至少提供一个。使用stations时不需要提供station_type)",
    "query_new_standard_report": "【第一优先级】查询HJ 633-2026新标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。⚠️ 优先使用此工具获取统计结果，不要手动计算。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理), use_old_composite_algorithm(bool, 可选, 默认false, 使用旧综合指数算法。false=新算法(PM2.5权重3,NO2权重2,O3权重2),true=旧算法(所有权重均为1))",
    "query_old_standard_report": "【第一优先级】查询HJ 633-2013旧标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。⚠️ 优先使用此工具获取统计结果，不要手动计算。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理), use_new_composite_algorithm(bool, 可选, 默认false, 使用新综合指数算法。false=旧算法(所有权重均为1),true=新算法(PM2.5权重3,NO2权重2,O3权重2))",
    "query_standard_comparison": "【第一优先级】新旧标准对比统计查询（返回综合指数、超标天数、达标率等统计指标）。⚠️ 优先使用此工具获取统计结果，不要手动计算。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理)",
    "compare_standard_reports": "【第一优先级】新标准报表对比分析（对比两个时间段的综合指数、超标天数、达标率、六参数统计、单项质量指数、首要污染物统计等全部指标）。⚠️ 同比环比查询必须使用此工具，禁止手动计算。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "compare_old_standard_reports": "【第一优先级】旧标准报表对比分析（基于 HJ 633-2013 旧标准，对比两个时间段的综合指数、超标天数、达标率、六参数统计、单项质量指数、首要污染物统计等全部指标）。⚠️ 旧标准同比环比查询必须使用此工具，禁止手动计算。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "read_data_registry": "读取已保存的数据。⚠️ **必须指定 time_range 参数（list_fields 模式除外）**，支持时间范围、字段选择、jq聚合。⚠️ 过滤后明细超过200条会拒绝返回完整data，请缩小time_range、减少fields或使用jq_filter聚合。参数: data_id(str), time_range(str, **数据读取时必填**), list_fields(bool, 可选, 查看字段时使用), fields(可选, list), jq_filter(可选, str, ⚠️ **聚合操作返回标量值**：length/max/min/add 返回数字，不是数组)",

    # 分析工具（需先获取数据）
    "calculate_pm_pmf": "PM2.5 PMF源解析（需先调用get_pm25_ionic和get_pm25_carbon获取数据）。参数: data_ids(list), n_factors(int, 可选, 默认5)",
    "calculate_vocs_pmf": "VOCs PMF源解析（需先调用get_vocs_data获取数据）。参数: data_id(str), n_factors(int, 可选, 默认5)",
    "calculate_pmf": "PMF源解析（需先调用get_pm25_ionic和get_pm25_carbon获取数据）。参数: data_id(str), n_factors(int, 可选, 默认5)",
    "calculate_obm_ofp": "OBM/OFP分析（需先调用get_vocs_data获取数据）。⚠️ 必需参数: vocs_data_id(str)。可选: air_quality_data_id(str, 空气质量数据ID)",
    "analyze_upwind_enterprises": "上风向企业分析（独立工具，直接输入参数）。⚠️ 必需参数: lat(float), lon(float), start_time(str)。可选: city_name(str, 城市名称), station_name(str, 站点名称), search_range_km(float, 搜索半径km, 默认5), max_enterprises(int, 最大企业数, 默认10), top_n(int, 显示前N个, 默认8), map_type(str, 地图类型, 默认normal), mode(str, 分析模式, 默认topn_mixed)",
    "meteorological_trajectory_analysis": "后向轨迹分析（独立工具，直接输入参数，基于NOAA HYSPLIT模型）。⚠️ 必需参数: lat(float), lon(float), start_time(str)。可选: hours(int, 后向小时数, 默认72), height(float, 起始高度m, 默认500), meteorological_data(str, 气象数据类型, 默认era5)",
    "analyze_trajectory_sources": "轨迹+源清单深度溯源（独立工具，结合后向轨迹和排放源清单）。⚠️ 必需参数: lat(float), lon(float), start_time(str)。可选: city_name(str), station_name(str), hours(int, 默认72), height(float, 默认500), meteorological_data(str, 默认era5), pollutant(str, 默认PM2_5)",
    "calculate_reconstruction": "PM2.5七大组分重构（需先调用get_pm25_ionic、get_pm25_carbon、get_pm25_crustal获取数据）。参数: ionic_data_id(str), carbon_data_id(str), crustal_data_id(str)",
    "calculate_carbon": "碳组分分析POC/SOC/EC（需先调用get_pm25_carbon获取数据）。参数: data_id(str)",
    "calculate_soluble": "水溶性离子分析（需先调用get_pm25_ionic获取数据）。参数: data_id(str)",
    "calculate_crustal": "地壳元素分析（需先调用get_pm25_crustal获取数据）。参数: data_id(str)",
    "calculate_trace": "微量元素分析（需先调用get_pm25_crustal获取数据）。参数: data_id(str)",
    "predict_air_quality": "空气质量预测（需先获取历史空气质量数据）。参数: city(str), days(int, 可选, 默认7)",

    # 可视化工具
    "revise_chart": "修订已生成图表（基于用户反馈调整图表）。⚠️ 必需参数: chart_id(str), revision_instruction(str, 修订说明)",
    "generate_map": "生成地图可视化（高德地图，展示站点位置和污染分布）。⚠️ 必需参数: locations(list, 站点列表, 每个站点包含lat/lon)。可选: map_type(str, 地图类型: scatter/heatmap/bubble, 默认scatter), center_lat/center_lon(float, 地图中心), zoom(int, 缩放级别, 默认10)",

    # 任务管理
    "TodoWrite": "更新任务清单（完整替换）。⚠️ 溯源分析任务必须使用: TodoWrite(task_list_file='backend/config/task_lists/quick_trace_standard_multi_agent.md')，不要手动输入items（会丢失详细信息）",

    # 代码执行
    "execute_python": "执行 Python 代码（数值计算、数据处理、统计分析、可视化生成、Excel文件处理）。⭐ **Excel文件处理**：自动注入辅助函数（读取/修改均自动生成前端预览）。读取：read_excel_with_preview('file.xlsx')返回数据+预览。修改：edit_excel_data('file.xlsx', {'A1':'新值'})保留图表。合并：merge_excel_with_charts([file1, file2], 'output.xlsx')合并多个文件（跨平台保留图表）。❌ 禁止pandas.to_excel()修改现有文件（会丢失图表）。✅ 创建新文件可用pandas。详细文档：backend/app/tools/office/office_skills_guide.md。⭐ **AQI日历图**：from app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id; img = generate_calendar_from_data_id(data_id='xxx', year=2026, month=3); print('CHART_SAVED:data:image/png;base64,' + img)。⭐ **极坐标污染玫瑰图**：from app.tools.visualization.polar_contour_generator import generate_pollution_rose_contour; img = generate_pollution_rose_contour(data_id='xxx', pollutant_name='PM10'); print('CHART_SAVED:data:image/png;base64,' + img)。参数: code(str), timeout(int, 可选, 默认30)",

    # 文件操作（保存分析结果、读取配置文件）
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。⚠️ **Excel文件（.xlsx/.xls/.xlsm）需要使用 execute_python 工具读取**（read_file会自动检测并提示）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "edit_file": "精确编辑文件（V2版本：支持引号规范化、Trailing空格处理、文件修改检查）。⚠️ 必须先使用read_file读取文件。参数: path(str), old_string(str, 要替换的原内容), new_string(str, 替换后的新内容), replace_all(bool, 可选, 是否替换所有匹配项, 默认false), encoding(str, 可选, 文件编码, 默认自动检测)",
    "grep": "搜索文件内容（支持 Glob 模式、分页、多行模式、上下文控制）。参数: pattern(str, 正则表达式), path(str, 可选, 相对于backend/), glob(str, 可选, 文件模式如*.{py,ts}), output_mode(str, 可选, content/files_with_matches/count), context_lines(int, 可选, 上下文行数), context_lines_before/context_lines_after(int, 可选), show_line_numbers(bool, 可选), multiline(bool, 可选, 多行模式), case_insensitive(bool, 可选), head_limit(int, 可选, 最多返回条数, 默认250), offset(int, 可选, 跳过前N条, 用于分页)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件名（glob模式，支持递归搜索）。⚠️ 参数: pattern(str, glob模式), path(str, 可选, 搜索路径, 默认当前目录)。重要：递归搜索子目录必须使用 **（如'**/*.json'），否则只在指定目录的顶层搜索。示例: search_files(pattern='**/*.json', path='backend/config') 递归搜索所有JSON文件; search_files(pattern='*.py', path='backend/app') 只在backend/app目录搜索Python文件",
    "notebook_edit": "编辑 Jupyter Notebook (.ipynb) 文件的单元格（专家模式 - 数据分析专用）。⚠️ 必须先用read_file读取文件。自动记录任务到任务列表。参数: notebook_path(str, .ipynb文件路径), cell_id(str, 可选, 目标单元格如'cell-0'或索引号), new_source(str, 新单元格内容), cell_type(str, 可选, code/markdown, insert模式必填), edit_mode(str, 可选, replace/insert/delete, 默认replace)",

    # 其他
    "call_sub_agent": "调用助手Agent。参数: target_mode(str), goal(str), context_str(str, 可选)",
    "FINISH_SUMMARY": "生成分析报告。参数: answer(str)",
}

# ===== 问数模式工具 =====
QUERY_TOOLS = {
    # === 系统操作 ===
    "bash": "执行Shell命令。参数: command(str), timeout(int, 可选, 默认60), working_dir(str, 可选)",

    # === 源码查看工具（了解工具实现细节） ===
    "grep": "搜索文件内容（支持 Glob 模式、分页、多行模式、上下文控制）。参数: pattern(str, 正则表达式), path(str, 可选, 相对于backend/), glob(str, 可选, 文件模式如*.{py,ts}), output_mode(str, 可选, content/files_with_matches/count), context_lines(int, 可选, 上下文行数), context_lines_before/context_lines_after(int, 可选), show_line_numbers(bool, 可选), multiline(bool, 可选, 多行模式), case_insensitive(bool, 可选), head_limit(int, 可选, 最多返回条数, 默认250), offset(int, 可选, 跳过前N条, 用于分页)",
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。⚠️ **Excel文件（.xlsx/.xls/.xlsm）需要使用 execute_python 工具读取**（read_file会自动检测并提示）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "edit_file": "精确编辑文件（V2版本：支持引号规范化、Trailing空格处理、文件修改检查）。⚠️ 必须先使用read_file读取文件。参数: path(str), old_string(str, 要替换的原内容), new_string(str, 替换后的新内容), replace_all(bool, 可选, 是否替换所有匹配项, 默认false), encoding(str, 可选, 文件编码, 默认自动检测)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件名（glob模式，支持递归搜索）。⚠️ 参数: pattern(str, glob模式), path(str, 可选, 搜索路径, 默认当前目录)。重要：递归搜索子目录必须使用 **（如'**/*.json'），否则只在指定目录的顶层搜索。示例: search_files(pattern='**/*.json', path='backend/config') 递归搜索所有JSON文件; search_files(pattern='*.py', path='backend/app') 只在backend/app目录搜索Python文件",

    # === 现有参数化查询工具（复用） ===
    "get_pm25_ionic": "查询PM2.5水溶性离子。参数: start_time(str), end_time(str), locations(可选)",
    "get_pm25_carbon": "查询PM2.5碳组分。参数: start_time(str), end_time(str), locations(可选)",
    "get_pm25_crustal": "查询PM2.5地壳元素。参数: start_time(str), end_time(str), locations(可选)",
    "get_weather_forecast": "查询天气预报（未来7-16天，支持获取今天和昨天数据，Open-Meteo API）。⚠️ 必需参数: lat(float), lon(float)。可选: location_name(str), forecast_days(int, 默认7), past_days(int, 默认0), hourly(bool, 默认true), daily(bool, 默认true)",
    "query_xcai_city_history": "查询全国城市历史空气质量数据（SQL Server XcAiDb数据库，支持773个城市）。⚠️ 必需参数: cities(list, 城市名称如'广州市'), data_type(str, hour=小时数据/day=日数据), start_time(str, 格式YYYY-MM-DD HH:MM:SS), end_time(str, 格式YYYY-MM-DD HH:MM:SS)。小时数据表2017年至今，日数据表2021年至今",
    "execute_sql_query": EXECUTE_SQL_QUERY_DESCRIPTION,
    "query_gd_suncere_city_hour": "查询广东省【城市级别】小时空气质量数据（⚠️ 仅支持城市名称如'广州'、'深圳'，不支持站点名称如'广雅中学'。如需站点小时数据，请使用 query_gd_suncere_station_hour_new）。参数: cities(list, 城市名称列表), start_time(str, 'YYYY-MM-DD HH:MM:SS'), end_time(str, 'YYYY-MM-DD HH:MM:SS'), include_weather(bool, 可选, 是否包含气象字段, 默认true, 包含风速/风向/温度/湿度/气压等)",
    "query_gd_suncere_station_hour_new": "查询广东省【站点级别】小时空气质量数据（⭐ 新标准 HJ 633-2026，自动计算新标准IAQI、AQI、首要污染物。⚠️ 适用场景：当用户提到具体站点名称（如'广雅中学'、'市监测站'、'天河职防'）或需要站点级别数据时必须使用此工具，不要使用 query_gd_suncere_city_hour）。⚠️ 必需参数: start_time(str, 'YYYY-MM-DD HH:MM:SS'), end_time(str, 'YYYY-MM-DD HH:MM:SS')。可选: station_type(str, 站点类型, 默认'国控'。⚠️ 仅在使用cities参数时有效，用于过滤该城市下的指定类型站点。如果使用stations参数，则不需要此参数), cities(list, 城市名自动展开该城市下所有站点，与stations至少提供一个), stations(list, 站点名称如['广雅中学','市监测站'], 与cities至少提供一个。使用stations时不需要提供station_type), include_weather(bool, 是否包含气象字段, 默认true, 包含风速/风向/温度/湿度/气压等)",
    "query_gd_suncere_station_day_new": "查询广东省站点级别日空气质量数据（⭐ 新标准 HJ 633-2026，自动计算新标准IAQI、AQI、首要污染物，三天内原始数据，三天前审核数据）。⚠️ 必需参数: station_type(str, 站点类型, 如'国控'/'省控'/'市控'或'1.0'/'2.0'/'3.0'), start_date(str, 'YYYY-MM-DD'), end_date(str, 'YYYY-MM-DD')。可选: cities(list, 城市名自动展开站点, 与stations至少提供一个), stations(list, 站点名称如['广雅中学','市监测站'], 与cities至少提供一个)",
    "query_gd_suncere_city_day": "查询广东省【城市级别】日空气质量数据（旧标准 HJ 633-2013，⚠️ 仅支持城市名称，不支持站点名称。如需站点日数据，请使用 query_gd_suncere_station_day_new）。参数: cities(list, 城市名称列表, 如['广州','深圳']), start_date(str), end_date(str), data_type(int, 可选, 0原始实况/1审核实况默认/2原始标况/3审核标况)",
    "query_gd_suncere_city_day_new": "查询广东省【城市级别】日空气质量数据（新标准 HJ 633-2026，⚠️ 仅支持城市名称，不支持站点名称。如需站点日数据，请使用 query_gd_suncere_station_day_new）。参数: cities(list, 城市名称列表, 如['广州','深圳']), start_date(str), end_date(str), data_type(int, 可选, 0原始实况/1审核实况默认/2原始标况/3审核标况)",
    "query_gd_suncere_regional_comparison": "查询广东省区域对比空气质量数据（目标城市与周边城市对比，用于区域传输分析）。参数: target_city(str), nearby_cities(list), start_time(str, 'YYYY-MM-DD HH:MM:SS'), end_time(str, 'YYYY-MM-DD HH:MM:SS')",
    "query_new_standard_report": "查询HJ 633-2026新标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理), use_old_composite_algorithm(bool, 可选, 默认false, 使用旧综合指数算法。false=新算法(PM2.5权重3,NO2权重2,O3权重2),true=旧算法(所有权重均为1))",
    "query_old_standard_report": "查询HJ 633-2013旧标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理), use_new_composite_algorithm(bool, 可选, 默认false, 使用新综合指数算法。false=旧算法(所有权重均为1),true=新算法(PM2.5权重3,NO2权重2,O3权重2))",
    "query_standard_comparison": "新旧标准对比统计查询（返回综合指数、超标天数、达标率等统计指标）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理)",
    "compare_standard_reports": "新标准报表对比分析（对比两个时间段的综合指数、超标天数、达标率、六参数统计、单项质量指数、首要污染物统计等全部指标）。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "compare_old_standard_reports": "旧标准报表对比分析（基于 HJ 633-2013 旧标准，对比两个时间段的综合指数、超标天数、达标率、六参数统计、单项质量指数、首要污染物统计等全部指标）。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "query_station_new_standard_report": "站点级新标准统计报表查询（基于 HJ 633-2026，查询站点的综合指数、超标天数、达标率、六参数统计）。⚠️ 与城市工具的差异：不支持扣沙处理，使用station_name字段，支持城市名称自动展开为站点列表。⚠️ 必需参数: start_date(str), end_date(str)。可选: station_type(str, 站点类型, 默认'国控'。⚠️ 仅在使用cities参数时有效，用于过滤该城市下的指定类型站点。如果使用stations参数，则不需要此参数), cities(list, 城市名自动展开站点, 与stations至少提供一个。如果不提供station_type，默认查询国控站点), stations(list, 站点名称, 与cities至少提供一个。使用stations时不需要提供station_type), aggregate(bool, 是否计算多站点汇总, 默认false)",
    "compare_station_standard_reports": "站点级新标准报表对比分析（对比两个时间段的站点统计数据，返回差值和变化率）。⚠️ 站点级同比环比查询必须使用此工具，禁止手动计算。参数: query_period{start_date, end_date}, comparison_period{start_date, end_date}, cities(list, 可选, 城市名自动展开站点), stations(list, 可选, 站点名称), aggregate(bool, 可选, 是否计算多站点汇总对比, 默认false)",

    # === 新增：全国省份空气质量查询工具 ===
    "query_national_province_air_quality": "查询全国各省份空气质量统计数据（六参数均值、AQI达标率、综合指数）。⚠️ 数据来源：参考项目 GDQFWS_SYS（广东省环境监测中心预报预警系统），支持31个省份。⚠️ 必需参数: start_date(str, 开始日期'YYYY-MM-DD'), end_date(str, 结束日期'YYYY-MM-DD')。可选: ns_type(str, 数据类型, 默认'NS')。返回数据: AreaCode(省份代码), AreaName(省份名称), SO2/NO2/CO/O3_8h/PM10/PM2_5(六参数均值), SumIndex(综合指数), AQIStandardRate(AQI达标率%)",
    "query_national_city_air_quality": "查询全国各城市空气质量统计数据（六参数均值、AQI达标率、综合指数）。⚠️ 数据来源：参考项目 GDQFWS_SYS（广东省环境监测中心预报预警系统）。⚠️ 必需参数: start_date(str, 开始日期'YYYY-MM-DD'), end_date(str, 结束日期'YYYY-MM-DD')。可选: province_code(str, 省份代码, 如'440000'表示广东省, 不填则查询全国所有城市), ns_type(str, 数据类型, 默认'NS')。返回数据: AreaCode(城市代码), AreaName(城市名称), SO2/NO2/CO/O3_8h/PM10/PM2_5(六参数均值), SumIndex(综合指数), AQIStandardRate(AQI达标率%)",

    # === 数据注册表工具 ===
    "read_data_registry": "读取已保存的数据。⚠️ **必须指定 time_range 参数（list_fields 模式除外）**，支持时间范围、字段选择、jq聚合。⚠️ 过滤后明细超过200条会拒绝返回完整data，请缩小time_range、减少fields或使用jq_filter聚合。参数: data_id(str), time_range(str, **数据读取时必填**), list_fields(bool, 可选, 查看字段时使用), fields(可选, list), jq_filter(可选, str, ⚠️ **聚合操作返回标量值**：length/max/min/add 返回数字，不是数组)",

    # === 知识库检索（预报会商场景） ===
    "knowledge_qa_workflow": "知识库检索入口。⚠️ 调用前应先把用户原问题改写成组合检索词：保留原始问题全文，并追加3-8个补充关键词/同义词/标准号不同写法/文件简称/英文缩写；不要只传抽象摘要。示例: 用户问'HJ 633-2026 综合指数怎么算'，query可写为'HJ 633-2026 综合指数怎么算 综合指数 计算方法 评价项目 分指数 IAQI AQI HJ633-2026 环境空气质量指数'。参数: query(str, 原问题+补充关键词的组合检索词), knowledge_base_ids(list, 可选, 指定知识库ID), top_k(int, 可选, 默认3, 最多10), reranker(str, 可选, auto/always/never, 默认auto)。返回sources和document_read_targets；严肃知识问答应继续调用knowledge_document_reader读取相邻chunks后再答。",
    "knowledge_document_reader": "读取知识库文档的chunk文本视图。适用：knowledge_qa_workflow返回document_read_targets后，按document_id+chunk_index读取相邻chunks或全文chunks，再回答严肃知识问答。参数: knowledge_base_id(str, 必需), document_id(str, 必需), chunk_index(int, 可选, 单个命中chunk索引), chunk_indices(list[int], 可选, 多个命中chunk索引), mode(str, 可选, neighbor_chunks/all_chunks, 默认neighbor_chunks), window(int, 可选, 相邻窗口, 默认2), max_chunks(int, 可选, 返回chunk上限, 默认30)",

    # === 可视化工具 ===

    # === 数值计算工具 ===
    "execute_python": "【第二优先级】执行 Python 代码进行数值计算（均值、中位数、百分比、单位换算等）、可视化生成（AQI日历图、极坐标污染玫瑰图）或Excel文件处理。⚠️ **计算场景：仅当统计查询工具无法满足需求时才使用（如自定义聚合、复杂计算等）。禁止用于同环比、超标率等常见统计计算（应使用compare_standard_reports或query_new_standard_report）。❌ 禁止用来校验统计查询工具返回的结果。⭐ **Excel文件处理**：使用标准库pandas和openpyxl，无需自定义辅助函数。读取：import pandas as pd; df = pd.read_excel('file.xlsx')。创建：from openpyxl import Workbook; ws['B2'] = '=SUM(A1:A10)'（公式优先，不要硬编码）。详细文档：backend/docs/skills/excel.md。可视化场景：⭐ **AQI日历图**：from app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id; img = generate_calendar_from_data_id(data_id='xxx', year=2026, month=3); print('CHART_SAVED:data:image/png;base64,' + img)。⭐ **极坐标污染玫瑰图**：from app.tools.visualization.polar_contour_generator import generate_pollution_rose_contour; img = generate_pollution_rose_contour(data_id='xxx', pollutant_name='PM10'); print('CHART_SAVED:data:image/png;base64,' + img)。参数: code(str), timeout(int, 可选, 默认30)",

    # === 任务管理 ===
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # === 模式互调 ===
    "call_sub_agent": "调用专家Agent（深度分析）或助手Agent（生成报告）。参数: target_mode(str), goal(str), context_str(str, 可选)",

    # === 规划工具 ===
    "complex_query_planner": "复杂查询计划工具（多数据源查询规划）。当需要同时查询多组数据、或不确定应使用哪个广东省查询工具时调用。⚠️ 必需参数: query_description(str, 详细描述查询需求，⚠️ 必须附上用户的查询输入原文，避免信息遗漏), mode(str, 固定为'query')",
}

# ===== 报告模式工具 =====
REPORT_TOOLS = {
    # 核心工具（⚠️ **Office工具使用前必须先阅读指导文档**：read_file(file_path='backend/app/tools/office/office_skills_guide.md')）
    "read_docx": "读取DOCX文档内容（直接读取，无需解包）。参数: path(str), max_paragraphs(int, 可选, 默认100), include_tables(bool, 可选, 默认true)",

    # 数据查询工具（直接调用，支持并发）
    "query_xcai_city_history": "查询全国城市历史空气质量数据（SQL Server XcAiDb数据库，支持773个城市）。⚠️ 必需参数: cities(list, 城市名称如'广州市'), data_type(str, hour=小时数据/day=日数据), start_time(str, 格式YYYY-MM-DD HH:MM:SS), end_time(str, 格式YYYY-MM-DD HH:MM:SS)。小时数据表2017年至今，日数据表2021年至今",
    "execute_sql_query": EXECUTE_SQL_QUERY_DESCRIPTION,
    "query_gd_suncere_city_day_new": "查询广东省城市日空气质量数据（新标准 HJ 633-2026）。参数: cities(list), start_date(str), end_date(str), data_type(int, 可选, 0原始实况/1审核实况默认/2原始标况/3审核标况)",
    "query_new_standard_report": "查询HJ 633-2026新标准空气质量统计报表（综合指数、超标天数、达标率）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true), use_old_composite_algorithm(bool, 可选, 默认false, 使用旧综合指数算法。false=新算法(PM2.5权重3,NO2权重2,O3权重2),true=旧算法(所有权重均为1))",
    "query_old_standard_report": "查询HJ 633-2013旧标准空气质量统计报表（综合指数、超标天数、达标率）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true), use_new_composite_algorithm(bool, 可选, 默认false, 使用新综合指数算法。false=旧算法(所有权重均为1),true=新算法(PM2.5权重3,NO2权重2,O3权重2))",
    "query_standard_comparison": "查询新旧空气质量标准对比（综合指数、超标天数、达标率）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true)",
    "compare_standard_reports": "新标准报表对比分析（对比两个时间段的综合指数、超标天数、达标率、六参数统计等全部指标）。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "compare_old_standard_reports": "旧标准报表对比分析（基于 HJ 633-2013 旧标准，对比两个时间段的综合指数、超标天数、达标率、六参数统计等全部指标）。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "query_station_new_standard_report": "站点级新标准统计报表查询（基于 HJ 633-2026，查询站点的综合指数、超标天数、达标率、六参数统计）。⚠️ 与城市工具的差异：不支持扣沙处理，使用station_name字段，支持城市名称自动展开为站点列表。⚠️ 必需参数: start_date(str), end_date(str)。可选: station_type(str, 站点类型, 默认'国控'。⚠️ 仅在使用cities参数时有效，用于过滤该城市下的指定类型站点。如果使用stations参数，则不需要此参数), cities(list, 城市名自动展开站点, 与stations至少提供一个。如果不提供station_type，默认查询国控站点), stations(list, 站点名称, 与cities至少提供一个。使用stations时不需要提供station_type), aggregate(bool, 是否计算多站点汇总, 默认false)",
    "compare_station_standard_reports": "站点级新标准报表对比分析（对比两个时间段的站点统计数据，返回差值和变化率）。⚠️ 站点级同比环比查询必须使用此工具，禁止手动计算。参数: query_period{start_date, end_date}, comparison_period{start_date, end_date}, cities(list, 可选, 城市名自动展开站点), stations(list, 可选, 站点名称), aggregate(bool, 可选, 是否计算多站点汇总对比, 默认false)",

    # 数据读取
    "read_data_registry": "读取已保存的数据。⚠️ **必须指定 time_range 参数（list_fields 模式除外）**，支持时间范围、字段选择。⚠️ 过滤后明细超过200条会拒绝返回完整data，请缩小time_range或减少fields。参数: data_id(str), time_range(str, **数据读取时必填**), list_fields(bool, 可选, 查看字段时使用), fields(可选, list)",

    # 文件操作
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。⚠️ **Excel文件（.xlsx/.xls/.xlsm）需要使用 execute_python 工具读取**（read_file会自动检测并提示）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "edit_file": "精确编辑文件（V2版本：支持引号规范化、Trailing空格处理、文件修改检查）。⚠️ 必须先使用read_file读取文件。参数: path(str), old_string(str, 要替换的原内容), new_string(str, 替换后的新内容), replace_all(bool, 可选, 是否替换所有匹配项, 默认false), encoding(str, 可选, 文件编码, 默认自动检测)",
    "grep": "搜索文件内容（支持 Glob 模式、分页、多行模式、上下文控制）。参数: pattern(str, 正则表达式), path(str, 可选, 相对于backend/), glob(str, 可选, 文件模式如*.{py,ts}), output_mode(str, 可选, content/files_with_matches/count), context_lines(int, 可选, 上下文行数), context_lines_before/context_lines_after(int, 可选), show_line_numbers(bool, 可选), multiline(bool, 可选, 多行模式), case_insensitive(bool, 可选), head_limit(int, 可选, 最多返回条数, 默认250), offset(int, 可选, 跳过前N条, 用于分页)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件名（glob模式，支持递归搜索）。⚠️ 参数: pattern(str, glob模式), path(str, 可选, 搜索路径, 默认当前目录)。重要：递归搜索子目录必须使用 **（如'**/*.json'），否则只在指定目录的顶层搜索。示例: search_files(pattern='**/*.json', path='backend/config') 递归搜索所有JSON文件; search_files(pattern='*.py', path='backend/app') 只在backend/app目录搜索Python文件",

    # 任务管理
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # 代码执行
    "execute_python": "执行 Python 代码（数值计算、文档生成、数据处理、可视化生成、Excel文件处理）。⭐ **Excel文件处理**：使用标准库pandas和openpyxl，无需自定义辅助函数。读取：import pandas as pd; df = pd.read_excel('file.xlsx')。创建：from openpyxl import Workbook; ws['B2'] = '=SUM(A1:A10)'（公式优先，不要硬编码）。详细文档：backend/docs/skills/excel.md。⭐ **AQI日历图**：from app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id; img = generate_calendar_from_data_id(data_id='xxx', year=2026, month=3); print('CHART_SAVED:data:image/png;base64,' + img)。⭐ **极坐标污染玫瑰图**：from app.tools.visualization.polar_contour_generator import generate_pollution_rose_contour; img = generate_pollution_rose_contour(data_id='xxx', pollutant_name='PM10'); print('CHART_SAVED:data:image/png;base64,' + img)。参数: code(str), timeout(int, 可选, 默认30)",

    # 模式互调
    "call_sub_agent": "调用问数模式查询数据。参数: target_mode(str), goal(str), context_str(str, 可选)",

    # 规划工具
    "complex_query_planner": "复杂查询计划工具（报告数据准备规划）。当需要同时准备多组查询数据、或不确定应使用哪个广东省查询工具时调用。⚠️ 必需参数: query_description(str, 详细描述查询需求，⚠️ 必须附上用户的查询输入原文，避免信息遗漏), mode(str, 固定为'report')",
}
CHART_TOOLS = {
    # 数据查询工具（广东省数据）
    "get_5min_data": "查询站点5分钟污染物浓度和气象数据（SQL Server air_quality_db数据库，表名格式Air_5m_{年份}_{站点代码}_Src）。⚠️ 必需参数: station(str, 站点名称或站点代码，如'广雅中学'或'1001A'), start_time(str, 开始时间ISO 8601格式'YYYY-MM-DDTHH:MM:SS'), end_time(str, 结束时间ISO 8601格式'YYYY-MM-DDTHH:MM:SS')。可选: pollutants(list, 污染物列表，如['PM2.5','O3','WS','WD'], 默认查询所有)。返回: 5分钟数据（宽表格式，包含PM2.5、PM10、SO2、NO2、O3、CO、风速WS、风向WD、温度TEMP、湿度RH、气压PRESSURE），支持生成风玫瑰图、时序图等高精度图表",
    "query_gd_suncere_city_hour": "查询广东省【城市级别】小时空气质量数据（⚠️ 仅支持城市名称，不支持站点名称。如果用户提到具体站点如'广雅中学'、'市监测站'等，必须使用 query_gd_suncere_station_hour_new 工具）。⚠️ 必需参数: cities(list, 城市名称列表, 如['广州','深圳','珠海'], 不支持站点名称), start_time(str, 开始时间'YYYY-MM-DD HH:MM:SS'), end_time(str, 结束时间'YYYY-MM-DD HH:MM:SS')。可选: include_weather(bool, 是否包含气象字段, 默认true, 包含风速/风向/温度/湿度/气压等)。返回: 城市级别PM2.5、PM10、SO2、NO2、CO、O3小时数据（多个站点的平均值）",
    "query_gd_suncere_station_hour_new": "查询广东省【站点级别】小时空气质量数据（⭐ 新标准 HJ 633-2026，自动计算新标准IAQI、AQI、首要污染物，支持气象字段提取）。⚠️ 适用场景：当用户提到具体站点名称（如'广雅中学'、'市监测站'、'天河职防'）或需要站点级别数据时使用。⚠️ 必需参数: start_time(str, 'YYYY-MM-DD HH:MM:SS'), end_time(str, 'YYYY-MM-DD HH:MM:SS')。可选: station_type(str, 站点类型, 默认'国控'。⚠️ 仅在使用cities参数时有效，用于过滤该城市下的指定类型站点。如果使用stations参数，则不需要此参数), cities(list, 城市名自动展开该城市下所有站点，与stations至少提供一个), stations(list, 站点名称如['广雅中学','市监测站'], 与cities至少提供一个。使用stations时不需要提供station_type), include_weather(bool, 是否包含气象字段, 默认true, 包含风速/风向/温度/湿度/气压等)。返回: 站点级别小时数据、新标准IAQI/AQI/首要污染物",
    "query_gd_suncere_city_day_new": "查询广东省【城市级别】日空气质量数据（新标准 HJ 633-2026，⚠️ 仅支持城市名称，不支持站点名称。如需站点日数据，请使用 query_gd_suncere_station_day_new）。⚠️ 必需参数: cities(list, 城市名称列表, 如['广州','深圳']), start_date(str, 开始日期'YYYY-MM-DD'), end_date(str, 结束日期'YYYY-MM-DD')。可选: data_type(int, 数据类型, 默认1=审核数据)。返回: 城市级别日均值、AQI、首要污染物、空气质量等级",

    # SQL Server通用查询（声环境数据等）
    "execute_sql_query": EXECUTE_SQL_QUERY_DESCRIPTION,

    # 知识库检索
    "knowledge_qa_workflow": "知识库检索入口。⚠️ 调用前应先把用户原问题改写成组合检索词：保留原始问题全文，并追加3-8个补充关键词/同义词/标准号不同写法/文件简称/英文缩写；不要只传抽象摘要。示例: 用户问'HJ 633-2026 综合指数怎么算'，query可写为'HJ 633-2026 综合指数怎么算 综合指数 计算方法 评价项目 分指数 IAQI AQI HJ633-2026 环境空气质量指数'。参数: query(str, 原问题+补充关键词的组合检索词), knowledge_base_ids(list, 可选, 指定知识库ID), top_k(int, 可选, 默认3, 最多10), reranker(str, 可选, auto/always/never, 默认auto)。返回sources和document_read_targets；严肃知识问答应继续调用knowledge_document_reader读取相邻chunks后再答。",
    "knowledge_document_reader": "读取知识库文档的chunk文本视图。适用：knowledge_qa_workflow返回document_read_targets后，按document_id+chunk_index读取相邻chunks或全文chunks，再回答严肃知识问答。参数: knowledge_base_id(str, 必需), document_id(str, 必需), chunk_index(int, 可选, 单个命中chunk索引), chunk_indices(list[int], 可选, 多个命中chunk索引), mode(str, 可选, neighbor_chunks/all_chunks, 默认neighbor_chunks), window(int, 可选, 相邻窗口, 默认2), max_chunks(int, 可选, 返回chunk上限, 默认30)",

    # 数据读取
    "read_data_registry": "读取已保存的数据结构。⚠️ **list_fields 必须为 true（必选）**——图表模式只需了解字段名称和类型，不需要获取具体数据内容；实际数据在 execute_python 中通过 data_id 对应的 JSON 文件路径自行读取。参数: data_id(str), list_fields(bool=true, 必选)",

    # 文件操作
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。⚠️ **Excel文件（.xlsx/.xls/.xlsm）需要使用 execute_python 工具读取**（read_file会自动检测并提示）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "edit_file": "精确编辑文件（V2版本：支持引号规范化、Trailing空格处理、文件修改检查）。⚠️ 必须先使用read_file读取文件。参数: path(str), old_string(str, 要替换的原内容), new_string(str, 替换后的新内容), replace_all(bool, 可选, 是否替换所有匹配项, 默认false), encoding(str, 可选, 文件编码, 默认自动检测)",
    "grep": "搜索文件内容（支持 Glob 模式、分页、多行模式、上下文控制）。参数: pattern(str, 正则表达式), path(str, 可选, 相对于backend/), glob(str, 可选, 文件模式如*.{py,ts}), output_mode(str, 可选, content/files_with_matches/count), context_lines(int, 可选, 上下文行数), context_lines_before/context_lines_after(int, 可选), show_line_numbers(bool, 可选), multiline(bool, 可选, 多行模式), case_insensitive(bool, 可选), head_limit(int, 可选, 最多返回条数, 默认250), offset(int, 可选, 跳过前N条, 用于分页)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件名（glob模式，支持递归搜索）。⚠️ 参数: pattern(str, glob模式), path(str, 可选, 搜索路径, 默认当前目录)。重要：递归搜索子目录必须使用 **（如'**/*.json'），否则只在指定目录的顶层搜索。示例: search_files(pattern='**/*.json', path='backend/config') 递归搜索所有JSON文件; search_files(pattern='*.py', path='backend/app') 只在backend/app目录搜索Python文件",
    "bash": "执行Shell命令（谨慎使用，用于删除/移动文件等操作）。参数: command(str), timeout(int, 可选, 默认60), working_dir(str, 可可选)",

    # 代码执行
    "execute_python": "执行 Python 代码（数值计算、生成 Matplotlib 图表、Excel文件处理）。⭐ **Excel文件处理**：使用标准库pandas和openpyxl，无需自定义辅助函数。读取：import pandas as pd; df = pd.read_excel('file.xlsx')。创建：from openpyxl import Workbook; ws['B2'] = '=SUM(A1:A10)'（公式优先，不要硬编码）。详细文档：backend/docs/skills/excel.md。⭐ **AQI日历图**：from app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id; img = generate_calendar_from_data_id(data_id='xxx', year=2026, month=3); print('CHART_SAVED:data:image/png;base64,' + img)。⭐ **极坐标污染玫瑰图**：from app.tools.visualization.polar_contour_generator import generate_pollution_rose_contour; img = generate_pollution_rose_contour(data_id='xxx', pollutant_name='PM10'); print('CHART_SAVED:data:image/png;base64,' + img)。参数: code(str), timeout(int, 可选, 默认30)",

    # 任务管理
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # 模式互调
    "call_sub_agent": "调用问数模式查询数据。参数: target_mode(str), goal(str), context_str(str, 可选)",
}

# ===== 社交模式工具（移动端助理） =====
SOCIAL_TOOLS = {
    # === 系统操作 ===
    "bash": "执行Shell命令（谨慎使用）。参数: command(str), timeout(int, 可选, 默认60), working_dir(str, 可选)",

    # === 文件操作 ===
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。⚠️ **Excel文件（.xlsx/.xls/.xlsm）需要使用 execute_python 工具读取**（read_file会自动检测并提示）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "edit_file": "精确编辑文件（V2版本：支持引号规范化、Trailing空格处理、文件修改检查）。⚠️ 必须先使用read_file读取文件。参数: path(str), old_string(str, 要替换的原内容), new_string(str, 替换后的新内容), replace_all(bool, 可选, 是否替换所有匹配项, 默认false), encoding(str, 可选, 文件编码, 默认自动检测)",
    "read_docx": "读取DOCX文档内容（直接读取，无需解包）。参数: path(str), max_paragraphs(int, 可选, 默认100), include_tables(bool, 可选, 默认true)",
    "parse_pdf": "解析PDF文件并提取内容（支持文本提取、OCR识别、表格提取、元数据提取）。⚠️ 必需参数: path(str, PDF文件路径)。可选: mode(str, 解析模式: auto=自动检测/text=文本提取/ocr=OCR识别/table=表格提取/image=图片信息/meta=元数据, 默认auto), pages(str, 页面范围如'1-5', 可选), extract_tables(bool, 是否提取表格, 默认false), extract_images(bool, 是否提取图片信息, 默认false), ocr_engine(str, OCR引擎: auto/qwen/paddleocr/tesseract, 默认auto)",
    "grep": "搜索文件内容（支持 Glob 模式、分页、多行模式、上下文控制）。参数: pattern(str, 正则表达式), path(str, 可选, 相对于backend/), glob(str, 可选, 文件模式如*.{py,ts}), output_mode(str, 可选, content/files_with_matches/count), context_lines(int, 可选, 上下文行数), context_lines_before/context_lines_after(int, 可选), show_line_numbers(bool, 可选), multiline(bool, 可选, 多行模式), case_insensitive(bool, 可选), head_limit(int, 可选, 最多返回条数, 默认250), offset(int, 可选, 跳过前N条, 用于分页)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件名（glob模式，支持递归搜索）。⚠️ 参数: pattern(str, glob模式), path(str, 可选, 搜索路径, 默认当前目录)。重要：递归搜索子目录必须使用 **（如'**/*.json'），否则只在指定目录的顶层搜索。示例: search_files(pattern='**/*.json', path='backend/config') 递归搜索所有JSON文件; search_files(pattern='*.py', path='backend/app') 只在backend/app目录搜索Python文件",
    "list_skills": "列出可用的技能文档（支持关键词过滤）。参数: keyword(str, 可选, 过滤关键词), category(str, 可选, 分类过滤)",

    # === 图片分析 ===
    "analyze_image": "分析图片内容。参数: path(str), operation(str, 可选, 默认analyze), prompt(str, 可选)",

    # === 知识库检索 ===
    "knowledge_qa_workflow": "知识库检索入口。⚠️ 调用前应先把用户原问题改写成组合检索词：保留原始问题全文，并追加3-8个补充关键词/同义词/标准号不同写法/文件简称/英文缩写；不要只传抽象摘要。参数: query(str, 原问题+补充关键词的组合检索词), knowledge_base_ids(list, 可选), top_k(int, 可选, 默认3), reranker(str, 可选, auto/always/never, 默认auto)。返回document_read_targets后，应调用knowledge_document_reader读取证据chunks。",
    "knowledge_document_reader": "读取知识库文档的chunk文本视图。适用：knowledge_qa_workflow返回document_read_targets后，按document_id+chunk_index读取相邻chunks或全文chunks，再回答严肃知识问答。参数: knowledge_base_id(str, 必需), document_id(str, 必需), chunk_index(int, 可选, 单个命中chunk索引), chunk_indices(list[int], 可选, 多个命中chunk索引), mode(str, 可选, neighbor_chunks/all_chunks, 默认neighbor_chunks), window(int, 可选, 相邻窗口, 默认2), max_chunks(int, 可选, 返回chunk上限, 默认30)",

    # === 记忆管理 ===
    "remember_fact": "记住重要事实到长期记忆（MEMORY.md）。使用时机：✅用户明确说'记住'、✅分享偏好、✅纠正错误、✅发现环境信息。❌不使用：临时信息、对话内容、不稳定事实。参数: fact(str, 要记住的事实), category(str, 类别: 用户偏好/领域知识/历史结论/环境信息), priority(int, 可选, 优先级1-5, 默认3)",
    "replace_memory": "替换MEMORY.md中的现有条目。使用时机：✅用户纠正错误信息、✅更新过时偏好、✅修正不准确结论。参数: old_text(str, 要替换的旧内容), new_text(str, 新的内容), category(str, 可选, 类别过滤)",
    "remove_memory": "从MEMORY.md删除过时或错误的条目。使用时机：✅删除临时环境信息、✅删除过时结论、✅删除错误记忆。参数: text(str, 要删除的内容), category(str, 可选, 类别过滤)",

    # === 数据查询 ===
    "query_gd_suncere_city_day_new": "查询广东省城市日空气质量数据（新标准 HJ 633-2026）。参数: cities(list), start_date(str), end_date(str), data_type(int, 可选, 0原始实况/1审核实况默认/2原始标况/3审核标况)",
    "query_new_standard_report": "查询HJ 633-2026新标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true), use_old_composite_algorithm(bool, 可选, 默认false, 使用旧综合指数算法。false=新算法(PM2.5权重3,NO2权重2,O3权重2),true=旧算法(所有权重均为1))",
    "compare_standard_reports": "新标准报表对比分析（对比两个时间段的综合指数、超标天数、达标率、六参数统计等全部指标）。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "compare_old_standard_reports": "旧标准报表对比分析（基于 HJ 633-2013 旧标准，对比两个时间段的综合指数、超标天数、达标率、六参数统计等全部指标）。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "get_weather_forecast": "查询天气预报（未来7-16天，支持获取今天和昨天数据，Open-Meteo API）。⚠️ 必需参数: lat(float), lon(float)。可选: location_name(str), forecast_days(int, 默认7), past_days(int, 默认0), hourly(bool, 默认true), daily(bool, 默认true)",

    # === 可视化 ===

    # === 代码执行 ===
    "execute_python": "执行 Python 代码（数值计算、数据处理、统计分析、可视化生成、Excel文件处理）。⭐ **Excel文件处理**：使用标准库pandas和openpyxl，无需自定义辅助函数。读取：import pandas as pd; df = pd.read_excel('file.xlsx')。创建：from openpyxl import Workbook; ws['B2'] = '=SUM(A1:A10)'（公式优先，不要硬编码）。详细文档：backend/docs/skills/excel.md。⭐ **AQI日历图**：from app.tools.visualization.generate_aqi_calendar.calendar_renderer import generate_calendar_from_data_id; img = generate_calendar_from_data_id(data_id='xxx', year=2026, month=3); print('CHART_SAVED:data:image/png;base64,' + img)。⭐ **极坐标污染玫瑰图**：from app.tools.visualization.polar_contour_generator import generate_pollution_rose_contour; img = generate_pollution_rose_contour(data_id='xxx', pollutant_name='PM10'); print('CHART_SAVED:data:image/png;base64,' + img)。参数: code(str), timeout(int, 可选, 默认30)",

    # === 模式互调 ===
    "call_sub_agent": "调用子Agent（code=编程, expert=数据分析, query=数据查询）。⚠️ 用自然语言描述任务，不要传递结构化参数或指定工具名称。参数: target_mode(str), goal(str), context_str(str, 可选)",

    # === 呼吸式特有工具 ===
    "schedule_task": "创建定时任务。参数: task_description(str), schedule(str, cron表达式), channels(list, 可选, 支持'weixin'|'qq')",
    "send_notification": "主动发送通知（支持文本、图片、文件，自动发送到当前对话的用户）。参数: message(str), media(list, 可选, 支持本地路径或URL)",
    "spawn": "⭐创建后台子Agent执行长时间任务（不阻塞主对话，完成后主动通知）。参数: task(str, 任务描述), label(str, 可选, 任务标签), timeout(int, 可选, 超时秒数, 默认3600, 范围60-86400), manual_mode(str, 可选, assistant/expert/query/code, 默认assistant)",

    # === 网络搜索 ===
    "web_search": "搜索互联网。参数: query(str), count(int, 可选, 默认5, 范围1-10)",
    "web_fetch": "抓取网页并提取可读内容。参数: url(str), maxChars(int, 可选, 默认10000)",


    # === 任务管理 ===
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",
}

# ===== 编程模式工具 =====
CODE_TOOLS = {
    # 文件操作
    "read_file": "读取文件（统一入口，支持文本/图片/PDF/DOCX）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "write_file": "写入文件。参数: path(str), content(str)",
    "edit_file": "编辑文件。参数: path(str), old_string(str), new_string(str)",
    "grep": "搜索文件内容（支持 Glob 模式、分页、多行模式、上下文控制）。参数: pattern(str, 正则表达式), path(str, 可选, 相对于backend/), glob(str, 可选, 文件模式如*.{py,ts}), output_mode(str, 可选, content/files_with_matches/count), context_lines(int, 可选, 上下文行数), context_lines_before/context_lines_after(int, 可选), show_line_numbers(bool, 可选), multiline(bool, 可选, 多行模式), case_insensitive(bool, 可选), head_limit(int, 可选, 最多返回条数, 默认250), offset(int, 可选, 跳过前N条, 用于分页)",
    "search_files": "搜索文件名（glob模式，支持递归搜索）。⚠️ 参数: pattern(str, glob模式), path(str, 可选, 搜索路径, 默认当前目录)。重要：递归搜索子目录必须使用 **（如'**/*.json'），否则只在指定目录的顶层搜索。示例: search_files(pattern='**/*.json', path='backend/config') 递归搜索所有JSON文件; search_files(pattern='*.py', path='backend/app') 只在backend/app目录搜索Python文件",
    "list_directory": "列出目录。参数: path(str)",

    # Shell命令
    "bash": "执行Shell命令。参数: command(str)",

    # 编程工具
    "validate_tool": "验证工具定义。参数: tool_path(str)",

    # 模式互调
    "call_sub_agent": "调用Agent。参数: target_mode(str), goal(str), context_str(str, 可选)",
}

# ===== 记忆整合器工具（后台专用） =====
MEMORY_CONSOLIDATOR_TOOLS = {
    "remember_fact": "添加重要事实到长期记忆。⚠️ **字符限制**：记忆文件上限3000字符，当前使用率会显示在提示词中。当接近上限（>80%）时，优先删除旧内容。参数：fact(str, 要记住的事实，简洁明确，一句话), category(str, 事实类别：用户偏好/领域知识/历史结论/环境信息), priority(int, 优先级1-5，5最高，默认3，用于记忆满时的删除决策)",
    "replace_memory": "替换现有记忆条目。⚠️ **字符限制**：替换操作不会改变总字符数，但可以提高记忆质量。参数：old_text(str, 要替换的旧内容，支持子串匹配), new_text(str, 新的内容), category(str, 可选，用于精确匹配，提高替换准确性)",
    "remove_memory": "删除过时或错误记忆。⚠️ **使用场景**：当记忆文件接近上限（>80%）或已满（100%）时使用。删除优先级：环境信息（临时）> 历史结论（可能过时）> 领域知识（相对稳定）> 用户偏好（最重要）。参数：text(str, 要删除的内容，支持子串匹配), category(str, 可选，用于精确匹配)",
}

# ===== 会商专用模式工具（仅专家会商内部使用） =====
DELIBERATION_METEOROLOGY_TOOLS = {
    "get_weather_forecast": EXPERT_TOOLS["get_weather_forecast"],
    "query_gd_suncere_city_hour": EXPERT_TOOLS["query_gd_suncere_city_hour"],
    "query_gd_suncere_station_hour_new": EXPERT_TOOLS["query_gd_suncere_station_hour_new"],
    "meteorological_trajectory_analysis": EXPERT_TOOLS["meteorological_trajectory_analysis"],
    "analyze_upwind_enterprises": EXPERT_TOOLS["analyze_upwind_enterprises"],
    "analyze_trajectory_sources": EXPERT_TOOLS["analyze_trajectory_sources"],
    "read_data_registry": EXPERT_TOOLS["read_data_registry"],
    "TodoWrite": EXPERT_TOOLS["TodoWrite"],
}

DELIBERATION_CHEMISTRY_TOOLS = {
    "get_vocs_data": EXPERT_TOOLS["get_vocs_data"],
    "get_pm25_ionic": EXPERT_TOOLS["get_pm25_ionic"],
    "get_pm25_carbon": EXPERT_TOOLS["get_pm25_carbon"],
    "get_pm25_crustal": EXPERT_TOOLS["get_pm25_crustal"],
    "calculate_pm_pmf": EXPERT_TOOLS["calculate_pm_pmf"],
    "calculate_vocs_pmf": EXPERT_TOOLS["calculate_vocs_pmf"],
    "calculate_pmf": EXPERT_TOOLS["calculate_pmf"],
    "calculate_obm_ofp": EXPERT_TOOLS["calculate_obm_ofp"],
    "calculate_reconstruction": EXPERT_TOOLS["calculate_reconstruction"],
    "calculate_carbon": EXPERT_TOOLS["calculate_carbon"],
    "calculate_soluble": EXPERT_TOOLS["calculate_soluble"],
    "calculate_crustal": EXPERT_TOOLS["calculate_crustal"],
    "read_data_registry": EXPERT_TOOLS["read_data_registry"],
    "TodoWrite": EXPERT_TOOLS["TodoWrite"],
}

DELIBERATION_REVIEWER_TOOLS = {
    "read_data_registry": EXPERT_TOOLS["read_data_registry"],
    "TodoWrite": EXPERT_TOOLS["TodoWrite"],
}

# ===== 工具排序（影响展示顺序） =====
ASSISTANT_TOOL_ORDER = [
    "bash", "read_file", "edit_file", "grep", "write_file", "list_directory", "search_files",
    "list_skills",  # 技能管理工具
    "read_docx",  # 读取DOCX文档（优先使用）
    "parse_pdf",  # 解析PDF文件
    "unpack_office", "pack_office", "word_edit", "accept_word_changes",
    "recalc_excel", "add_ppt_slide",
    "TodoWrite",  # 任务管理工具
    "execute_python",  # 数值计算工具
    "create_scheduled_task", "analyze_image",
    "browser",  # 浏览器自动化工具
    "call_sub_agent",  # 调用专家Agent
]

EXPERT_TOOL_ORDER = [
    # 查询工具
    "get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_forecast",

    # 广东省结构化查询工具
    "query_gd_suncere_city_hour",
    "query_gd_suncere_station_hour_new",
    "query_gd_suncere_station_day_new",
    "query_gd_suncere_city_day", "query_gd_suncere_city_day_new",
    "query_new_standard_report", "query_old_standard_report",
    "query_standard_comparison", "compare_standard_reports",
    "query_xcai_city_history",  # 全国城市历史数据（XcAiDb SQL Server）
    "execute_sql_query",  # 通用SQL执行工具（支持统计表和噪声达标率表）
    "read_data_registry",

    # 分析工具
    "calculate_pm_pmf", "calculate_vocs_pmf", "calculate_pmf",
    "calculate_obm_ofp",
    "analyze_upwind_enterprises", "meteorological_trajectory_analysis", "analyze_trajectory_sources",
    "calculate_reconstruction", "calculate_carbon", "calculate_soluble", "calculate_crustal", "calculate_trace",
    "predict_air_quality",

    # 可视化
    "revise_chart", "generate_map",

    # 任务管理
    "TodoWrite",  # 任务管理工具

    # 代码执行
    "execute_python",  # 数值计算工具

    # 文件操作
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",

    # 调用助手Agent
    "call_sub_agent",

    # 完成
    "FINISH_SUMMARY"
]

CODE_TOOL_ORDER = [
    # 浏览
    "list_directory", "search_files", "read_file",

    # 搜索
    "grep", "search_files",

    # 编辑
    "write_file", "edit_file",

    # 执行
    "bash", "validate_tool",

    # 模式互调
    "call_sub_agent"
]

QUERY_TOOL_ORDER = [
    # 规划工具（复杂查询时优先考虑）
    "complex_query_planner",

    # 系统操作
    "bash",

    # 源码查看工具
    "grep", "read_file", "write_file", "edit_file", "list_directory", "search_files",

    # 参数化查询工具
    "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_forecast",
    "query_xcai_city_history",
    "execute_sql_query",  # 通用SQL执行工具
    "query_gd_suncere_city_hour", "query_gd_suncere_station_hour_new", "query_gd_suncere_station_day_new", "query_gd_suncere_city_day", "query_gd_suncere_city_day_new", "query_gd_suncere_regional_comparison",
    "query_new_standard_report",  # 新标准统计报表
    "query_old_standard_report",  # 旧标准统计报表
    "query_standard_comparison",  # 新旧标准对比
    "compare_standard_reports",  # 新标准报表对比分析
    "compare_old_standard_reports",  # 旧标准报表对比分析
    "query_station_new_standard_report",  # 站点级新标准统计报表
    "compare_station_standard_reports",  # 站点级新标准报表对比分析
    "query_national_province_air_quality",  # 全国省份空气质量查询
    "query_national_city_air_quality",  # 全国城市空气质量查询

    # 知识库检索（预报会商场景）
    "knowledge_qa_workflow",
    "knowledge_document_reader",

    # 可视化工具

    # 数值计算工具
    "execute_python",

    # 数据注册表
    "read_data_registry",

    # 任务管理
    "TodoWrite",

    # 模式互调
    "call_sub_agent",
]

# ===== 报告模式工具排序 =====
REPORT_TOOL_ORDER = [
    # 规划工具（复杂数据准备时优先考虑）
    "complex_query_planner",

    # 核心工具
    "read_docx",

    # 数据查询工具（支持并发）
    "query_gd_suncere_city_hour",
    "query_gd_suncere_city_day_new",
    "query_new_standard_report",  # 新标准统计报表
    "query_old_standard_report",  # 旧标准统计报表
    "query_standard_comparison",
    "compare_standard_reports",  # 新标准报表对比分析
    "compare_old_standard_reports",  # 旧标准报表对比分析
    "query_station_new_standard_report",  # 站点级新标准统计报表
    "compare_station_standard_reports",  # 站点级新标准报表对比分析
    "query_xcai_city_history",  # 全国城市历史数据（XcAiDb SQL Server）
    "execute_sql_query",  # 通用SQL执行工具（支持统计表和噪声达标率表）

    # 数据读取
    "read_data_registry",

    # 文件操作
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",

    # 任务管理
    "TodoWrite",

    # 代码执行
    "execute_python",

    # 模式互调
    "call_sub_agent",
]

# ===== 图表模式工具排序 =====
CHART_TOOL_ORDER = [
    # 数据查询工具（广东省数据）
    "get_5min_data",  # 5分钟数据查询（高精度数据，支持风玫瑰图等）
    "query_gd_suncere_city_hour",
    "query_gd_suncere_station_hour_new",
    "query_gd_suncere_city_day_new",
    "query_new_standard_report",
    "query_old_standard_report",
    "compare_standard_reports",

    # SQL Server通用查询（声环境数据等）
    "execute_sql_query",

    # 知识库检索
    "knowledge_qa_workflow",
    "knowledge_document_reader",

    # 数据读取
    "read_data_registry",

    # 文件操作
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files", "bash",

    # 代码执行
    "execute_python",

    # 任务管理
    "TodoWrite",

    # 模式互调
    "call_sub_agent",
]

# ===== 社交模式工具排序 =====
SOCIAL_TOOL_ORDER = [
    # 系统操作
    "bash",  # 执行Shell命令

    # 文件操作
    "read_file",
    "edit_file",  # 编辑文件
    "read_docx",
    "parse_pdf",  # 解析PDF文件
    "grep",
    "write_file",
    "list_directory",
    "search_files",
    "list_skills",  # 技能管理工具

    # 图片分析
    "analyze_image",

    # 数据查询
    "query_gd_suncere_city_day_new",
    "query_new_standard_report",
    "compare_standard_reports",
    "get_weather_forecast",

    # 可视化

    # 代码执行
    "execute_python",

    # 知识库检索
    "knowledge_qa_workflow",
    "knowledge_document_reader",

    # 呼吸式特有工具
    "schedule_task",
    "send_notification",
    "spawn",  # ⭐ 后台任务工具

    # 网络搜索
    "web_search",
    "web_fetch",


    # 任务管理
    "TodoWrite",

    # 模式互调
    "call_sub_agent",
]

DELIBERATION_METEOROLOGY_TOOL_ORDER = [
    "get_weather_forecast",
    "query_gd_suncere_city_hour",
    "query_gd_suncere_station_hour_new",
    "meteorological_trajectory_analysis",
    "analyze_upwind_enterprises",
    "analyze_trajectory_sources",
    "read_data_registry",
    "TodoWrite",
]

DELIBERATION_CHEMISTRY_TOOL_ORDER = [
    "get_vocs_data",
    "get_pm25_ionic",
    "get_pm25_carbon",
    "get_pm25_crustal",
    "calculate_pm_pmf",
    "calculate_vocs_pmf",
    "calculate_pmf",
    "calculate_obm_ofp",
    "calculate_reconstruction",
    "calculate_carbon",
    "calculate_soluble",
    "calculate_crustal",
    "read_data_registry",
    "TodoWrite",
]

DELIBERATION_REVIEWER_TOOL_ORDER = [
    "read_data_registry",
    "TodoWrite",
]


def get_tools_by_mode(mode: str) -> Dict[str, str]:
    """
    根据模式获取工具列表

    Args:
        mode: "assistant" | "expert" | "code" | "query" | "report" | "social" | "chart" | "memory_consolidator"

    Returns:
        工具字典 {tool_name: description}
    """
    if mode == "assistant":
        return ASSISTANT_TOOLS
    elif mode == "expert":
        return EXPERT_TOOLS
    elif mode == "code":
        return CODE_TOOLS
    elif mode == "query":
        return QUERY_TOOLS
    elif mode == "report":
        return REPORT_TOOLS
    elif mode == "social":
        return SOCIAL_TOOLS
    elif mode == "chart":
        return CHART_TOOLS
    elif mode == "memory_consolidator":
        return MEMORY_CONSOLIDATOR_TOOLS
    elif mode == "deliberation_meteorology":
        return DELIBERATION_METEOROLOGY_TOOLS
    elif mode == "deliberation_chemistry":
        return DELIBERATION_CHEMISTRY_TOOLS
    elif mode == "deliberation_reviewer":
        return DELIBERATION_REVIEWER_TOOLS
    else:
        raise ValueError(f"Unknown mode: {mode}")


def get_tool_order(mode: str) -> List[str]:
    """
    根据模式获取工具排序

    Args:
        mode: "assistant" | "expert" | "code" | "query" | "report" | "social" | "chart" | "memory_consolidator"

    Returns:
        工具名称列表（按展示顺序）
    """
    if mode == "assistant":
        return ASSISTANT_TOOL_ORDER
    elif mode == "expert":
        return EXPERT_TOOL_ORDER
    elif mode == "code":
        return CODE_TOOL_ORDER
    elif mode == "query":
        return QUERY_TOOL_ORDER
    elif mode == "report":
        return REPORT_TOOL_ORDER
    elif mode == "social":
        return SOCIAL_TOOL_ORDER
    elif mode == "chart":
        return CHART_TOOL_ORDER
    elif mode == "memory_consolidator":
        return ["remember_fact", "replace_memory", "remove_memory"]
    elif mode == "deliberation_meteorology":
        return DELIBERATION_METEOROLOGY_TOOL_ORDER
    elif mode == "deliberation_chemistry":
        return DELIBERATION_CHEMISTRY_TOOL_ORDER
    elif mode == "deliberation_reviewer":
        return DELIBERATION_REVIEWER_TOOL_ORDER
    else:
        raise ValueError(f"Unknown mode: {mode}")

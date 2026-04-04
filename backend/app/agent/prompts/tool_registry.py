"""
工具注册表

定义六种Agent模式的工具列表和排序

⚠️ 注意：保留现有的query模式（WEB端问数模式），新增social模式（移动端呼吸式Agent）
"""

from typing import Dict, List

# ===== 助手模式工具 =====
ASSISTANT_TOOLS = {
    # Shell命令
    "bash": "执行Shell命令。参数: command(str)",

    # 文件操作
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "edit_file": "精确编辑文件（字符串替换）。参数: path(str), old_string(str), new_string(str)",
    "grep": "搜索文件内容。参数: pattern(str), path(str)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件（glob模式）。参数: pattern(str)",

    # Office工具（复杂工具，必须先阅读 office_skills_guide.md）
    "read_docx": "读取DOCX文档内容（直接读取，无需解包）。参数: path(str), max_paragraphs(int, 可选, 默认100), include_tables(bool, 可选, 默认true)",
    "parse_pdf": "解析PDF文件并提取内容（支持文本提取、OCR识别、表格提取、元数据提取）。⚠️ 必需参数: path(str, PDF文件路径)。可选: mode(str, 解析模式: auto=自动检测/text=文本提取/ocr=OCR识别/table=表格提取/image=图片信息/meta=元数据, 默认auto), pages(str, 页面范围如'1-5', 可选), extract_tables(bool, 是否提取表格, 默认false), extract_images(bool, 是否提取图片信息, 默认false), ocr_engine(str, OCR引擎: auto/qwen/paddleocr/tesseract, 默认auto)",
    "unpack_office": "解包Office文件为XML（Word/Excel/PPT）。参数: path(str), output_dir(str, 可选)",
    "pack_office": "打包XML为Office文件。参数: input_dir(str), output_path(str)",
    "word_edit": "Word高级编辑（替换文本、插入内容）。参数: docx_path(str), edits(list)",
    "accept_word_changes": "接受Word文档的所有修订。参数: docx_path(str), output_path(str, 可选)",
    "find_replace_word": "Word文档查找替换。参数: docx_path(str), find(str), replace(str)",
    "recalc_excel": "Excel公式重算。参数: xlsx_path(str), output_path(str, 可选)",
    "add_ppt_slide": "PPT添加幻灯片。参数: pptx_path(str), slide_content(dict)",

    # 任务管理
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # 代码执行
    "execute_python": "执行 Python 代码（数值计算、数据处理、文件操作）。参数: code(str), timeout(int, 可选, 默认30)",

    # 其他工具
    "create_scheduled_task": "创建定时任务。参数: user_request(str)",
    "analyze_image": "分析图片内容。参数: path(str), operation(str, 可选, 默认analyze), prompt(str, 可选)",
    "browser": "浏览器自动化。[必须先阅读browser_skills_guide.md]",
    "call_sub_agent": "调用专家Agent。参数: target_mode(str), task_description(str)",
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
    "query_gd_suncere_city_day": "查询广东省城市日空气质量数据（旧标准，返回每日六参数、AQI、首要污染物）。参数: cities(list), start_date(str), end_date(str)",
    "query_gd_suncere_city_day_new": "查询广东省城市日空气质量数据（新标准 HJ 633-2024，返回每日六参数、AQI、首要污染物）。参数: cities(list), start_date(str), end_date(str)",
    "query_gd_suncere_station_hour_new": "查询广东省站点级别小时空气质量数据（⭐ 新标准 HJ 633-2024，自动计算新标准IAQI、AQI、首要污染物，三天内原始数据，三天前审核数据）。参数: start_time(str, 'YYYY-MM-DD HH:MM:SS'), end_time(str, 'YYYY-MM-DD HH:MM:SS'), cities(list, 可选, 城市名自动展开站点), stations(list, 可选, 站点名称如['广雅中学','市监测站'])",
    "query_gd_suncere_station_day_new": "查询广东省站点级别日空气质量数据（⭐ 新标准 HJ 633-2024，自动计算新标准IAQI、AQI、首要污染物，三天内原始数据，三天前审核数据）。参数: start_date(str, 'YYYY-MM-DD'), end_date(str, 'YYYY-MM-DD'), cities(list, 可选, 城市名自动展开站点), stations(list, 可选, 站点名称如['广雅中学','市监测站'])",
    "query_new_standard_report": "【第一优先级】查询HJ 633-2024新标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。⚠️ 优先使用此工具获取统计结果，不要手动计算。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理)",
    "query_old_standard_report": "【第一优先级】查询HJ 633-2011旧标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。⚠️ 优先使用此工具获取统计结果，不要手动计算。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理)",
    "query_standard_comparison": "【第一优先级】新旧标准对比统计查询（返回综合指数、超标天数、达标率等统计指标）。⚠️ 优先使用此工具获取统计结果，不要手动计算。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理)",
    "compare_standard_reports": "【第一优先级】新标准报表对比分析（对比两个时间段的综合指数、超标天数、达标率、六参数统计、单项质量指数、首要污染物统计等全部指标）。⚠️ 同比环比查询必须使用此工具，禁止手动计算。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "read_data_registry": "读取已保存的数据。⚠️ **必须指定 time_range 参数（list_fields 模式除外）**，支持时间范围、字段选择、jq聚合。参数: data_id(str), time_range(str, **数据读取时必填**), list_fields(bool, 可选, 查看字段时使用), fields(可选, list), jq_filter(可选, str, ⚠️ **聚合操作返回标量值**：length/max/min/add 返回数字，不是数组)",
    "aggregate_data": "【第二优先级】数据聚合分析工具（⚠️ 仅当统计查询工具无法满足需求时使用。前置条件：必须先使用查询工具获取data_id。使用前请先阅读使用指南：read_file(file_path='backend/app/tools/analysis/aggregate_data/aggregate_data_guide.md')）",

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
    "generate_chart": "生成标准图表（15种类型：pie/bar/line/timeseries/wind_rose/profile/scatter3d/surface3d/heatmap/radar/map等）。⚠️ 必需参数: chart_type(str), data(list或dict)。可选: title(str), x_field(str), y_field(str), meta(dict)",
    "smart_chart_generator": "智能图表生成（自动选择图表类型和数据可视化）。⚠️ 必需参数: data_id(str, 数据ID)",
    "revise_chart": "修订已生成图表（基于用户反馈调整图表）。⚠️ 必需参数: chart_id(str), revision_instruction(str, 修订说明)",
    "generate_map": "生成地图可视化（高德地图，展示站点位置和污染分布）。⚠️ 必需参数: locations(list, 站点列表, 每个站点包含lat/lon)。可选: map_type(str, 地图类型: scatter/heatmap/bubble, 默认scatter), center_lat/center_lon(float, 地图中心), zoom(int, 缩放级别, 默认10)",

    # 任务管理
    "TodoWrite": "更新任务清单（完整替换）。⚠️ 溯源分析任务必须使用: TodoWrite(task_list_file='backend/config/task_lists/quick_trace_standard_multi_agent.md')，不要手动输入items（会丢失详细信息）",

    # 代码执行
    "execute_python": "执行 Python 代码（数值计算、数据处理、统计分析）。参数: code(str), timeout(int, 可选, 默认30)",

    # 文件操作（保存分析结果、读取配置文件）
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "edit_file": "精确编辑文件（字符串替换）。参数: path(str), old_string(str), new_string(str)",
    "grep": "搜索文件内容。参数: pattern(str), path(str)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件（glob模式）。参数: pattern(str)",

    # 其他
    "call_sub_agent": "调用助手Agent。参数: target_mode(str), task_description(str)",
    "FINISH_SUMMARY": "生成分析报告。参数: answer(str)",
}

# ===== 问数模式工具 =====
QUERY_TOOLS = {
    # === 源码查看工具（了解工具实现细节） ===
    "grep": "搜索文件内容。参数: pattern(str), path(str)",
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "edit_file": "精确编辑文件（字符串替换）。参数: path(str), old_string(str), new_string(str)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件（glob模式）。参数: pattern(str)",

    # === 现有参数化查询工具（复用） ===
    "get_pm25_ionic": "查询PM2.5水溶性离子。参数: start_time(str), end_time(str), locations(可选)",
    "get_pm25_carbon": "查询PM2.5碳组分。参数: start_time(str), end_time(str), locations(可选)",
    "get_pm25_crustal": "查询PM2.5地壳元素。参数: start_time(str), end_time(str), locations(可选)",
    "get_weather_forecast": "查询天气预报（未来7-16天，支持获取今天和昨天数据，Open-Meteo API）。⚠️ 必需参数: lat(float), lon(float)。可选: location_name(str), forecast_days(int, 默认7), past_days(int, 默认0), hourly(bool, 默认true), daily(bool, 默认true)",
    "query_xcai_city_history": "查询全国城市历史空气质量数据（SQL Server XcAiDb数据库，支持773个城市）。⚠️ 必需参数: cities(list, 城市名称如'广州市'), data_type(str, hour=小时数据/day=日数据), start_time(str, 格式YYYY-MM-DD HH:MM:SS), end_time(str, 格式YYYY-MM-DD HH:MM:SS)。小时数据表2017年至今，日数据表2021年至今",
    "execute_sql_query": "通用SQL执行工具，支持查看表结构和执行SQL查询（二选一）。⚠️ 查看表结构：describe_table(str, 输入目标表名如'qc_history'或'working_orders'，动态从数据库获取表结构)。执行查询：sql(str, SQL查询语句)。⚠️ 中文查询注意事项：SQL Server 查询中文字符串必须使用 N 前缀，如 WHERE StationName LIKE N'%增城派潭%'（错误写法：LIKE '%增城派潭%'）。建议优先使用 StationCode（站点编码）查询。可选：limit(int, 返回记录数限制, 默认1000, 最大10000)。可用表：qc_history(自动质控历史)、working_orders(运维工单)",
    "query_gd_suncere_city_hour": "查询广东省城市小时空气质量数据（支持多城市并发查询）。参数: cities(list), start_time(str, 'YYYY-MM-DD HH:MM:SS'), end_time(str, 'YYYY-MM-DD HH:MM:SS')",
    "query_gd_suncere_station_hour_new": "查询广东省站点级别小时空气质量数据（⭐ 新标准 HJ 633-2024，自动计算新标准IAQI、AQI、首要污染物，三天内原始数据，三天前审核数据）。参数: start_time(str, 'YYYY-MM-DD HH:MM:SS'), end_time(str, 'YYYY-MM-DD HH:MM:SS'), cities(list, 可选, 城市名自动展开站点), stations(list, 可选, 站点名称如['广雅中学','市监测站'])。cities和stations至少提供一个，可组合使用",
    "query_gd_suncere_station_day_new": "查询广东省站点级别日空气质量数据（⭐ 新标准 HJ 633-2024，自动计算新标准IAQI、AQI、首要污染物，三天内原始数据，三天前审核数据）。参数: start_date(str, 'YYYY-MM-DD'), end_date(str, 'YYYY-MM-DD'), cities(list, 可选, 城市名自动展开站点), stations(list, 可选, 站点名称如['广雅中学','市监测站'])。cities和stations至少提供一个，可组合使用",
    "query_gd_suncere_city_day": "查询广东省城市日空气质量数据（旧标准，返回每日六参数、AQI、首要污染物）。参数: cities(list), start_date(str), end_date(str)",
    "query_gd_suncere_city_day_new": "查询广东省城市日空气质量数据（新标准 HJ 633-2024，返回每日六参数、AQI、首要污染物）。参数: cities(list), start_date(str), end_date(str)",
    "query_gd_suncere_regional_comparison": "查询广东省区域对比空气质量数据（目标城市与周边城市对比，用于区域传输分析）。参数: target_city(str), nearby_cities(list), start_time(str, 'YYYY-MM-DD HH:MM:SS'), end_time(str, 'YYYY-MM-DD HH:MM:SS')",
    "query_gd_suncere_report": "查询广东省综合统计报表（支持周报/月报/季报/年报/任意时间，含AQI、综合指数、污染物浓度统计）。参数: cities(list), start_time(str, 'YYYY-MM-DD HH:MM:SS'), end_time(str, 'YYYY-MM-DD HH:MM:SS'), time_type(int, 可选, 3=周报/4=月报/5=季报/7=年报/8=任意时间, 默认8), area_type(int, 可选, 0=站点/1=区县/2=城市, 默认2)",
    "query_gd_suncere_report_compare": "查询广东省对比分析报表（两个时间段对比，支持月报和任意时间对比）。参数: cities(list), time_point(list, 当前时间范围['start', 'end']), contrast_time(list, 对比时间范围['start', 'end']), time_type(int, 可选, 4=月报/8=任意时间, 默认8), area_type(int, 可选, 0=站点/1=区县/2=城市, 默认2)",
    "query_new_standard_report": "查询HJ 633-2024新标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理)",
    "query_old_standard_report": "查询HJ 633-2011旧标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理)",
    "query_standard_comparison": "新旧标准对比统计查询（返回综合指数、超标天数、达标率等统计指标）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理)",
    "compare_standard_reports": "新标准报表对比分析（对比两个时间段的综合指数、超标天数、达标率、六参数统计、单项质量指数、首要污染物统计等全部指标）。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "query_station_new_standard_report": "站点级新标准统计报表查询（基于 HJ 633-2024，查询站点的综合指数、超标天数、达标率、六参数统计）。⚠️ 与城市工具的差异：不支持扣沙处理，使用station_name字段，支持城市名称自动展开为站点列表。参数: start_date(str), end_date(str), cities(list, 可选, 城市名自动展开站点), stations(list, 可选, 站点名称), aggregate(bool, 可选, 是否计算多站点汇总, 默认false)",
    "compare_station_standard_reports": "站点级新标准报表对比分析（对比两个时间段的站点统计数据，返回差值和变化率）。⚠️ 站点级同比环比查询必须使用此工具，禁止手动计算。参数: query_period{start_date, end_date}, comparison_period{start_date, end_date}, cities(list, 可选, 城市名自动展开站点), stations(list, 可选, 站点名称), aggregate(bool, 可选, 是否计算多站点汇总对比, 默认false)",

     # === 新增：数据注册表工具 ===
    "read_data_registry": "读取已保存的数据。⚠️ **必须指定 time_range 参数（list_fields 模式除外）**，支持时间范围、字段选择、jq聚合。参数: data_id(str), time_range(str, **数据读取时必填**), list_fields(bool, 可选, 查看字段时使用), fields(可选, list), jq_filter(可选, str, ⚠️ **聚合操作返回标量值**：length/max/min/add 返回数字，不是数组)",

    # === 数据分析工具 ===
    "aggregate_data": "数据聚合分析工具（使用前请先阅读使用指南：read_file(file_path='backend/app/tools/analysis/aggregate_data/aggregate_data_guide.md')）",

    # === 知识库检索（预报会商场景） ===
    "search_knowledge_base": "检索会商记录、模型参数、历史案例等知识库内容。参数: query(str), knowledge_base_ids(list, 可选, 指定会商知识库ID), top_k(int, 可选, 默认5), score_threshold(float, 可选, 默认0.5), filters(dict, 可选, 元数据过滤), use_reranker(bool, 可选, 默认true)",

    # === 可视化工具 ===
    "generate_aqi_calendar": "生成AQI日历热力图（需先使用query_new_standard_report等查询工具获取数据并得到data_id）。参数: data_id(str), year(int), month(int), pollutant(str, 可选, 默认AQI, 支持AQI/SO2/NO2/CO/O3_8h/PM2_5/PM10), cities(list, 可选, 默认广东省21个城市)",
    "generate_chart": "生成标准图表（15种类型：pie/bar/line/timeseries/wind_rose/profile/scatter3d/surface3d/heatmap/radar/map等）。参数: chart_type(str), data(list或dict) [其他参数详见工具文档]",
    "smart_chart_generator": "智能图表生成（需data_id，自动选择图表类型）。参数: data_id(str)",

    # === 数值计算工具 ===
    "execute_python": "【第三优先级】执行 Python 代码进行数值计算（均值、中位数、百分比、单位换算等）。⚠️ **最后手段：仅当统计查询工具和aggregate_data都无法满足需求时才使用**。禁止用于同环比、超标率等常见统计计算（应使用compare_standard_reports或query_new_standard_report）。❌ **禁止用来校验统计查询工具返回的结果，统计查询工具的结果是最准确的**。参数: code(str), timeout(int, 可选, 默认30)",

    # === 任务管理 ===
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # === 模式互调 ===
    "call_sub_agent": "调用专家Agent（深度分析）或助手Agent（生成报告）。参数: target_mode(str), task_description(str)",

    # === 规划工具 ===
    "complex_query_planner": "复杂查询计划工具（多数据源查询规划）。当需要同时查询多组数据、或不确定应使用哪个广东省查询工具时调用。⚠️ 必需参数: query_description(str, 详细描述查询需求), mode(str, 固定为'query')",
}

# ===== 报告模式工具 =====
REPORT_TOOLS = {
    # 核心工具
    "read_docx": "读取DOCX文档内容（直接读取，无需解包）。参数: path(str), max_paragraphs(int, 可选, 默认100), include_tables(bool, 可选, 默认true)",

    # 数据查询工具（直接调用，支持并发）
    "query_xcai_city_history": "查询全国城市历史空气质量数据（SQL Server XcAiDb数据库，支持773个城市）。⚠️ 必需参数: cities(list, 城市名称如'广州市'), data_type(str, hour=小时数据/day=日数据), start_time(str, 格式YYYY-MM-DD HH:MM:SS), end_time(str, 格式YYYY-MM-DD HH:MM:SS)。小时数据表2017年至今，日数据表2021年至今",
    "query_gd_suncere_city_day_new": "查询广东省城市日空气质量数据（新标准 HJ 633-2024）。参数: cities(list), start_date(str), end_date(str), data_type(int, 可选)",
    "query_new_standard_report": "查询HJ 633-2024新标准空气质量统计报表（综合指数、超标天数、达标率）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true)",
    "query_old_standard_report": "查询HJ 633-2011旧标准空气质量统计报表（综合指数、超标天数、达标率）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true)",
    "query_standard_comparison": "查询新旧空气质量标准对比（综合指数、超标天数、达标率）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true)",
    "compare_standard_reports": "新标准报表对比分析（对比两个时间段的综合指数、超标天数、达标率、六参数统计等全部指标）。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "query_station_new_standard_report": "站点级新标准统计报表查询（基于 HJ 633-2024，查询站点的综合指数、超标天数、达标率、六参数统计）。⚠️ 与城市工具的差异：不支持扣沙处理，使用station_name字段，支持城市名称自动展开为站点列表。参数: start_date(str), end_date(str), cities(list, 可选, 城市名自动展开站点), stations(list, 可选, 站点名称), aggregate(bool, 可选, 是否计算多站点汇总, 默认false)",
    "compare_station_standard_reports": "站点级新标准报表对比分析（对比两个时间段的站点统计数据，返回差值和变化率）。⚠️ 站点级同比环比查询必须使用此工具，禁止手动计算。参数: query_period{start_date, end_date}, comparison_period{start_date, end_date}, cities(list, 可选, 城市名自动展开站点), stations(list, 可选, 站点名称), aggregate(bool, 可选, 是否计算多站点汇总对比, 默认false)",

    # 数据读取
    "read_data_registry": "读取已保存的数据。⚠️ **必须指定 time_range 参数（list_fields 模式除外）**，支持时间范围、字段选择。参数: data_id(str), time_range(str, **数据读取时必填**), list_fields(bool, 可选, 查看字段时使用), fields(可选, list)",

    # 文件操作
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "edit_file": "精确编辑文件（字符串替换）。参数: path(str), old_string(str), new_string(str)",
    "grep": "搜索文件内容。参数: pattern(str), path(str)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件（glob模式）。参数: pattern(str)",

    # 任务管理
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # 代码执行
    "execute_python": "执行 Python 代码（数值计算、文档生成、数据处理、可视化）。参数: code(str), timeout(int, 可选, 默认30)",

    # 模式互调
    "call_sub_agent": "调用问数模式查询数据。参数: target_mode(str), task_description(str)",

    # 规划工具
    "complex_query_planner": "复杂查询计划工具（报告数据准备规划）。当需要同时准备多组查询数据、或不确定应使用哪个广东省查询工具时调用。⚠️ 必需参数: query_description(str, 详细描述查询需求), mode(str, 固定为'report')",
}
CHART_TOOLS = {
    # 数据查询工具（广东省数据）
    "query_gd_suncere_city_hour": "查询广东省城市小时空气质量数据（小时级别污染物数据）。⚠️ 必需参数: cities(list, 城市名称列表, 如['广州','深圳']), start_time(str, 开始时间'YYYY-MM-DD HH:MM:SS'), end_time(str, 结束时间'YYYY-MM-DD HH:MM:SS')。返回: PM2.5、PM10、SO2、NO2、CO、O3小时数据, 支持多城市并发查询",
    "query_gd_suncere_city_day_new": "查询广东省城市日空气质量数据（新标准 HJ 633-2024）。⚠️ 必需参数: cities(list, 城市名称列表), start_date(str, 开始日期'YYYY-MM-DD'), end_date(str, 结束日期'YYYY-MM-DD')。可选: data_type(int, 数据类型, 默认1=审核数据)。返回: 日均值、AQI、首要污染物、空气质量等级",
    # 数据读取
    "read_data_registry": "读取已保存的数据结构。⚠️ **list_fields 必须为 true（必选）**——图表模式只需了解字段名称和类型，不需要获取具体数据内容；实际数据在 execute_python 中通过 data_id 对应的 JSON 文件路径自行读取。参数: data_id(str), list_fields(bool=true, 必选)",

    # 文件操作
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "edit_file": "精确编辑文件（字符串替换）。参数: path(str), old_string(str), new_string(str)",
    "grep": "搜索文件内容。参数: pattern(str), path(str)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件（glob模式）。参数: pattern(str)",

    # 代码执行
    "execute_python": "执行 Python 代码（数值计算、生成 Matplotlib 图表）。参数: code(str), timeout(int, 可选, 默认30)",

    # 任务管理
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # 模式互调
    "call_sub_agent": "调用问数模式查询数据。参数: target_mode(str), task_description(str)",
}

# ===== 社交模式工具（移动端助理） =====
SOCIAL_TOOLS = {
    # === 系统操作 ===
    "bash": "执行Shell命令（谨慎使用）。参数: command(str), timeout(int, 可选, 默认60), working_dir(str, 可选)",

    # === 文件操作 ===
    "read_file": "读取文件内容（统一入口，支持文本/图片/PDF/DOCX）。参数: path(str), offset(int, 可选, 起始行号), limit(int, 可选, 读取行数), pages(str, 可选, PDF/DOCX页面范围如'1-5'), extract_tables(bool, 可选, PDF提取表格, 默认true), extract_images(bool, 可选, PDF提取图片, 默认false), enable_preview(bool, 可选, PDF/DOCX生成预览, 默认true), encoding(str, 可选, 默认utf-8)",
    "edit_file": "精确编辑文件（字符串替换）。参数: path(str), old_string(str), new_string(str)",
    "read_docx": "读取DOCX文档内容（直接读取，无需解包）。参数: path(str), max_paragraphs(int, 可选, 默认100), include_tables(bool, 可选, 默认true)",
    "parse_pdf": "解析PDF文件并提取内容（支持文本提取、OCR识别、表格提取、元数据提取）。⚠️ 必需参数: path(str, PDF文件路径)。可选: mode(str, 解析模式: auto=自动检测/text=文本提取/ocr=OCR识别/table=表格提取/image=图片信息/meta=元数据, 默认auto), pages(str, 页面范围如'1-5', 可选), extract_tables(bool, 是否提取表格, 默认false), extract_images(bool, 是否提取图片信息, 默认false), ocr_engine(str, OCR引擎: auto/qwen/paddleocr/tesseract, 默认auto)",
    "grep": "搜索文件内容。参数: pattern(str), path(str)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件（glob模式）。参数: pattern(str)",

    # === 图片分析 ===
    "analyze_image": "分析图片内容。参数: path(str), operation(str, 可选, 默认analyze), prompt(str, 可选)",

    # === 知识库检索 ===
    "search_knowledge_base": "在知识库中检索相关信息。参数: query(str), knowledge_base_ids(list, 可选), top_k(int, 可选, 默认5), score_threshold(float, 可选, 默认0.5)",

    # === 数据查询 ===
    "query_gd_suncere_city_day_new": "查询广东省城市日空气质量数据（新标准 HJ 633-2024）。参数: cities(list), start_date(str), end_date(str)",
    "query_new_standard_report": "查询HJ 633-2024新标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true)",
    "compare_standard_reports": "新标准报表对比分析（对比两个时间段的综合指数、超标天数、达标率、六参数统计等全部指标）。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",
    "get_weather_forecast": "查询天气预报（未来7-16天，支持获取今天和昨天数据，Open-Meteo API）。⚠️ 必需参数: lat(float), lon(float)。可选: location_name(str), forecast_days(int, 默认7), past_days(int, 默认0), hourly(bool, 默认true), daily(bool, 默认true)",

    # === 可视化 ===
    "generate_aqi_calendar": "生成AQI日历热力图（需先使用query_new_standard_report等查询工具获取数据并得到data_id）。参数: data_id(str), year(int), month(int), pollutant(str, 可选, 默认AQI, 支持AQI/SO2/NO2/CO/O3_8h/PM2_5/PM10), cities(list, 可选, 默认广东省21个城市)",

    # === 代码执行 ===
    "execute_python": "执行 Python 代码（数值计算、数据处理、统计分析）。参数: code(str), timeout(int, 可选, 默认30)",

    # === 模式互调 ===
    "call_sub_agent": "调用子Agent（code=编程任务, expert=数据分析）。参数: target_mode(str), task_description(str), context_data(dict, 可选)",

    # === 呼吸式特有工具 ===
    "schedule_task": "创建定时任务。参数: task_description(str), schedule(str, cron表达式), channels(list, 可选, 支持'weixin'|'qq')",
    "send_notification": "主动发送通知（支持文本、图片、文件，自动发送到当前对话的用户）。参数: message(str), media(list, 可选, 支持本地路径或URL)",
    "spawn": "⭐创建后台子Agent执行长时间任务（不阻塞主对话，完成后主动通知）。参数: task(str, 任务描述), label(str, 可选, 任务标签), timeout(int, 可选, 超时秒数, 默认3600, 范围60-86400)",

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
    "grep": "搜索文件内容。参数: pattern(str), path(str)",
    "search_files": "搜索文件名。参数: pattern(str)",
    "list_directory": "列出目录。参数: path(str)",

    # Shell命令
    "bash": "执行Shell命令。参数: command(str)",

    # 编程工具
    "validate_tool": "验证工具定义。参数: tool_path(str)",

    # 模式互调
    "call_sub_agent": "调用Agent。参数: target_mode(str), task_description(str)",
}

# ===== 工具排序（影响展示顺序） =====
ASSISTANT_TOOL_ORDER = [
    "bash", "read_file", "edit_file", "grep", "write_file", "list_directory", "search_files",
    "read_docx",  # 读取DOCX文档（优先使用）
    "parse_pdf",  # 解析PDF文件
    "unpack_office", "pack_office", "word_edit", "accept_word_changes", "find_replace_word",
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
    "read_data_registry",
    "aggregate_data",

    # 分析工具
    "calculate_pm_pmf", "calculate_vocs_pmf", "calculate_pmf",
    "calculate_obm_ofp",
    "analyze_upwind_enterprises", "meteorological_trajectory_analysis", "analyze_trajectory_sources",
    "calculate_reconstruction", "calculate_carbon", "calculate_soluble", "calculate_crustal", "calculate_trace",
    "predict_air_quality",

    # 可视化
    "generate_chart", "smart_chart_generator", "revise_chart", "generate_map",

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

    # 源码查看工具
    "grep", "read_file", "write_file", "edit_file", "list_directory", "search_files",

    # 参数化查询工具
    "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_forecast",
    "query_xcai_city_history",
    "execute_sql_query",  # 通用SQL执行工具
    "query_gd_suncere_city_hour", "query_gd_suncere_station_hour_new", "query_gd_suncere_station_day_new", "query_gd_suncere_city_day", "query_gd_suncere_city_day_new", "query_gd_suncere_regional_comparison",
    "query_gd_suncere_report", "query_gd_suncere_report_compare",
    "query_new_standard_report",  # 新标准统计报表
    "query_old_standard_report",  # 旧标准统计报表
    "query_standard_comparison",  # 新旧标准对比
    "compare_standard_reports",  # 新标准报表对比分析
    "query_station_new_standard_report",  # 站点级新标准统计报表
    "compare_station_standard_reports",  # 站点级新标准报表对比分析

    # 数据分析工具
    "aggregate_data",

    # 知识库检索（预报会商场景）
    "search_knowledge_base",

    # 可视化工具
    "generate_aqi_calendar",
    "generate_chart",
    "smart_chart_generator",

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
    "query_station_new_standard_report",  # 站点级新标准统计报表
    "compare_station_standard_reports",  # 站点级新标准报表对比分析

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
    "query_gd_suncere_city_hour",
    "query_gd_suncere_city_day_new",
    "query_new_standard_report",
    "query_old_standard_report",
    "compare_standard_reports",

    # 数据读取
    "read_data_registry",

    # 文件操作
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",

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

    # 图片分析
    "analyze_image",

    # 数据查询
    "query_gd_suncere_city_day_new",
    "query_new_standard_report",
    "compare_standard_reports",
    "get_weather_forecast",

    # 可视化
    "generate_aqi_calendar",  # AQI日历热力图

    # 代码执行
    "execute_python",

    # 知识库检索
    "search_knowledge_base",

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


def get_tools_by_mode(mode: str) -> Dict[str, str]:
    """
    根据模式获取工具列表

    Args:
        mode: "assistant" | "expert" | "code" | "query" | "report" | "social" | "chart"

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
    else:
        raise ValueError(f"Unknown mode: {mode}")


def get_tool_order(mode: str) -> List[str]:
    """
    根据模式获取工具排序

    Args:
        mode: "assistant" | "expert" | "code" | "query" | "report" | "social" | "chart"

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
    else:
        raise ValueError(f"Unknown mode: {mode}")

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
    "read_file": "读取文件内容。参数: path(str), encoding(str, 可选, 默认utf-8)",
    "edit_file": "精确编辑文件（字符串替换）。参数: path(str), old_string(str), new_string(str)",
    "grep": "搜索文件内容。参数: pattern(str), path(str)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "list_directory": "列出目录内容。参数: path(str)",
    "search_files": "搜索文件（glob模式）。参数: pattern(str)",

    # Office工具（复杂工具，必须先阅读 office_skills_guide.md）
    "read_docx": "读取DOCX文档内容（直接读取，无需解包）。参数: path(str), max_paragraphs(int, 可选, 默认100), include_tables(bool, 可选, 默认true)",
    "unpack_office": "解包Office文件为XML（Word/Excel/PPT）。参数: path(str), output_dir(str, 可选)",
    "pack_office": "打包XML为Office文件。参数: input_dir(str), output_path(str)",
    "word_edit": "Word高级编辑（替换文本、插入内容）。参数: docx_path(str), edits(list)",
    "accept_word_changes": "接受Word文档的所有修订。参数: docx_path(str), output_path(str, 可选)",
    "find_replace_word": "Word文档查找替换。参数: docx_path(str), find(str), replace(str)",
    "recalc_excel": "Excel公式重算。参数: xlsx_path(str), output_path(str, 可选)",
    "add_ppt_slide": "PPT添加幻灯片。参数: pptx_path(str), slide_content(dict)",

    # 任务管理
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # 其他工具
    "create_scheduled_task": "创建定时任务。参数: user_request(str)",
    "analyze_image": "分析图片内容。参数: path(str), operation(str, 可选, 默认analyze), prompt(str, 可选)",
    "browser": "浏览器自动化。[必须先阅读browser_skills_guide.md]",
    "call_sub_agent": "调用专家Agent。参数: target_mode(str), task_description(str)",
}

# ===== 专家模式工具 =====
EXPERT_TOOLS = {
    # 数据查询工具（自然语言查询）
    "get_air_quality": "查询全国空气质量（自然语言查询）。参数: question(str)",
    "get_vocs_data": "查询VOCs组分数据（自然语言查询）。参数: question(str)",
    "get_pm25_ionic": "查询PM2.5水溶性离子。参数: start_time(str), end_time(str)",
    "get_pm25_carbon": "查询PM2.5碳组分。参数: start_time(str), end_time(str)",
    "get_pm25_crustal": "查询PM2.5地壳元素。参数: start_time(str), end_time(str)",
    "get_weather_data": "查询气象数据。参数: data_type(str), start_time(str), end_time(str)",

    # 分析工具（需先获取数据）
    "calculate_pm_pmf": "PM2.5 PMF源解析（需先调用get_pm25_ionic和get_pm25_carbon获取数据）。参数: data_ids(list), n_factors(int, 可选, 默认5)",
    "calculate_vocs_pmf": "VOCs PMF源解析（需先调用get_vocs_data获取数据）。参数: data_id(str), n_factors(int, 可选, 默认5)",
    "calculate_pmf": "PMF源解析（需先调用get_pm25_ionic和get_pm25_carbon获取数据）。参数: data_id(str), n_factors(int, 可选, 默认5)",
    "calculate_obm_ofp": "OBM/OFP分析（需先调用get_vocs_data、get_air_quality获取数据）。参数: vocs_data_id(str), air_quality_data_id(str)",
    "analyze_upwind_enterprises": "上风向企业分析（需先调用get_weather_data获取气象数据）。参数: lat(float), lon(float), start_time(str) [其他参数详见工具文档]",
    "meteorological_trajectory_analysis": "后向轨迹分析（独立工具，直接输入参数）。参数: lat(float), lon(float), start_time(str), hours(int, 可选, 默认72)",
    "analyze_trajectory_sources": "轨迹+源清单深度溯源（独立工具，直接输入参数）。参数: lat(float), lon(float), start_time(str) [其他参数详见工具文档]",
    "calculate_reconstruction": "PM2.5七大组分重构（需先调用get_pm25_ionic、get_pm25_carbon、get_pm25_crustal获取数据）。参数: ionic_data_id(str), carbon_data_id(str), crustal_data_id(str)",
    "calculate_carbon": "碳组分分析POC/SOC/EC（需先调用get_pm25_carbon获取数据）。参数: data_id(str)",
    "calculate_soluble": "水溶性离子分析（需先调用get_pm25_ionic获取数据）。参数: data_id(str)",
    "calculate_crustal": "地壳元素分析（需先调用get_pm25_crustal获取数据）。参数: data_id(str)",
    "calculate_trace": "微量元素分析（需先调用get_pm25_crustal获取数据）。参数: data_id(str)",
    "predict_air_quality": "空气质量预测（需先调用get_air_quality获取至少7天数据）。参数: city(str), days(int, 可选, 默认7)",

    # 可视化工具
    "generate_chart": "生成标准图表（15种类型）。参数: chart_type(str), data(list) [其他参数详见工具文档]",
    "smart_chart_generator": "智能图表生成（需data_id）。参数: data_id(str)",
    "revise_chart": "修订已生成图表（需chart_id）。参数: chart_id(str), revision_instruction(str)",
    "generate_map": "生成地图可视化（需站点坐标）。参数: locations(list), map_type(str, 可选, 默认scatter)",

    # 任务管理
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # 其他
    "call_sub_agent": "调用助手Agent。参数: target_mode(str), task_description(str)",
    "FINISH_SUMMARY": "生成分析报告。参数: answer(str)",
}

# ===== 问数模式工具 =====
QUERY_TOOLS = {
    # === 源码查看工具（了解工具实现细节） ===
    "grep": "搜索文件内容。参数: pattern(str), path(str)",
    "read_file": "读取文件内容。参数: path(str), encoding(str, 可选, 默认utf-8)",

    # === 现有参数化查询工具（复用） ===
    "get_pm25_ionic": "查询PM2.5水溶性离子。参数: start_time(str), end_time(str), locations(可选)",
    "get_pm25_carbon": "查询PM2.5碳组分。参数: start_time(str), end_time(str), locations(可选)",
    "get_pm25_crustal": "查询PM2.5地壳元素。参数: start_time(str), end_time(str), locations(可选)",
    "get_weather_data": "查询气象数据。参数: data_type(str), start_time(str), end_time(str), lat/lon(可选)",
    "query_gd_suncere_city_hour": "查询广东省城市小时空气质量数据。参数: cities(list), start_time(str), end_time(str)",
    "query_gd_suncere_city_day": "查询广东省城市日空气质量数据（旧标准，返回每日六参数、AQI、首要污染物）。参数: cities(list), start_date(str), end_date(str)",
    "query_gd_suncere_city_day_new": "查询广东省城市日空气质量数据（新标准 HJ 633-2024，返回每日六参数、AQI、首要污染物）。参数: cities(list), start_date(str), end_date(str)",
    "query_new_standard_report": "查询HJ 633-2024新标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理)",
    "query_old_standard_report": "查询HJ 633-2011旧标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理)",
    "query_standard_comparison": "新旧标准对比统计查询（返回综合指数、超标天数、达标率等统计指标）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true, 启用扣沙处理)",
    "compare_standard_reports": "新标准报表对比分析（对比两个时间段的综合指数、超标天数、达标率、六参数统计、单项质量指数、首要污染物统计等全部指标）。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",

     # === 新增：数据注册表工具 ===
    "read_data_registry": "读取已保存的数据。⚠️ **必须指定 time_range 参数（list_fields 模式除外）**，支持时间范围、字段选择。参数: data_id(str), time_range(str, **数据读取时必填**), list_fields(bool, 可选, 查看字段时使用), fields(可选, list), jq_filter(可选, str)",

    # === 数据分析工具 ===
    "aggregate_data": "数据聚合分析工具（使用前请先阅读使用指南：read_file(file_path='backend/app/tools/analysis/aggregate_data/aggregate_data_guide.md')）",

    # === 可视化工具 ===
    "generate_aqi_calendar": "生成AQI日历热力图（需先使用query_new_standard_report等查询工具获取数据并得到data_id）。参数: data_id(str), year(int), month(int), pollutant(str, 可选, 默认AQI, 支持AQI/SO2/NO2/CO/O3_8h/PM2_5/PM10), cities(list, 可选, 默认广东省21个城市)",

    # === 任务管理 ===
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # === 模式互调 ===
    "call_sub_agent": "调用专家Agent（深度分析）或助手Agent（生成报告）。参数: target_mode(str), task_description(str)",
}

# ===== 报告模式工具 =====
REPORT_TOOLS = {
    # 核心工具
    "read_docx": "读取DOCX文档内容（直接读取，无需解包）。参数: path(str), max_paragraphs(int, 可选, 默认100), include_tables(bool, 可选, 默认true)",

    # 数据查询工具（直接调用，支持并发）
    "query_gd_suncere_city_hour": "查询广东省城市小时空气质量数据。参数: cities(list), start_time(str), end_time(str)",
    "query_gd_suncere_city_day_new": "查询广东省城市日空气质量数据（新标准 HJ 633-2024）。参数: cities(list), start_date(str), end_date(str), data_type(int, 可选)",
    "query_new_standard_report": "查询HJ 633-2024新标准空气质量统计报表（综合指数、超标天数、达标率）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true)",
    "query_old_standard_report": "查询HJ 633-2011旧标准空气质量统计报表（综合指数、超标天数、达标率）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true)",
    "query_standard_comparison": "查询新旧空气质量标准对比（综合指数、超标天数、达标率）。参数: cities(list), start_date(str), end_date(str), enable_sand_deduction(bool, 可选, 默认true)",
    "compare_standard_reports": "新标准报表对比分析（对比两个时间段的综合指数、超标天数、达标率、六参数统计等全部指标）。参数: cities(list), query_period{start_date, end_date}, comparison_period{start_date, end_date}, enable_sand_deduction(bool, 可选, 默认true)",

    # 数据读取
    "read_data_registry": "读取已保存的数据。⚠️ **必须指定 time_range 参数（list_fields 模式除外）**，支持时间范围、字段选择。参数: data_id(str), time_range(str, **数据读取时必填**), list_fields(bool, 可选, 查看字段时使用), fields(可选, list)",

    # 文件操作
    "read_file": "读取文件内容。参数: path(str), encoding(str, 可选, 默认utf-8)",
    "write_file": "写入文件内容。参数: path(str), content(str)",
    "list_directory": "列出目录内容。参数: path(str)",

    # 任务管理
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",

    # 代码执行
    "execute_python": "执行 Python 代码（用于生成文档、数据处理、可视化）。参数: code(str), timeout(int, 可选, 默认30)",

    # 模式互调
    "call_sub_agent": "调用问数模式查询数据。参数: target_mode(str), task_description(str)",
}

# ===== 社交模式工具（移动端助理） =====
SOCIAL_TOOLS = {
    # === 系统操作 ===
    "bash": "执行Shell命令（谨慎使用）。参数: command(str), timeout(int, 可选, 默认60), working_dir(str, 可选)",

    # === 文件操作 ===
    "read_file": "读取文件内容。参数: path(str), encoding(str, 可选, 默认utf-8)",
    "edit_file": "精确编辑文件（字符串替换）。参数: path(str), old_string(str), new_string(str)",
    "read_docx": "读取DOCX文档内容（直接读取，无需解包）。参数: path(str), max_paragraphs(int, 可选, 默认100), include_tables(bool, 可选, 默认true)",
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
    "get_weather_data": "查询气象数据。参数: data_type(str), start_time(str), end_time(str)",

    # === 模式互调 ===
    "call_sub_agent": "调用子Agent（code=编程任务, expert=数据分析）。参数: target_mode(str), task_description(str), context_data(dict, 可选)",

    # === 呼吸式特有工具 ===
    "schedule_task": "创建定时任务。参数: task_description(str), schedule(str, cron表达式), channels(list, 可选, 支持'weixin'|'qq')",
    "send_notification": "主动发送通知（支持文本、图片、文件，自动发送到当前对话的用户）。参数: message(str), media(list, 可选, 支持本地路径或URL)",
    "spawn": "⭐创建后台子Agent执行长时间任务（不阻塞主对话，完成后主动通知）。参数: task(str, 任务描述), label(str, 可选, 任务标签), timeout(int, 可选, 超时秒数, 默认3600, 范围60-86400)",

    # === 网络搜索 ===
    "web_search": "搜索互联网。参数: query(str), count(int, 可选, 默认5, 范围1-10)",
    "web_fetch": "抓取网页并提取可读内容。参数: url(str), maxChars(int, 可选, 默认10000)",

    # === 记忆管理 ===
    "remember_fact": "记住重要事实。参数: fact(str), category(str, 可选, 默认general)",
    "search_history": "搜索历史对话。参数: query(str), limit(int, 可选, 默认10)",

    # === 任务管理 ===
    "TodoWrite": "更新任务清单（完整替换）。参数: items([{content, status}])",
}

# ===== 编程模式工具 =====
CODE_TOOLS = {
    # 文件操作
    "read_file": "读取文件。参数: path(str)",
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
    "unpack_office", "pack_office", "word_edit", "accept_word_changes", "find_replace_word",
    "recalc_excel", "add_ppt_slide",
    "TodoWrite",  # 任务管理工具
    "create_scheduled_task", "analyze_image",
    "browser",  # 浏览器自动化工具
    "call_sub_agent",  # 调用专家Agent
]

EXPERT_TOOL_ORDER = [
    # 查询工具
    "get_air_quality",
    "get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_data",

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
    # 源码查看工具
    "grep", "read_file",

    # 参数化查询工具
    "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_data",
    "query_gd_suncere_city_hour", "query_gd_suncere_city_day", "query_gd_suncere_city_day_new", "query_gd_suncere_regional_comparison",
    "query_gd_suncere_report", "query_gd_suncere_report_compare",
    "query_new_standard_report",  # 新标准统计报表
    "query_old_standard_report",  # 旧标准统计报表
    "query_standard_comparison",  # 新旧标准对比
    "compare_standard_reports",  # 新标准报表对比分析

    # 数据分析工具
    "aggregate_data",

    # 可视化工具
    "generate_aqi_calendar",

    # 数据注册表
    "read_data_registry",

    # 任务管理
    "TodoWrite",

    # 模式互调
    "call_sub_agent",
]

# ===== 报告模式工具排序 =====
REPORT_TOOL_ORDER = [
    # 核心工具
    "read_docx",

    # 数据查询工具（支持并发）
    "query_gd_suncere_city_hour",
    "query_gd_suncere_city_day_new",
    "query_new_standard_report",  # 新标准统计报表
    "query_old_standard_report",  # 旧标准统计报表
    "query_standard_comparison",
    "compare_standard_reports",  # 新标准报表对比分析

    # 数据读取
    "read_data_registry",

    # 文件操作
    "read_file", "write_file", "list_directory",

    # 任务管理
    "TodoWrite",

    # 代码执行
    "execute_python",

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
    "get_weather_data",

    # 知识库检索
    "search_knowledge_base",

    # 呼吸式特有工具
    "schedule_task",
    "send_notification",
    "spawn",  # ⭐ 后台任务工具

    # 网络搜索
    "web_search",
    "web_fetch",

    # 记忆管理
    "remember_fact",
    "search_history",

    # 任务管理
    "TodoWrite",

    # 模式互调
    "call_sub_agent",
]


def get_tools_by_mode(mode: str) -> Dict[str, str]:
    """
    根据模式获取工具列表

    Args:
        mode: "assistant" | "expert" | "code" | "query" | "report" | "social"

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
    else:
        raise ValueError(f"Unknown mode: {mode}")


def get_tool_order(mode: str) -> List[str]:
    """
    根据模式获取工具排序

    Args:
        mode: "assistant" | "expert" | "code" | "query" | "report" | "social"

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
    else:
        raise ValueError(f"Unknown mode: {mode}")

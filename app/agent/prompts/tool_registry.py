"""
工具注册表

定义两种Agent模式的工具列表和排序
"""

from typing import Dict, List

# ===== 助手模式工具 =====
ASSISTANT_TOOLS = {
    # Shell命令
    "bash": "执行Shell命令（支持管道、重定向、后台任务）",

    # 文件操作
    "read_file": "读取文件内容（支持文本、图片、PDF等）",
    "edit_file": "精确编辑文件内容（字符串替换）",
    "grep": "搜索文件内容（正则表达式，支持上下文行、文件过滤）",
    "write_file": "写入文件内容",
    "list_directory": "列出目录内容",
    "search_files": "搜索文件（支持glob模式）",

    # Office工具（参数需要严格匹配schema定义）
    "unpack_office": "解包Office文件为XML [需详细参数]",
    "pack_office": "打包XML为Office文件 [需详细参数]",
    "accept_word_changes": "接受Word文档所有修订 [需详细参数]",
    "find_replace_word": "Word文档查找替换 [需详细参数]",
    "recalc_excel": "Excel公式重算 [需详细参数]",
    "add_ppt_slide": "PPT添加幻灯片 [需详细参数]",
    "word_processor": "处理Word文档（读取、编辑、生成）",
    "excel_processor": "处理Excel表格（读取、计算、生成图表）",
    "ppt_processor": "处理PPT演示文稿",

    # 任务管理
    "create_scheduled_task": "创建定时任务 [需详细参数]",

    # 图片分析
    "analyze_image": "分析图片内容（OCR、目标检测等）[需详细参数]",

    # 浏览器自动化
    "browser": "浏览器自动化工具（导航网页/截图/提取数据/搜索等）",

    # 调用专家Agent
    "call_sub_agent": "调用专家Agent分析环境数据（空气质量/污染溯源/数据可视化）",

    # 注意：助手模式不需要FINISH工具，任务完成时直接输出纯文本回复
}

# ===== 专家模式工具 =====
EXPERT_TOOLS = {
    # 数据查询工具（高优先级）
    "get_guangdong_regular_stations": "查询广东省21城市空气质量数据",
    "get_air_quality": "查询全国空气质量监测数据（PM2.5/O3/AQI等）",
    "get_vocs_data": "查询VOCs组分数据",
    "get_pm25_ionic": "查询PM2.5水溶性离子数据（硫酸盐/硝酸盐等）",
    "get_pm25_carbon": "查询PM2.5碳组分数据（OC/EC）",
    "get_pm25_crustal": "查询PM2.5地壳元素数据",
    "get_weather_data": "查询气象数据（温度/风速/风向/降水等）",

    # 分析工具（包含依赖说明）
    "calculate_pm_pmf": "PMF受体模型源解析（识别污染源贡献，需先调用get_pm25_ionic和get_pm25_carbon获取小时粒度数据）",
    "calculate_vocs_pmf": "VOCs PMF源解析（需先调用get_vocs_data获取小时粒度VOCs数据）",
    "calculate_pmf": "PMF受体模型源解析（识别污染源贡献，需先调用get_pm25_ionic和get_pm25_carbon获取小时粒度数据）",
    "calculate_obm_ofp": "OBM/OFP臭氧生成潜势分析（需先调用get_vocs_data、get_air_quality获取VOCs和NOx/O3数据）",
    "calculate_obm_full_chemistry": "完整化学机理OBM分析（需先调用get_vocs_data和get_air_quality获取数据）",
    "analyze_upwind_enterprises": "上风向污染源企业分析（基于后向轨迹，需先调用get_weather_data获取气象数据）",
    "meteorological_trajectory_analysis": "后向轨迹分析（独立工具，直接输入经纬度和时间参数，内部调用NOAA HYSPLIT API）",
    "analyze_trajectory_sources": "HYSPLIT轨迹+源清单深度溯源（独立工具，直接输入经纬度和分析参数）",
    "calculate_reconstruction": "PM2.5七大组分重构（需先调用get_pm25_ionic、get_pm25_carbon、get_pm25_crustal获取完整组分数据）",
    "calculate_carbon": "碳组分分析POC/SOC/EC（需先调用get_pm25_carbon获取OC和EC数据）",
    "calculate_soluble": "水溶性离子分析（需先调用get_pm25_ionic获取离子数据）",
    "calculate_crustal": "地壳元素分析（需先调用get_pm25_crustal获取地壳元素数据）",
    "calculate_trace": "微量元素分析（需先调用get_pm25_crustal获取微量元素数据）",
    "calculate_iaqi": "IAQI计算（需先调用get_air_quality获取污染物浓度数据）",
    "predict_air_quality": "空气质量预测（需先调用get_air_quality获取至少7天历史数据）",

    # 可视化工具（包含依赖说明）
    "generate_chart": "生成标准图表（15种类型：折线/柱状/饼图/散点/风向玫瑰等）",
    "smart_chart_generator": "智能图表生成（自动选择最佳图表类型，需要data_id参数）",
    "revise_chart": "修订已生成图表（需要原图表的chart_id）",
    "generate_map": "生成地图可视化（需先调用get_nearby_stations或query_station_info获取站点坐标）",

    # 任务管理
    "create_task": "创建任务到任务清单",
    "update_task": "更新任务状态（pending/in_progress/completed）",
    "list_tasks": "查看当前所有任务",
    "get_task": "获取任务详情",

    # 调用助手Agent
    "call_sub_agent": "调用助手Agent处理办公任务（文件/Office/Shell）",

    # 特殊工具
    "load_data_from_memory": "从存储加载完整数据（需要先有data_id，格式如vocs_unified:xxx或pmf_result:xxx）",

    # 完成工具
    "FINISH_SUMMARY": "生成数据分析报告（数据查询完成后使用）",
}

# ===== 会商专用模式工具（仅专家会商内部使用） =====
DELIBERATION_METEOROLOGY_TOOLS = {
    "get_weather_data": EXPERT_TOOLS["get_weather_data"],
    "meteorological_trajectory_analysis": EXPERT_TOOLS["meteorological_trajectory_analysis"],
    "analyze_upwind_enterprises": EXPERT_TOOLS["analyze_upwind_enterprises"],
    "analyze_trajectory_sources": EXPERT_TOOLS["analyze_trajectory_sources"],
    "load_data_from_memory": EXPERT_TOOLS["load_data_from_memory"],
}

DELIBERATION_MONITORING_TOOLS = {
    "get_guangdong_regular_stations": EXPERT_TOOLS["get_guangdong_regular_stations"],
    "get_air_quality": EXPERT_TOOLS["get_air_quality"],
    "load_data_from_memory": EXPERT_TOOLS["load_data_from_memory"],
    "execute_python": EXPERT_TOOLS["execute_python"],
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
    "calculate_obm_full_chemistry": EXPERT_TOOLS["calculate_obm_full_chemistry"],
    "calculate_reconstruction": EXPERT_TOOLS["calculate_reconstruction"],
    "calculate_carbon": EXPERT_TOOLS["calculate_carbon"],
    "calculate_soluble": EXPERT_TOOLS["calculate_soluble"],
    "calculate_crustal": EXPERT_TOOLS["calculate_crustal"],
    "load_data_from_memory": EXPERT_TOOLS["load_data_from_memory"],
}

DELIBERATION_REVIEWER_TOOLS = {
    "load_data_from_memory": EXPERT_TOOLS["load_data_from_memory"],
}

# ===== 工具排序（影响展示顺序） =====
ASSISTANT_TOOL_ORDER = [
    "bash", "read_file", "edit_file", "grep", "write_file", "list_directory", "search_files",
    "unpack_office", "pack_office", "accept_word_changes", "find_replace_word", "recalc_excel", "add_ppt_slide",
    "word_processor", "excel_processor", "ppt_processor",
    "create_scheduled_task", "analyze_image",
    "browser",  # 浏览器自动化工具
    "call_sub_agent",  # 调用专家Agent
]

EXPERT_TOOL_ORDER = [
    # 查询工具
    "get_guangdong_regular_stations", "get_air_quality",
    "get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_data",

    # 分析工具
    "calculate_pm_pmf", "calculate_vocs_pmf", "calculate_pmf",
    "calculate_obm_ofp", "calculate_obm_full_chemistry",
    "analyze_upwind_enterprises", "meteorological_trajectory_analysis", "analyze_trajectory_sources",
    "calculate_reconstruction", "calculate_carbon", "calculate_soluble", "calculate_crustal", "calculate_trace",
    "calculate_iaqi", "predict_air_quality",

    # 可视化
    "generate_chart", "smart_chart_generator", "revise_chart", "generate_map",

    # 任务管理
    "create_task", "update_task", "list_tasks", "get_task",

    # 特殊工具
    "load_data_from_memory",

    # 调用助手Agent
    "call_sub_agent",

    # 完成
    "FINISH_SUMMARY"
]

DELIBERATION_METEOROLOGY_TOOL_ORDER = [
    "get_weather_data",
    "meteorological_trajectory_analysis",
    "analyze_upwind_enterprises",
    "analyze_trajectory_sources",
    "load_data_from_memory",
]

DELIBERATION_MONITORING_TOOL_ORDER = [
    "get_guangdong_regular_stations",
    "get_air_quality",
    "load_data_from_memory",
    "execute_python",
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
    "calculate_obm_full_chemistry",
    "calculate_reconstruction",
    "calculate_carbon",
    "calculate_soluble",
    "calculate_crustal",
    "load_data_from_memory",
]

DELIBERATION_REVIEWER_TOOL_ORDER = [
    "load_data_from_memory",
]


def get_tools_by_mode(mode: str) -> Dict[str, str]:
    """
    根据模式获取工具列表

    Args:
        mode: "assistant" | "expert"

    Returns:
        工具字典 {tool_name: description}
    """
    if mode == "assistant":
        return ASSISTANT_TOOLS
    elif mode == "expert":
        return EXPERT_TOOLS
    elif mode == "deliberation_meteorology":
        return DELIBERATION_METEOROLOGY_TOOLS
    elif mode == "deliberation_monitoring":
        return DELIBERATION_MONITORING_TOOLS
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
        mode: "assistant" | "expert"

    Returns:
        工具名称列表（按展示顺序）
    """
    if mode == "assistant":
        return ASSISTANT_TOOL_ORDER
    elif mode == "expert":
        return EXPERT_TOOL_ORDER
    elif mode == "deliberation_meteorology":
        return DELIBERATION_METEOROLOGY_TOOL_ORDER
    elif mode == "deliberation_monitoring":
        return DELIBERATION_MONITORING_TOOL_ORDER
    elif mode == "deliberation_chemistry":
        return DELIBERATION_CHEMISTRY_TOOL_ORDER
    elif mode == "deliberation_reviewer":
        return DELIBERATION_REVIEWER_TOOL_ORDER
    else:
        raise ValueError(f"Unknown mode: {mode}")

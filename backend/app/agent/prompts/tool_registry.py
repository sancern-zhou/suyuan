"""
工具注册表

定义多种Agent模式的工具列表和排序

⚠️ 重要说明：
- 工具参数和描述由原生 tool schema 提供（function_schema）
- 系统提示词不再重复注入工具目录
- 此文件仅定义各模式的工具名称列表和排序
"""

from typing import Dict, List, Literal

# ========================================
# 工具列表定义（仅包含工具名称）
# ========================================

# ===== 助手模式工具 =====
ASSISTANT_TOOL_NAMES = {
    # Shell命令
    "bash",

    # 文件操作
    "read_file", "edit_file", "grep", "write_file", "present_artifact", "list_directory",
    "search_files", "list_skills", "view_skill", "create_skill_draft",

    # Office工具
    "analyze_pptx_template", "create_pptx_from_template",
    "edit_pptx", "create_pptx_with_ppt_master", "validate_pptx",

    # 报告/展示产物
    "create_report_package", "validate_report_package", "create_html_artifact", "present_artifact",
    "create_diagram_artifact", "create_report_chart",

    # 任务管理
    "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",

    # 代码执行
    "execute_python",

    # 其他工具
    "create_scheduled_task", "broadcast_social_users", "analyze_image", "browser", "call_sub_agent",
    "web_search", "web_fetch", "wait_task",

    # 知识库检索
    "knowledge_qa_workflow", "knowledge_document_reader",

    # CLI会话管理
    "cli_session", "terminal_session",
}

# ===== 专家模式工具 =====
EXPERT_TOOL_NAMES = {
    # 数据查询工具
    "get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_forecast", "query_xcai_city_history", "execute_sql_query",
    "query_gd_suncere_city_hour", "query_gd_suncere_station_hour_new",
    "query_gd_suncere_city_day", "query_gd_suncere_district_day",
    "query_gd_suncere_district_report",
    "query_city_standard_report", "query_city_standard_yoy_report", "read_data_registry",

    # 分析工具
    "calculate_pm_pmf", "calculate_vocs_pmf",
    "analyze_upwind_enterprises",
    "meteorological_trajectory_analysis", "analyze_trajectory_sources",
    "calculate_reconstruction", "calculate_carbon", "calculate_soluble",
    "calculate_crustal", "calculate_trace", "predict_air_quality",

    # 可视化
    "revise_chart", "generate_map", "create_report_chart",

    # 代码执行
    "execute_python",

    # 文件操作
    "read_file", "write_file", "present_artifact", "edit_file", "grep", "list_directory", "search_files",

}

# ===== 问数模式工具 =====
QUERY_TOOL_NAMES = {
    # === 源码查看工具 ===
    "grep", "read_file", "write_file", "edit_file", "list_directory", "search_files",

    # === 参数化查询工具 ===
    "get_5min_data",
    "get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_forecast", "query_xcai_city_history", "execute_sql_query",
    "query_gd_suncere_city_hour",
    "query_gd_suncere_city_day", "query_gd_suncere_district_day",
    "query_city_standard_report", "query_city_standard_yoy_report",
    "query_station_standard_report", "query_station_standard_yoy_report",
    "query_gd_suncere_district_report",

    # === 全国省份空气质量查询 ===
    "query_national_province_air_quality", "query_national_city_air_quality",

    # === 数据注册表工具 ===
    "read_data_registry",

    # === 数值计算工具 ===
    "execute_python",
}

# ===== 报告模式工具 =====
REPORT_TOOL_NAMES = {
    # === 数据查询 ===
    # 5分钟数据
    "get_5min_data",

    # 广东省空气质量数据查询
    "query_gd_suncere_city_hour",          # 城市小时数据
    "query_gd_suncere_city_day",           # 城市日数据（通过ns_type选择新/旧国标）
    "query_gd_suncere_district_day",       # 区县日数据

    # SQL Server通用查询
    "execute_sql_query",

    # === 广东省统计报表工具 ===
    # 城市正式统计报表统一使用 query_city_standard_report / query_city_standard_yoy_report；
    # 旧通用综合报表工具 query_gd_suncere_report* 保留在底层注册中作兼容，不再暴露给报告 Agent 选择。
    "query_city_standard_report",          # 城市新/旧国标统计报表接口直查
    "query_city_standard_yoy_report",      # 城市新/旧国标同比/环比统计报表
    "query_gd_suncere_district_report",    # 区县统计报表（月度/年度/任意时段）
    "query_station_standard_report",       # 站点新/旧国标统计报表
    "query_station_standard_yoy_report",   # 站点新/旧国标同比/环比统计报表

    # === 数据读取 ===
    "read_data_registry",

    # === 文件操作 ===
    "read_file", "write_file", "present_artifact", "edit_file", "grep", "list_directory", "search_files",
    "bash",

    # === 报告/展示产物 ===
    "present_artifact",            # 将任意已生成文件推送到右侧预览面板
    "create_report_package",       # 正式报告收口为标准 ReportPackage，并触发右侧预览
    "validate_report_package",     # 检查 report.qmd、图片引用和已生成格式
    "create_report_chart",         # 正式报告静态图表，优先于自由 execute_python 绘图

    # === 代码执行 ===
    "execute_python",

    # === 规划工具 ===
    "complex_query_planner",
}

# ===== 图表模式工具 =====
CHART_TOOL_NAMES = {
    # 数据查询工具
    "get_5min_data", "query_gd_suncere_city_hour",
    "query_gd_suncere_station_hour_new", "query_gd_suncere_city_day",
    "query_gd_suncere_district_day", "query_gd_suncere_district_report",
    "query_city_standard_report", "query_city_standard_yoy_report",
    "query_station_standard_report", "query_station_standard_yoy_report",

    # SQL Server通用查询
    "execute_sql_query",

    # 知识库检索
    "knowledge_qa_workflow", "knowledge_document_reader",

    # 数据读取
    "read_data_registry",

    # 文件操作
    "read_file", "write_file", "present_artifact", "edit_file", "grep", "list_directory", "search_files",
    "bash",

    # 代码执行
    "create_report_chart", "execute_python", "execute_echarts_python",
}

# ===== 运维管理模式工具 =====
OPS_TOOL_NAMES = {
    # 运维工单与通用SQL查询
    "execute_ops_sql_query",
    "ops_audit_fetch_dataset",
    "ops_audit_run_rules",
    "ops_audit_inspect",

    # 展示型流程图
    "create_diagram_artifact",
    "create_report_chart",
    "present_artifact",

    # 报告产物
    "create_report_package",
    "validate_report_package",

    # 站点小时/日数据核对
    "query_gd_suncere_station_hour_new",
    "query_gd_suncere_station_day_new",

    # 数据读取
    "read_data_registry",

    # 代码执行
    "execute_python",

    # 文件操作
    "read_file", "write_file", "present_artifact", "edit_file", "grep", "list_directory", "search_files", "list_skills", "view_skill",
}

# ===== 社交模式工具（移动端助理） =====
SOCIAL_TOOL_NAMES = {
    # === 系统操作 ===
    "bash",

    # === 文件操作 ===
    "read_file", "edit_file", "grep", "write_file",
    "list_directory", "search_files", "list_skills", "view_skill",

    # === 知识库检索 ===
    "knowledge_qa_workflow", "knowledge_document_reader",

    # === 数据查询（统一通过 call_sub_agent 调用问数模式） ===
    "get_weather_forecast",

    # === 代码执行 ===
    "execute_python",

    # === 模式互调 ===
    "call_sub_agent",

    # === 呼吸式特有工具 ===
    "schedule_task", "send_notification", "spawn", "wait_task",

    # === 网络搜索 ===
    "web_search", "web_fetch", "browser",

    # === CLI会话管理 ===
    "cli_session", "terminal_session",

    # === 历史会话搜索 ===
    "session_search",

}

# ===== 记忆整合器工具（后台专用） =====
MEMORY_CONSOLIDATOR_TOOL_NAMES = {
    # 文件操作（只保留读取和搜索）
    "read_file", "grep",

    # 记忆管理（核心工具）
    "remember_fact", "replace_memory", "remove_memory",
}

# ===== 会商专用模式工具 =====
DELIBERATION_METEOROLOGY_TOOL_NAMES = {
    "get_weather_forecast", "query_gd_suncere_city_hour",
    "query_gd_suncere_station_hour_new", "meteorological_trajectory_analysis",
    "analyze_upwind_enterprises", "analyze_trajectory_sources",
    "read_data_registry", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
}

DELIBERATION_MONITORING_TOOL_NAMES = {
    "query_gd_suncere_city_hour", "query_gd_suncere_city_day",
    "query_gd_suncere_district_day", "query_gd_suncere_district_report",
    "query_gd_suncere_station_hour_new", "query_gd_suncere_station_day_new",
    "query_city_standard_report", "query_city_standard_yoy_report",
    "read_data_registry", "execute_python", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
}

DELIBERATION_CHEMISTRY_TOOL_NAMES = {
    "get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "calculate_vocs_pmf",
    "calculate_reconstruction", "calculate_carbon", "calculate_soluble",
    "calculate_crustal", "calculate_trace", "read_data_registry",
    "execute_python", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
}

DELIBERATION_REVIEWER_TOOL_NAMES = {
    "read_file", "write_file", "edit_file", "grep", "execute_python",
    "list_directory", "search_files", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
}

# ========================================
# 工具排序定义
# ========================================

ASSISTANT_TOOL_ORDER = [
    # 浏览
    "list_directory", "search_files", "read_file",

    # Office
    "analyze_pptx_template", "create_pptx_from_template",
    "edit_pptx", "create_pptx_with_ppt_master", "validate_pptx",

    # 报告/展示产物
    "create_report_package", "validate_report_package", "create_html_artifact", "present_artifact",

    # 编辑
    "write_file", "edit_file", "grep",

    # 执行
    "bash", "create_diagram_artifact", "create_report_chart", "execute_python", "analyze_image", "browser",

    # 知识库检索
    "knowledge_qa_workflow", "knowledge_document_reader",

    # 任务管理
    "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
    "create_scheduled_task", "wait_task", "list_skills", "view_skill", "create_skill_draft",

    # 模式互调
    "call_sub_agent"
]

EXPERT_TOOL_ORDER = [
    # 数据查询
    "get_vocs_data",
    "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_forecast",
    "query_xcai_city_history", "execute_sql_query",
    "query_gd_suncere_city_hour", "query_gd_suncere_city_day",
    "query_gd_suncere_district_day", "query_gd_suncere_district_report",
    "query_gd_suncere_station_hour_new", "query_gd_suncere_station_day_new",
    "query_city_standard_report", "query_city_standard_yoy_report",
    "read_data_registry",

    # 分析工具
    "calculate_pm_pmf", "calculate_vocs_pmf",
    "analyze_upwind_enterprises", "meteorological_trajectory_analysis", "analyze_trajectory_sources",
    "calculate_reconstruction", "calculate_carbon", "calculate_soluble", "calculate_crustal", "calculate_trace",
    "predict_air_quality",

    # 可视化
    "revise_chart", "generate_map", "create_report_chart",

    # 代码执行
    "execute_python",

    # 文件操作
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",

]

QUERY_TOOL_ORDER = [
    # 源码查看工具
    "grep", "read_file", "write_file", "edit_file", "list_directory", "search_files",

    # 参数化查询工具
    "get_5min_data",
    "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_forecast",
    "query_xcai_city_history", "execute_sql_query",
    "query_gd_suncere_city_hour", "query_gd_suncere_city_day",
    "query_gd_suncere_district_day",
    "query_city_standard_report", "query_city_standard_yoy_report",
    "query_station_standard_report", "query_station_standard_yoy_report",
    "query_gd_suncere_district_report",

    # 全国省份空气质量查询
    "query_national_province_air_quality", "query_national_city_air_quality",

    # 数据注册表工具
    "read_data_registry",

    # 数值计算
    "execute_python",

]

REPORT_TOOL_ORDER = [
    # 规划工具
    "complex_query_planner",

    # 数据查询
    "get_5min_data",
    "query_gd_suncere_city_hour",
    "query_gd_suncere_city_day",
    "query_gd_suncere_district_day",
    "execute_sql_query",
    "query_city_standard_report",
    "query_city_standard_yoy_report",
    "query_gd_suncere_district_report",
    "query_station_standard_report",
    "query_station_standard_yoy_report",

    # 知识库和数据读取
    "read_data_registry",

    # 文件和执行
    "read_file",
    "write_file",
    "present_artifact",
    "edit_file",
    "grep",
    "list_directory",
    "search_files",
    "bash",
    "create_report_chart",
    "execute_python",

    # 报告产物收口
    "create_report_package",
    "validate_report_package",
]

OPS_TOOL_ORDER = [
    # 技能发现与按需读取
    "list_skills",
    "view_skill",
    "read_file",

    # 工单查询
    "ops_audit_fetch_dataset",
    "ops_audit_run_rules",
    "ops_audit_inspect",
    "execute_ops_sql_query",

    # 展示型流程图
    "create_diagram_artifact",
    "create_report_chart",
    "present_artifact",

    # 报告产物收口
    "create_report_package",
    "validate_report_package",

    # 站点小时/日数据核对
    "query_gd_suncere_station_hour_new",
    "query_gd_suncere_station_day_new",

    # 数据读取
    "read_data_registry",

    # 代码执行
    "execute_python",

    # 文件操作
    "grep", "write_file", "present_artifact", "edit_file", "list_directory", "search_files",
]

CHART_TOOL_ORDER = [
    "read_file", "write_file", "present_artifact", "edit_file", "grep", "list_directory", "search_files",
    "bash", "create_report_chart", "execute_python", "execute_echarts_python",
    "read_data_registry",
    "get_5min_data", "query_gd_suncere_city_hour", "query_gd_suncere_station_hour_new",
    "query_gd_suncere_city_day", "query_gd_suncere_district_day", "query_gd_suncere_district_report",
    "query_city_standard_report", "query_city_standard_yoy_report",
    "query_station_standard_report", "query_station_standard_yoy_report",
    "execute_sql_query", "knowledge_qa_workflow", "knowledge_document_reader",
]

SOCIAL_TOOL_ORDER = [
    "read_file", "edit_file", "grep", "write_file",
    "list_directory", "search_files", "list_skills", "view_skill",
    "knowledge_qa_workflow", "knowledge_document_reader",
    "get_weather_forecast", "execute_python", "call_sub_agent",
    "web_search", "web_fetch", "browser",
    "schedule_task", "send_notification", "spawn", "wait_task",
    "cli_session", "terminal_session", "session_search",
    "bash",
]

MEMORY_CONSOLIDATOR_TOOL_ORDER = [
    # 文件操作（读取和搜索）
    "read_file", "grep",

    # 记忆管理（核心）
    "remember_fact", "replace_memory", "remove_memory",
]

DELIBERATION_REVIEWER_TOOL_ORDER = [
    "read_file", "write_file", "edit_file", "grep",
    "list_directory", "search_files", "execute_python",
    "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
]

# ========================================
# 工具字典生成（向后兼容）
# ========================================

def _build_tool_dict(tool_names: set) -> Dict[str, str]:
    """
    将工具名称集合转换为字典格式（向后兼容）

    Args:
        tool_names: 工具名称集合

    Returns:
        工具字典 {tool_name: ""}
    """
    return {name: "" for name in tool_names}

# 生成工具字典（保持向后兼容）
ASSISTANT_TOOLS = _build_tool_dict(ASSISTANT_TOOL_NAMES)
EXPERT_TOOLS = _build_tool_dict(EXPERT_TOOL_NAMES)
QUERY_TOOLS = _build_tool_dict(QUERY_TOOL_NAMES)
REPORT_TOOLS = _build_tool_dict(REPORT_TOOL_NAMES)
CHART_TOOLS = _build_tool_dict(CHART_TOOL_NAMES)
OPS_TOOLS = _build_tool_dict(OPS_TOOL_NAMES)
SOCIAL_TOOLS = _build_tool_dict(SOCIAL_TOOL_NAMES)
MEMORY_CONSOLIDATOR_TOOLS = _build_tool_dict(MEMORY_CONSOLIDATOR_TOOL_NAMES)
DELIBERATION_METEOROLOGY_TOOLS = _build_tool_dict(DELIBERATION_METEOROLOGY_TOOL_NAMES)
DELIBERATION_MONITORING_TOOLS = _build_tool_dict(DELIBERATION_MONITORING_TOOL_NAMES)
DELIBERATION_CHEMISTRY_TOOLS = _build_tool_dict(DELIBERATION_CHEMISTRY_TOOL_NAMES)
DELIBERATION_REVIEWER_TOOLS = _build_tool_dict(DELIBERATION_REVIEWER_TOOL_NAMES)


def get_tools_by_mode(mode: str) -> Dict[str, str]:
    """
    根据模式获取工具列表

    Args:
        mode: "assistant" | "expert" | "query" | "report" | "social" | "chart" | "ops" | "memory_consolidator" | "deliberation_*"

    Returns:
        工具字典 {tool_name: ""}
    """
    mode_mapping = {
        "assistant": ASSISTANT_TOOLS,
        "expert": EXPERT_TOOLS,
        "query": QUERY_TOOLS,
        "report": REPORT_TOOLS,
        "social": SOCIAL_TOOLS,
        "chart": CHART_TOOLS,
        "ops": OPS_TOOLS,
        "memory_consolidator": MEMORY_CONSOLIDATOR_TOOLS,
        "deliberation_meteorology": DELIBERATION_METEOROLOGY_TOOLS,
        "deliberation_monitoring": DELIBERATION_MONITORING_TOOLS,
        "deliberation_chemistry": DELIBERATION_CHEMISTRY_TOOLS,
        "deliberation_reviewer": DELIBERATION_REVIEWER_TOOLS,
    }

    if mode not in mode_mapping:
        raise ValueError(f"Unknown mode: {mode}")

    return mode_mapping[mode]


def get_tool_order(mode: str) -> List[str]:
    """
    获取模式的工具排序

    Args:
        mode: Agent模式名称

    Returns:
        排序后的工具名称列表
    """
    order_mapping = {
        "assistant": ASSISTANT_TOOL_ORDER,
        "expert": EXPERT_TOOL_ORDER,
        "query": QUERY_TOOL_ORDER,
        "report": REPORT_TOOL_ORDER,
        "social": SOCIAL_TOOL_ORDER,
        "chart": CHART_TOOL_ORDER,
        "ops": OPS_TOOL_ORDER,
        "memory_consolidator": MEMORY_CONSOLIDATOR_TOOL_ORDER,
        "deliberation_reviewer": DELIBERATION_REVIEWER_TOOL_ORDER,
    }

    return order_mapping.get(mode, [])

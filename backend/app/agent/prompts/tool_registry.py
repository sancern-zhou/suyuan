"""
工具注册表

定义六种Agent模式的工具列表和排序

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
    "read_file", "edit_file", "grep", "write_file", "list_directory",
    "search_files", "notebook_edit", "list_skills",

    # Office工具
    "read_docx", "parse_pdf", "unpack_office", "pack_office",
    "word_edit", "accept_word_changes", "read_pptx",
    "analyze_pptx_template", "create_pptx_from_template",
    "edit_pptx", "create_pptx", "validate_pptx",

    # 任务管理
    "TodoWrite",

    # 代码执行
    "execute_python",

    # 其他工具
    "create_scheduled_task", "analyze_image", "browser", "call_sub_agent",

    # CLI会话管理
    "cli_session", "terminal_session",
}

# ===== 专家模式工具 =====
EXPERT_TOOL_NAMES = {
    # 数据查询工具
    "get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_forecast", "query_xcai_city_history", "execute_sql_query",
    "query_gd_suncere_city_hour", "query_gd_suncere_station_hour_new",
    "query_gd_suncere_city_day", "query_gd_suncere_city_day_new",
    "query_city_standard_report", "query_city_standard_yoy_report", "read_data_registry",

    # 分析工具
    "calculate_pm_pmf", "calculate_vocs_pmf",
    "analyze_upwind_enterprises",
    "meteorological_trajectory_analysis", "analyze_trajectory_sources",
    "calculate_reconstruction", "calculate_carbon", "calculate_soluble",
    "calculate_crustal", "calculate_trace", "predict_air_quality",

    # 可视化
    "revise_chart", "generate_map",

    # 代码执行
    "execute_python",

    # 文件操作
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",

}

# ===== 问数模式工具 =====
QUERY_TOOL_NAMES = {
    # === 系统操作 ===
    "bash",

    # === 源码查看工具 ===
    "grep", "read_file", "write_file", "edit_file", "list_directory", "search_files",

    # === 参数化查询工具 ===
    "complex_query_planner",
    "get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "get_weather_forecast", "query_xcai_city_history", "execute_sql_query",
    "query_gd_suncere_city_hour", "query_gd_suncere_station_hour_new",
    "query_gd_suncere_city_day", "query_gd_suncere_city_day_new",
    "query_city_standard_report", "query_city_standard_yoy_report",
    "query_station_standard_report", "query_station_standard_yoy_report",

    # === 全国省份空气质量查询 ===
    "query_national_province_air_quality", "query_national_city_air_quality",

    # === 数据注册表工具 ===
    "read_data_registry",

    # === 知识库检索 ===
    "knowledge_qa_workflow", "knowledge_document_reader",

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
    "query_gd_suncere_station_hour_new",   # 站点小时数据（新标准）
    "query_gd_suncere_city_day",           # 城市日数据
    "query_gd_suncere_city_day_new",       # 城市日数据（新标准HJ 633-2026）

    # SQL Server通用查询
    "execute_sql_query",

    # === 广东省统计报表工具 ===
    # 城市正式统计报表统一使用 query_city_standard_report / query_city_standard_yoy_report；
    # 旧通用综合报表工具 query_gd_suncere_report* 保留在底层注册中作兼容，不再暴露给报告 Agent 选择。
    "query_city_standard_report",          # 城市新/旧国标统计报表接口直查
    "query_city_standard_yoy_report",      # 城市新/旧国标同比/环比统计报表
    "query_standard_comparison",           # 标准对比
    "query_old_standard_report",           # 旧标准统计报表（HJ 633-2013）

    # === 新标准统计报表工具（HJ 633-2026）===
    "query_new_standard_report",           # 新标准统计报表（城市/站点）
    "query_station_new_standard_report",   # 站点新标准统计报表
    "query_station_standard_report",       # 站点新/旧国标统计报表
    "query_station_standard_yoy_report",   # 站点新/旧国标同比/环比统计报表
    "compare_standard_reports",            # 新标准报表对比分析
    "compare_station_standard_reports",    # 站点新标准报表对比

    # === 旧标准统计报表工具（十三五/十四五）===
    "compare_old_standard_reports",        # 旧标准报表对比分析

    # === 知识库检索 ===
    "knowledge_qa_workflow", "knowledge_document_reader",

    # === 数据读取 ===
    "read_data_registry",

    # === 文件操作 ===
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",
    "bash",

    # === 代码执行 ===
    "execute_python",

    # === 任务管理 ===
    "TodoWrite",

    # === 模式互调 ===
    "call_sub_agent",

    # === 规划工具 ===
    "complex_query_planner",
}

# ===== 图表模式工具 =====
CHART_TOOL_NAMES = {
    # 数据查询工具
    "get_5min_data", "query_gd_suncere_city_hour",
    "query_gd_suncere_station_hour_new", "query_gd_suncere_city_day_new",
    "query_city_standard_report", "query_city_standard_yoy_report",
    "query_station_standard_report", "query_station_standard_yoy_report",

    # SQL Server通用查询
    "execute_sql_query",

    # 知识库检索
    "knowledge_qa_workflow", "knowledge_document_reader",

    # 数据读取
    "read_data_registry",

    # 文件操作
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",
    "bash",

    # 代码执行
    "execute_python",

    # 任务管理
    "TodoWrite",
}

# ===== 社交模式工具（移动端助理） =====
SOCIAL_TOOL_NAMES = {
    # === 系统操作 ===
    "bash",

    # === 文件操作 ===
    "read_file", "edit_file", "read_docx", "parse_pdf", "grep", "write_file",
    "list_directory", "search_files", "list_skills",

    # === 图片分析 ===
    "analyze_image",

    # === 知识库检索 ===
    "knowledge_qa_workflow", "knowledge_document_reader",

    # === 记忆管理 ===
    "remember_fact", "replace_memory", "remove_memory",

    # === 数据查询（统一通过 call_sub_agent 调用问数模式） ===
    "get_weather_forecast",

    # === 代码执行 ===
    "execute_python",

    # === 模式互调 ===
    "call_sub_agent",

    # === 呼吸式特有工具 ===
    "schedule_task", "send_notification", "spawn",

    # === 网络搜索 ===
    "web_search", "web_fetch",

    # === 任务管理 ===
    "TodoWrite",

    # === CLI会话管理 ===
    "cli_session", "terminal_session",

    # === 历史会话搜索 ===
    "session_search",

}

# ===== 记忆整合器工具（后台专用） =====
MEMORY_CONSOLIDATOR_TOOL_NAMES = {
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",
    "bash", "execute_python", "analyze_image", "create_scheduled_task",
    "browser", "call_sub_agent",
}

# ===== 会商专用模式工具 =====
DELIBERATION_METEOROLOGY_TOOL_NAMES = {
    "get_weather_forecast", "query_gd_suncere_city_hour",
    "query_gd_suncere_station_hour_new", "meteorological_trajectory_analysis",
    "analyze_upwind_enterprises", "analyze_trajectory_sources",
    "read_data_registry", "TodoWrite",
}

DELIBERATION_MONITORING_TOOL_NAMES = {
    "query_gd_suncere_city_hour", "query_gd_suncere_city_day_new",
    "query_gd_suncere_station_hour_new", "query_gd_suncere_station_day_new",
    "query_city_standard_report", "query_city_standard_yoy_report",
    "read_data_registry", "execute_python", "TodoWrite",
}

DELIBERATION_CHEMISTRY_TOOL_NAMES = {
    "get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "calculate_vocs_pmf",
    "calculate_reconstruction", "calculate_carbon", "calculate_soluble",
    "calculate_crustal", "calculate_trace", "read_data_registry",
    "execute_python", "TodoWrite",
}

DELIBERATION_REVIEWER_TOOL_NAMES = {
    "read_file", "write_file", "edit_file", "grep", "execute_python",
    "list_directory", "search_files", "TodoWrite",
}

# ========================================
# 工具排序定义
# ========================================

ASSISTANT_TOOL_ORDER = [
    # 浏览
    "list_directory", "search_files", "read_file",

    # Office
    "read_docx", "parse_pdf", "unpack_office", "pack_office",
    "word_edit", "accept_word_changes",
    "read_pptx", "analyze_pptx_template", "create_pptx_from_template",
    "edit_pptx", "create_pptx", "validate_pptx",

    # 编辑
    "write_file", "edit_file", "grep", "notebook_edit",

    # 执行
    "bash", "execute_python", "analyze_image", "browser",

    # 任务管理
    "TodoWrite", "create_scheduled_task", "list_skills",

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
    "query_gd_suncere_station_hour_new", "query_gd_suncere_station_day_new",
    "query_city_standard_report", "query_city_standard_yoy_report",
    "read_data_registry",

    # 分析工具
    "calculate_pm_pmf", "calculate_vocs_pmf",
    "analyze_upwind_enterprises", "meteorological_trajectory_analysis", "analyze_trajectory_sources",
    "calculate_reconstruction", "calculate_carbon", "calculate_soluble", "calculate_crustal", "calculate_trace",
    "predict_air_quality",

    # 可视化
    "revise_chart", "generate_map",

    # 代码执行
    "execute_python",

    # 文件操作
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",

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
    "query_xcai_city_history", "execute_sql_query",
    "query_gd_suncere_city_hour", "query_gd_suncere_city_day",
    "query_gd_suncere_station_hour_new", "query_gd_suncere_station_day_new",
    "query_city_standard_report", "query_city_standard_yoy_report",
    "query_station_standard_report", "query_station_standard_yoy_report",

    # 全国省份空气质量查询
    "query_national_province_air_quality", "query_national_city_air_quality",

    # 数据注册表工具
    "read_data_registry",

    # 知识库检索
    "knowledge_qa_workflow", "knowledge_document_reader",

    # 数值计算
    "execute_python",

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
        mode: "assistant" | "expert" | "code" | "query" | "report" | "social" | "chart" | "memory_consolidator" | "deliberation_*"

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
    }

    return order_mapping.get(mode, [])

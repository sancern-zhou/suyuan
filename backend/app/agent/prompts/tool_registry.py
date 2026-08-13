"""
工具注册表

定义多种 Agent 模式的有序工具白名单。

⚠️ 重要说明：
- 工具参数和描述由原生 tool schema 提供（function_schema）
- 系统提示词不再重复注入工具目录
- 此文件仅定义各模式可用工具；列表顺序即展示/提示顺序
"""

from typing import Dict, Iterable, List

# ========================================
# 工具有序白名单（仅包含工具名称）
# ========================================

# 工具实现可由显式后端工作流继续使用，但不得向任何 Agent 暴露。
AGENT_HIDDEN_TOOL_NAMES = frozenset({
    "aggregate_data",
    "calculate_pmf", "calculate_pm_pmf", "calculate_vocs_pmf",
    "analyze_trajectory_sources",
    "calculate_reconstruction", "calculate_carbon", "calculate_soluble",
    "calculate_crustal", "calculate_trace", "predict_air_quality",
    "generate_map",
    "get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
    "query_gd_suncere_city_hour", "query_gd_suncere_city_day",
    "query_gd_suncere_district_day", "query_gd_suncere_district_report",
    "query_gd_suncere_station_hour_new",
})

# ===== 助手模式工具 =====
ASSISTANT_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # 浏览
    "list_directory", "search_files", "read_file",

    # Office
    "manage_editable_ppt", "create_pptx_with_ppt_master", "validate_pptx",

    # 报告/展示产物
    "create_report_package", "render_report_package", "validate_report_package", "create_html_artifact",

    # 编辑
    "write_file", "edit_file", "grep",

    # 执行
    "bash", "create_report_chart", "execute_python",
    "get_platform_weather_image", "browser",

    # 知识库检索
    "knowledge_qa_workflow", "knowledge_document_reader",

    # 数据查询
    "qianlima_realtime_tender", "execute_tender_sql_query", "execute_postgres_sql_query",

    # 任务和技能
    "create_scheduled_task", "wait_task", "list_skills", "view_skill", "create_skill_draft",

    # 网络和通知
    "web_search", "web_fetch", "broadcast_social_users",

    # CLI会话管理
    "cli_session", "terminal_session",

    # 模式互调
    "call_sub_agent",
]

# ===== 幻灯片模式工具 =====
PPT_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # PPT 源码项目和交付
    "manage_editable_ppt", "validate_pptx", "create_pptx_with_ppt_master",
    # 文件读取与直接源码编辑
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",
    # 图表、图片检查和必要计算
    "create_report_chart", "execute_python",
    # 用户材料、知识库与外部资料
    "knowledge_qa_workflow", "knowledge_document_reader",
    "web_search", "web_fetch", "browser",
]

# ===== 专家模式工具 =====
EXPERT_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # 气象、空气质量与遥感证据查询工具
    "get_weather_data", "get_observed_meteorology",
    "get_current_weather", "get_weather_forecast",
    "get_platform_weather_image",
    "get_satellite_data", "get_gems_image", "get_sentinel5p_image", "get_fire_hotspots",
    "query_xcai_city_history", "execute_sql_query", "execute_postgres_sql_query",

    # 分析工具
    "analyze_upwind_enterprises", "analyze_xuchang_upwind_permit_sources",
    "meteorological_trajectory_analysis",

    # 可视化
    "create_report_chart",

    # 代码执行
    "execute_python",

    # 文件操作
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",
]

# ===== 问数模式工具 =====
QUERY_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # === 源码查看工具 ===
    "grep", "read_file", "write_file", "edit_file", "list_directory", "search_files",

    # === 参数化查询工具 ===
    "get_5min_data",
    "get_weather_data", "get_observed_meteorology", "get_weather_forecast",
    "query_xcai_city_history", "execute_sql_query", "execute_postgres_sql_query",
    "analyze_city_pollutant_rankings",
    "knowledge_graph_query",
    "resolve_station_geo",

    # === 全国省份空气质量查询 ===
    "query_national_province_air_quality", "query_national_city_air_quality",

    # === 数值计算工具 ===
    "execute_python",

    # === 图表生成工具 ===
    "create_report_chart", "execute_echarts_python",
]

# ===== 报告模式工具 =====
REPORT_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",

    # 数据查询
    "get_5min_data",
    "execute_sql_query", "execute_postgres_sql_query",
    "analyze_city_pollutant_rankings",

    # 文件和执行
    "read_file", "write_file", "edit_file", "grep",
    "list_directory", "search_files", "bash",
    "create_report_chart", "execute_python",

    # 报告产物收口
    "create_report_package", "render_report_package", "validate_report_package",
]

# ===== 图表模式工具 =====
CHART_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # 文件操作
    "read_file", "write_file", "edit_file", "grep", "list_directory", "search_files",
    "bash",

    # 代码执行和原生多模态视觉参考
    "create_report_chart", "execute_python", "execute_echarts_python",
]

# ===== 画板模式工具 =====
BOARD_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    "read_file",
    "edit_file",
    "create_drawio_board",
    "render_drawio_board_candidate",
    "accept_drawio_board_candidate",
]

# ===== 运维管理模式工具 =====
OPS_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # 技能发现与按需读取
    "list_skills", "view_skill", "read_file",

    # 工单查询
    "ops_audit_fetch_dataset", "ops_audit_run_rules", "ops_audit_inspect",
    "knowledge_graph_query", "execute_ops_sql_query",

    # 展示型流程图（已废弃 create_diagram_artifact，使用画板模式替代）
    "create_report_chart",

    # 报告产物收口
    "create_report_package", "render_report_package", "validate_report_package",

    # 子 Agent 复核
    "call_sub_agent",

    # 代码执行
    "execute_python",

    # 文件操作
    "grep", "write_file", "edit_file", "list_directory", "search_files",
]

# ===== 知识库图谱编辑模式工具 =====
GRAPH_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    "knowledge_graph_query",
    "knowledge_graph_build",
    "read_file",
    "edit_file",
    "grep",
    "list_directory",
    "search_files",
]

# ===== 社交模式工具（移动端助理） =====
SOCIAL_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # 文件操作
    "read_file", "edit_file", "grep", "write_file",
    "list_directory", "search_files", "list_skills", "view_skill",

    # 知识库检索
    "knowledge_qa_workflow", "knowledge_document_reader",

    # 代码执行和模式互调
    "execute_python", "call_sub_agent",

    # 网络搜索
    "web_search", "web_fetch",

    # 呼吸式特有工具
    "schedule_task", "send_notification", "spawn", "wait_task",

    # CLI会话管理和历史搜索
    "cli_session", "terminal_session", "session_search",

    # 系统操作
    "bash",
]

# ===== 记忆整合器工具（后台专用） =====
MEMORY_CONSOLIDATOR_TOOL_NAMES = [
    "list_session_resources",
    # 文件操作（只保留读取和搜索）
    "read_file", "grep",

    # 记忆管理（核心工具）
    "remember_fact", "replace_memory", "remove_memory",
]

# ===== 会商专用模式工具 =====
DELIBERATION_METEOROLOGY_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    "get_weather_forecast", "get_observed_meteorology", "meteorological_trajectory_analysis",
    "analyze_upwind_enterprises", "analyze_xuchang_upwind_permit_sources",
    "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
]

DELIBERATION_MONITORING_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    "execute_python", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
]

DELIBERATION_CHEMISTRY_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # 由会商专家的受限工具白名单提供化学分析能力。
    "execute_python", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
]

DELIBERATION_REVIEWER_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    "read_file", "write_file", "edit_file", "grep",
    "list_directory", "search_files", "execute_python",
    "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
]

# ========================================
# 工具字典生成（向后兼容）
# ========================================

def _build_tool_dict(tool_names: Iterable[str]) -> Dict[str, str]:
    """
    将工具名称列表转换为字典格式（向后兼容）。
    字典保留插入顺序，因此列表顺序就是模式工具顺序。
    """
    names = [name for name in tool_names if name not in AGENT_HIDDEN_TOOL_NAMES]
    if "list_session_resources" in names and "read_session_resource" not in names:
        names.insert(names.index("list_session_resources") + 1, "read_session_resource")
    return {name: "" for name in names}


ASSISTANT_TOOLS = _build_tool_dict(ASSISTANT_TOOL_NAMES)
PPT_TOOLS = _build_tool_dict(PPT_TOOL_NAMES)
EXPERT_TOOLS = _build_tool_dict(EXPERT_TOOL_NAMES)
QUERY_TOOLS = _build_tool_dict(QUERY_TOOL_NAMES)
REPORT_TOOLS = _build_tool_dict(REPORT_TOOL_NAMES)
CHART_TOOLS = _build_tool_dict(CHART_TOOL_NAMES)
BOARD_TOOLS = _build_tool_dict(BOARD_TOOL_NAMES)
OPS_TOOLS = _build_tool_dict(OPS_TOOL_NAMES)
GRAPH_TOOLS = _build_tool_dict(GRAPH_TOOL_NAMES)
SOCIAL_TOOLS = _build_tool_dict(SOCIAL_TOOL_NAMES)
MEMORY_CONSOLIDATOR_TOOLS = _build_tool_dict(MEMORY_CONSOLIDATOR_TOOL_NAMES)
DELIBERATION_METEOROLOGY_TOOLS = _build_tool_dict(DELIBERATION_METEOROLOGY_TOOL_NAMES)
DELIBERATION_MONITORING_TOOLS = _build_tool_dict(DELIBERATION_MONITORING_TOOL_NAMES)
DELIBERATION_CHEMISTRY_TOOLS = _build_tool_dict(DELIBERATION_CHEMISTRY_TOOL_NAMES)
DELIBERATION_REVIEWER_TOOLS = _build_tool_dict(DELIBERATION_REVIEWER_TOOL_NAMES)

# Backward-compatible order aliases used by tests and older callers.
ASSISTANT_TOOL_ORDER = ASSISTANT_TOOL_NAMES
PPT_TOOL_ORDER = PPT_TOOL_NAMES
EXPERT_TOOL_ORDER = EXPERT_TOOL_NAMES
QUERY_TOOL_ORDER = QUERY_TOOL_NAMES
REPORT_TOOL_ORDER = REPORT_TOOL_NAMES
CHART_TOOL_ORDER = CHART_TOOL_NAMES
BOARD_TOOL_ORDER = BOARD_TOOL_NAMES
OPS_TOOL_ORDER = OPS_TOOL_NAMES
GRAPH_TOOL_ORDER = GRAPH_TOOL_NAMES
SOCIAL_TOOL_ORDER = SOCIAL_TOOL_NAMES
MEMORY_CONSOLIDATOR_TOOL_ORDER = MEMORY_CONSOLIDATOR_TOOL_NAMES


def get_tools_by_mode(mode: str) -> Dict[str, str]:
    """
    根据模式获取工具有序白名单。

    Args:
        mode: "assistant" | "ppt" | "expert" | "query" | "report" | "social" | "chart" | "board" | "ops" | "memory_consolidator" | "deliberation_*"

    Returns:
        工具字典 {tool_name: ""}，key 顺序即工具顺序。
    """
    mode_mapping = {
        "assistant": ASSISTANT_TOOLS,
        "ppt": PPT_TOOLS,
        "expert": EXPERT_TOOLS,
        "query": QUERY_TOOLS,
        "report": REPORT_TOOLS,
        "social": SOCIAL_TOOLS,
        "chart": CHART_TOOLS,
        "board": BOARD_TOOLS,
        "ops": OPS_TOOLS,
        "graph": GRAPH_TOOLS,
        "memory_consolidator": MEMORY_CONSOLIDATOR_TOOLS,
        "deliberation_meteorology": DELIBERATION_METEOROLOGY_TOOLS,
        "deliberation_monitoring": DELIBERATION_MONITORING_TOOLS,
        "deliberation_chemistry": DELIBERATION_CHEMISTRY_TOOLS,
        "deliberation_reviewer": DELIBERATION_REVIEWER_TOOLS,
    }

    if mode not in mode_mapping:
        raise ValueError(f"Unknown mode: {mode}")

    from app.project_config.loader import load_project_context
    from config.settings import settings

    disabled_tools = set(
        load_project_context(settings.project_id).manifest.backend.disabled_tools
    )
    return {
        name: description
        for name, description in mode_mapping[mode].items()
        if name not in disabled_tools
    }


def get_tool_order(mode: str) -> List[str]:
    """
    获取模式工具顺序。

    顺序直接由 get_tools_by_mode(mode) 的有序白名单派生，不再维护独立排序常量。
    """
    return list(get_tools_by_mode(mode).keys())


def get_tool_order_by_mode(mode: str) -> List[str]:
    """Compatibility alias for callers that name the mode explicitly."""
    return get_tool_order(mode)

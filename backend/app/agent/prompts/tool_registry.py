"""
工具注册表

定义多种 Agent 模式的有序工具白名单。

⚠️ 重要说明：
- 工具参数和描述由原生 tool schema 提供（function_schema）
- 系统提示词不再重复注入工具目录
- 此文件仅定义各模式可用工具；列表顺序即展示/提示顺序
"""

from typing import Dict, Iterable, List

# 工具实现可由显式后端工作流继续使用，但不得向任何 Agent 暴露。
AGENT_HIDDEN_TOOL_NAMES = frozenset({
    "aggregate_data",
    "calculate_pmf", "calculate_pm_pmf", "calculate_vocs_pmf",
    "analyze_trajectory_sources",
    "calculate_reconstruction", "calculate_carbon", "calculate_soluble",
    "calculate_crustal", "calculate_trace", "predict_air_quality",
    "generate_map",
    "get_vocs_data", "get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal",
})

# ========================================
# 工具有序白名单（仅包含工具名称）
# ========================================

# Project manifests may append tools to a mode without changing the shared
# baseline.  The shared registry itself contains no project data-source names.
PROJECT_SCOPED_TOOL_NAMES = frozenset()

# Registered for internal orchestration and maintenance only. These tools must
# never be published in an Agent mode, including project-defined modes.
AGENT_INTERNAL_TOOL_NAMES = frozenset({
    "render_report_package",
    "validate_report_package",
})

# ===== 助手模式工具 =====
ASSISTANT_TOOL_NAMES = [
    "list_session_resources",
    "execute_tender_sql_query",
    "zhiliao_tender_detail",
    # 轻量办公：搜索、阅读、编辑文档和生成 HTML 结果。
    "list_directory",
    "search_files",
    "read_file",
    "write_file",
    "edit_file",
    "grep",
    "create_html_artifact",
    "create_report_package",
    # 轻量数据计算与网页检索抓取。
    "execute_python",
    "web_search",
    "web_fetch",
    "browser",
    # 任务调度、技能目录和重型工作空间委托。
    "create_scheduled_task",
    "wait_task",
    "list_skills",
    "view_skill",
    "call_sub_agent",
    "run_agent_workflow",
]

# ===== 幻灯片模式工具 =====
PPT_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # PPT 源码项目和交付
    "manage_editable_ppt",
    "validate_pptx",
    "create_pptx_with_ppt_master",
    # 文件读取与直接源码编辑
    "read_file",
    "write_file",
    "edit_file",
    "grep",
    "list_directory",
    "search_files",
    # 图表、图片检查和必要计算
    "create_business_chart",
    "execute_python",
    # 用户材料、知识库与外部资料
    "knowledge_qa_workflow",
    "knowledge_document_reader",
    "web_search",
    "web_fetch",
    "browser",
]

# ===== 专家模式工具 =====
EXPERT_TOOL_NAMES = [
    "run_agent_workflow",
    "call_sub_agent",
    "list_session_resources",
    "publish_session_file",
    # 知识库检索与命中文档上下文阅读
    "knowledge_qa_workflow",
    "knowledge_document_reader",
    # 数据查询工具
    "get_vocs_data",
    "get_pm25_ionic",
    "get_pm25_carbon",
    "get_pm25_crustal",
    "get_weather_forecast",
    "get_observed_meteorology",
    "get_platform_weather_image",
    "query_xcai_city_history",
    "execute_sql_query",
    # 分析工具
    "meteorological_trajectory_analysis",
    # 可视化
    "create_business_chart",
    "execute_echarts_python",
    # 代码执行
    "execute_python",
    # 文件操作
    "read_file",
    "write_file",
    "edit_file",
    "grep",
    "list_directory",
    "search_files",
]

# ===== 气象专家模式工具（报告 DAG 子专家，精简配置） =====
# 只保留气象研判必需工具；污染物/组分工具不进入本白名单。
EXPERT_METEOROLOGY_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # 上游产物复用与中间产物落地
    "read_file",
    "write_file",
    # 气象数据
    "get_observed_meteorology",
    "get_weather_forecast",
    "get_current_weather",
    "get_platform_weather_image",
    # 输送分析
    "meteorological_trajectory_analysis",
    "resolve_station_geo",
    "execute_sql_query",
    # 计算与绘图
    "execute_python",
    "create_business_chart",
]

# ===== 常规分析专家模式工具（报告 DAG 子专家，精简配置） =====
# 只保留监测数据研判必需工具；气象/轨迹工具不进入本白名单。
# 注意：组分数据工具（get_vocs_data 等）在 AGENT_HIDDEN_TOOL_NAMES 中，不对 Agent 暴露。
EXPERT_ANALYSIS_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # 上游产物复用与中间产物落地
    "read_file",
    "write_file",
    # 监测数据
    "query_xcai_city_history",
    "query_national_city_air_quality",
    "execute_sql_query",
    # 计算与可视化
    "execute_python",
    "create_business_chart",
]

# ===== 问数模式工具 =====
QUERY_TOOL_NAMES = [
    "run_agent_workflow",
    "call_sub_agent",
    "list_session_resources",
    "publish_session_file",
    # === 源码查看工具 ===
    "grep",
    "read_file",
    "write_file",
    "edit_file",
    "list_directory",
    "search_files",
    # === 参数化查询工具 ===
    "get_vocs_data",
    "get_pm25_ionic",
    "get_pm25_carbon",
    "get_pm25_crustal",
    "get_weather_data",
    "get_observed_meteorology",
    "get_weather_forecast",
    "get_current_weather",
    "query_xcai_city_history",
    "execute_sql_query",
    "knowledge_graph_query",
    "resolve_station_geo",
    # === 全国省份空气质量查询 ===
    "query_national_province_air_quality",
    "query_national_city_air_quality",
    # === Agentic GIS 视觉交互工具 ===
    "resolve_map_data_asset",
    "create_map_point_asset",
    "spatial_analysis",
    "spatial_interpolation",
    "visual_interaction",
    "get_map_program_receipt",
    "wait_map_program_receipt",
    # === 数值计算工具 ===
    "execute_python",
    # === 图表生成工具 ===
    "create_business_chart",
    "execute_echarts_python",
]

# ===== 报告 DAG 问数子模式工具（精简配置，核心取数集） =====
# 常规空气质量监测问数：只保留监测历史取数与核算必需工具；
# 气象/预报/轨迹工具不进入本白名单。
QUERY_MONITORING_TOOL_NAMES = [
    "list_session_resources",
    "read_session_resource",
    "publish_session_file",
    # 上游产物复用与中间产物落地（read_file 不进问数流程：
    # 质检/合并用 execute_python，读上游结果用 read_session_resource）
    "write_file",
    # 监测数据取数（目录解析工具与中台工具成对配置，服务乡镇站编码链路；
    # 综合兜底模式同样保留）
    "query_xcai_city_history",
    "execute_sql_query",
    "execute_crawler_sql_query",
    "execute_postgres_sql_query",
    "query_airdata_platform",
    "xuchang_station_catalog",
    "airdata_calc_report_summary",
    "query_national_city_air_quality",
    # 可选归一化计算
    "execute_python",
]

# 气象与空气质量预报问数：只保留气象实况/预报与预报产品取数必需工具；
# 监测历史统计工具不进入本白名单。
QUERY_FORECAST_TOOL_NAMES = [
    "list_session_resources",
    "read_session_resource",
    "publish_session_file",
    # 上游产物复用与中间产物落地（read_file 不进问数流程，同上）
    "write_file",
    # 气象实况与预报取数
    "get_weather_data",
    "get_current_weather",
    "get_weather_forecast",
    # 空气质量预报产品与站点定位
    "query_airdata_platform",
    "xuchang_station_catalog",
    "resolve_station_geo",
    "execute_postgres_sql_query",
    # 可选归一化计算
    "execute_python",
]

# 站点层级监测问数：国控站走采集库 SQL（Station 表即站点目录）；乡镇站/中台口径
# 走"目录解析编码 → 中台查询"（编码不可猜，必要串行），目录工具与中台工具成对配置。
QUERY_MONITORING_STATION_TOOL_NAMES = [
    # 站点层级取数（采集库 StationHour/StationDay/Station）
    "execute_crawler_sql_query",
    # 乡镇站/中台口径链路（先 xuchang_station_catalog 解析编码，再查询）
    "xuchang_station_catalog",
    "query_airdata_platform",
    # 可选归一化计算
    "execute_python",
]

# 城市层级监测问数：城市小时/日/年均值 + SQL Server 城市发布历史 + 中台接口；
# 站点层级表不进入本白名单（工具内仍可查，由阶段提示约束表层级）。
QUERY_MONITORING_CITY_TOOL_NAMES = [
    "query_xcai_city_history",
    "execute_sql_query",
    "execute_crawler_sql_query",
    "execute_postgres_sql_query",
    "query_airdata_platform",
    "airdata_calc_report_summary",
    "query_national_city_air_quality",
    # 可选归一化计算
    "execute_python",
]
# ===== 知识问答模式工具 =====
# 知识库检索为主；按需读取已注册的会话资源，并用网页搜索/抓取补充知识库不足。
KNOWLEDGE_TOOL_NAMES = [
    "knowledge_qa_workflow",
    "knowledge_document_reader",
    "knowledge_graph_query",
    "read_session_resource",
    "web_search",
    "web_fetch",
]

# ===== 报告模式工具 =====
REPORT_TOOL_NAMES = [
    "list_session_resources",
    "read_session_resource",
    "publish_session_file",
    # 读取参考资料、报告草稿与记忆；编辑交付物与记忆，数据查询由 DAG 子节点完成
    "read_file",
    "write_file",
    "edit_file",
    "grep",
    "list_directory",
    "search_files",
    "bash",
    "create_business_chart",
    "execute_python",
    "execute_echarts_python",
    # 报告产物收口
    "create_report_package",
    # 报告主 Agent 统一通过 DAG 委托子 Agent
    "run_agent_workflow",
]

# ===== 图表模式工具 =====
CHART_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    # 文件操作
    "read_file",
    "write_file",
    "edit_file",
    "grep",
    "list_directory",
    "search_files",
    "bash",
    # 代码执行和原生多模态视觉参考
    "create_business_chart",
    "execute_python",
    "execute_echarts_python",
    # 数据查询工具
    "get_observed_meteorology",
    "execute_sql_query",
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
    "list_skills",
    "view_skill",
    "read_file",
    # 工单查询
    "ops_audit_fetch_dataset",
    "ops_audit_run_rules",
    "ops_audit_inspect",
    "agent_case_library",
    "knowledge_graph_query",
    "execute_ops_sql_query",
    # 审核正式报告生成与验收
    "create_report_package",
    # 子 Agent 复核
    "call_sub_agent",
    # 代码执行
    "execute_python",
    # 文件操作
    "grep",
    "write_file",
    "edit_file",
    "list_directory",
    "search_files",
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
    "read_file",
    "edit_file",
    "grep",
    "write_file",
    "list_directory",
    "search_files",
    "list_skills",
    "view_skill",
    # 知识库检索
    "knowledge_qa_workflow",
    "knowledge_document_reader",
    # 代码执行和模式互调
    "execute_python",
    "call_sub_agent",
    # 正式报告生成与收口
    "create_business_chart",
    "create_report_package",
    # 网络搜索
    "web_search",
    "web_fetch",
    # 呼吸式特有工具
    "schedule_task",
    "send_notification",
    "spawn",
    "wait_task",
    # CLI会话管理和历史搜索
    "cli_session",
    "terminal_session",
    "session_search",
    # 系统操作
    "bash",
]

# ===== 生态环境执法备考模式（微信专业场景） =====
ENFORCEMENT_EXAM_TOOL_NAMES = [
    "exam_practice",
    "generate_exam_bank",
    "knowledge_qa_workflow",
    "knowledge_document_reader",
    "web_search",
    "web_fetch",
    "schedule_task",
]

# ===== 记忆整合器工具（后台专用） =====
MEMORY_CONSOLIDATOR_TOOL_NAMES = [
    "list_session_resources",
    # 文件操作（只保留读取和搜索）
    "read_file",
    "grep",
    # 记忆管理（核心工具）
    "remember_fact",
    "replace_memory",
    "remove_memory",
    "agent_case_library",
]

# ===== 会商专用模式工具 =====
DELIBERATION_METEOROLOGY_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    "get_weather_forecast",
    "get_observed_meteorology",
    "meteorological_trajectory_analysis",
    "analyze_trajectory_sources",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "TaskGet",
]

DELIBERATION_MONITORING_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    "execute_python",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "TaskGet",
]

DELIBERATION_CHEMISTRY_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    "get_vocs_data",
    "get_pm25_ionic",
    "get_pm25_carbon",
    "get_pm25_crustal",
    "calculate_vocs_pmf",
    "calculate_reconstruction",
    "calculate_carbon",
    "calculate_soluble",
    "calculate_crustal",
    "calculate_trace",
    "execute_python",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "TaskGet",
]

DELIBERATION_REVIEWER_TOOL_NAMES = [
    "list_session_resources",
    "publish_session_file",
    "read_file",
    "write_file",
    "edit_file",
    "grep",
    "list_directory",
    "search_files",
    "execute_python",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "TaskGet",
]

# ========================================
# 工具字典生成（向后兼容）
# ========================================


def _build_tool_dict(tool_names: Iterable[str]) -> Dict[str, str]:
    """
    将工具名称列表转换为字典格式（向后兼容）。
    字典保留插入顺序，因此列表顺序就是模式工具顺序。
    """
    names = [
        name
        for name in tool_names
        if name not in AGENT_HIDDEN_TOOL_NAMES and name not in AGENT_INTERNAL_TOOL_NAMES
    ]
    if "list_session_resources" in names and "read_session_resource" not in names:
        names.insert(names.index("list_session_resources") + 1, "read_session_resource")
    return {name: "" for name in names}


ASSISTANT_TOOLS = _build_tool_dict(ASSISTANT_TOOL_NAMES)
PPT_TOOLS = _build_tool_dict(PPT_TOOL_NAMES)
EXPERT_TOOLS = _build_tool_dict(EXPERT_TOOL_NAMES)
EXPERT_METEOROLOGY_TOOLS = _build_tool_dict(EXPERT_METEOROLOGY_TOOL_NAMES)
EXPERT_ANALYSIS_TOOLS = _build_tool_dict(EXPERT_ANALYSIS_TOOL_NAMES)
QUERY_MONITORING_TOOLS = _build_tool_dict(QUERY_MONITORING_TOOL_NAMES)
QUERY_MONITORING_STATION_TOOLS = _build_tool_dict(QUERY_MONITORING_STATION_TOOL_NAMES)
QUERY_MONITORING_CITY_TOOLS = _build_tool_dict(QUERY_MONITORING_CITY_TOOL_NAMES)
QUERY_FORECAST_TOOLS = _build_tool_dict(QUERY_FORECAST_TOOL_NAMES)
QUERY_TOOLS = _build_tool_dict(QUERY_TOOL_NAMES)
KNOWLEDGE_TOOLS = _build_tool_dict(KNOWLEDGE_TOOL_NAMES)
REPORT_TOOLS = _build_tool_dict(REPORT_TOOL_NAMES)
CHART_TOOLS = _build_tool_dict(CHART_TOOL_NAMES)
BOARD_TOOLS = _build_tool_dict(BOARD_TOOL_NAMES)
OPS_TOOLS = _build_tool_dict(OPS_TOOL_NAMES)
GRAPH_TOOLS = _build_tool_dict(GRAPH_TOOL_NAMES)
SOCIAL_TOOLS = _build_tool_dict(SOCIAL_TOOL_NAMES)
ENFORCEMENT_EXAM_TOOLS = _build_tool_dict(ENFORCEMENT_EXAM_TOOL_NAMES)
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
KNOWLEDGE_TOOL_ORDER = KNOWLEDGE_TOOL_NAMES
REPORT_TOOL_ORDER = REPORT_TOOL_NAMES
CHART_TOOL_ORDER = CHART_TOOL_NAMES
BOARD_TOOL_ORDER = BOARD_TOOL_NAMES
OPS_TOOL_ORDER = OPS_TOOL_NAMES
GRAPH_TOOL_ORDER = GRAPH_TOOL_NAMES
SOCIAL_TOOL_ORDER = SOCIAL_TOOL_NAMES
ENFORCEMENT_EXAM_TOOL_ORDER = ENFORCEMENT_EXAM_TOOL_NAMES
MEMORY_CONSOLIDATOR_TOOL_ORDER = MEMORY_CONSOLIDATOR_TOOL_NAMES


def get_tools_by_mode(mode: str) -> Dict[str, str]:
    """
    根据模式获取工具有序白名单。

    Args:
        mode: "assistant" | "ppt" | "expert" | "expert_meteorology" | "expert_analysis" | "query" | "query_monitoring" | "query_monitoring_station" | "query_monitoring_city" | "query_forecast" | "report" | "social" | "enforcement_exam" | "chart" | "board" | "ops" | "memory_consolidator" | "deliberation_*"

    Returns:
        工具字典 {tool_name: ""}，key 顺序即工具顺序。
    """
    mode_mapping = {
        "assistant": ASSISTANT_TOOLS,
        "ppt": PPT_TOOLS,
        "expert": EXPERT_TOOLS,
        "expert_meteorology": EXPERT_METEOROLOGY_TOOLS,
        "expert_analysis": EXPERT_ANALYSIS_TOOLS,
        "query_monitoring": QUERY_MONITORING_TOOLS,
        "query_monitoring_station": QUERY_MONITORING_STATION_TOOLS,
        "query_monitoring_city": QUERY_MONITORING_CITY_TOOLS,
        "query_forecast": QUERY_FORECAST_TOOLS,
        "query": QUERY_TOOLS,
        "knowledge": KNOWLEDGE_TOOLS,
        "report": REPORT_TOOLS,
        "social": SOCIAL_TOOLS,
        "enforcement_exam": ENFORCEMENT_EXAM_TOOLS,
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

    project_tool_names = _get_project_tool_names_by_mode(mode)
    if mode not in mode_mapping and project_tool_names is None:
        raise ValueError(f"Unknown mode: {mode}")

    if project_tool_names is not None:
        tools = _build_tool_dict(project_tool_names)
    else:
        extra_tool_names = _get_project_extra_tool_names_by_mode(mode)
        base_names = list(mode_mapping[mode].keys())
        if mode in {"assistant", "ppt", "expert", "query", "knowledge", "report", "chart", "board", "ops", "graph"}:
            base_names.append("ask_user_question")
        merged_names = base_names + [name for name in (extra_tool_names or []) if name not in base_names]
        tools = _build_tool_dict(merged_names)

    disabled_tools = _get_project_disabled_tool_names()
    if not disabled_tools:
        return tools
    return {name: description for name, description in tools.items() if name not in disabled_tools}


def _load_project_context():
    """Load the active project context; missing/broken manifests fail loudly."""
    from app.project_config.loader import load_project_context
    from config.settings import settings

    return load_project_context(settings.project_id)


def _get_project_tool_names_by_mode(mode: str) -> list[str] | None:
    """Return project-specific mode tools when the active manifest declares them."""
    from app.project_config.loader import ProjectConfigError

    try:
        context = _load_project_context()
    except ProjectConfigError:
        # Fail closed: a broken manifest must not silently expose the full
        # shared whitelist (this is how project-scoped tools used to leak).
        raise
    except Exception:
        return None
    return context.manifest.backend.agent_mode_tools.get(mode)


def _get_project_extra_tool_names_by_mode(mode: str) -> list[str]:
    """Return project tools appended to a shared mode whitelist."""
    from app.project_config.loader import ProjectConfigError

    try:
        context = _load_project_context()
    except ProjectConfigError:
        raise
    except Exception:
        return []
    return context.manifest.backend.agent_mode_extra_tools.get(mode, [])


def _get_project_disabled_tool_names() -> frozenset[str]:
    """Return tools that the active project must not expose to agents."""
    from app.project_config.loader import ProjectConfigError

    try:
        context = _load_project_context()
    except ProjectConfigError:
        raise
    except Exception:
        return frozenset()
    return frozenset(context.manifest.backend.disabled_tools)


def get_tool_order(mode: str) -> List[str]:
    """
    获取模式工具顺序。

    顺序直接由 get_tools_by_mode(mode) 的有序白名单派生，不再维护独立排序常量。
    """
    return list(get_tools_by_mode(mode).keys())


def get_tool_order_by_mode(mode: str) -> List[str]:
    """Compatibility alias for callers that name the mode explicitly."""
    return get_tool_order(mode)

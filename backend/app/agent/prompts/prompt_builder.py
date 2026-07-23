"""
ReAct系统提示词构建器（多模式架构）

⚠️ 注意：保留现有的query模式（WEB端问数模式），支持social、chart、ops等独立场景模式。
"""

from typing import Literal, List, Optional
from .assistant_prompt import build_assistant_prompt
from .ppt_prompt import build_ppt_prompt
from .expert_prompt import build_expert_prompt
from .query_prompt import build_query_prompt
from .report_prompt import build_report_prompt
from .social_prompt import build_social_prompt
from .chart_prompt import build_chart_prompt
from .board_prompt import build_board_prompt
from .ops_prompt import build_ops_prompt
from .graph_prompt import build_graph_prompt
from .custom_prompt import build_custom_prompt
from .deliberation_prompt import (
    build_deliberation_chemistry_prompt,
    build_deliberation_meteorology_prompt,
    build_deliberation_monitoring_prompt,
    build_deliberation_reviewer_prompt,
)
from .tool_registry import get_tools_by_mode
import structlog

logger = structlog.get_logger()

AgentMode = Literal[
    "assistant",
    "ppt",
    "expert",
    "query",
    "report",
    "social",
    "chart",
    "board",
    "ops",
    "graph",
    "custom",
    "memory_consolidator",
    "deliberation_meteorology",
    "deliberation_monitoring",
    "deliberation_chemistry",
    "deliberation_reviewer",
]


def build_react_system_prompt(
    mode: AgentMode,
    available_tools: Optional[List[str]] = None,
    user_preferences: Optional[dict] = None,
    memory_file_path: Optional[str] = None,
    soul_file_path: Optional[str] = None,  # ✅ 新增：soul.md 文件路径
    user_file_path: Optional[str] = None,  # ✅ 新增：USER.md 文件路径
    heartbeat_file_path: Optional[str] = None,  # ✅ 新增：HEARTBEAT.md 文件路径
    memory_context: Optional[str] = None,  # ✅ 记忆上下文内容（MEMORY.md）
    soul_context: Optional[str] = None,  # ✅ 新增：soul.md 内容（助理灵魂档案）
    user_context: Optional[str] = None,  # ✅ 新增：用户上下文内容（USER.md）
    heartbeat_context: Optional[str] = None,  # ✅ 新增：HEARTBEAT.md 当前内容
    backend_host: Optional[str] = None,  # ✅ 新增：网关地址（仅social模式使用）
    board_context: Optional[dict] = None,  # 画板模式 draw.io 上下文
) -> str:
    """
    构建ReAct系统提示词（多模式架构）

    Args:
        mode: Agent模式 ("assistant" | "ppt" | "expert" | "query" | "report" | "social" | "chart" | "ops")
        available_tools: 可用工具列表（如果为None，自动加载该模式的所有工具）
        user_preferences: 用户偏好配置（仅social模式使用）
        memory_file_path: 用户记忆文件路径（仅social模式使用）
        soul_file_path: soul.md 文件路径（仅social模式使用）
        user_file_path: USER.md 文件路径（仅social模式使用）
        heartbeat_file_path: HEARTBEAT.md 文件路径（仅social模式使用）
        memory_context: 记忆上下文内容（从快照获取，直接注入到系统提示词）
        soul_context: soul.md 内容（助理灵魂档案，仅social模式使用）
        user_context: 用户上下文内容（从USER.md获取，仅social模式使用）
        heartbeat_context: HEARTBEAT.md 当前内容（仅social模式使用）
        backend_host: 网关地址（仅social模式使用，优先使用API_BASE_URL配置，用于生成公网分享链接）

    Returns:
        系统提示词字符串
    """
    # 如果未指定工具，加载该模式的默认工具
    if available_tools is None and mode != "custom":
        tools_dict = get_tools_by_mode(mode)
        available_tools = list(tools_dict.keys())

    # 过滤：只保留该模式支持的工具
    if mode == "custom":
        filtered_tools = list(available_tools or [])
    else:
        mode_tools = get_tools_by_mode(mode)
        filtered_tools = [t for t in available_tools if t in mode_tools]

    logger.info(
        "building_prompt",
        mode=mode,
        tool_count=len(filtered_tools),
        has_user_preferences=user_preferences is not None,
        memory_file_path=memory_file_path,
        soul_file_path=soul_file_path,  # ✅ 新增日志
        user_file_path=user_file_path,  # ✅ 新增日志
        has_memory_context=memory_context is not None,
        has_soul_context=soul_context is not None,  # ✅ 新增日志
        has_user_context=user_context is not None,  # ✅ 新增日志
        has_heartbeat_context=heartbeat_context is not None,
        has_board_context=board_context is not None,
    )

    # 根据模式构建Prompt（✅ 统一传递所有路径和上下文）
    if mode == "custom":
        return build_custom_prompt(filtered_tools)
    if mode == "assistant":
        return build_assistant_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "ppt":
        return build_ppt_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "expert":
        return build_expert_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "query":
        return build_query_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "report":
        return build_report_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "social":
        return build_social_prompt(
            filtered_tools,
            user_preferences,
            memory_file_path,
            soul_file_path,
            user_file_path,
            heartbeat_file_path,
            memory_context,
            soul_context,
            user_context,
            heartbeat_context,
            backend_host,
        )
    elif mode == "chart":
        return build_chart_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "board":
        return build_board_prompt(
            filtered_tools,
            memory_context,
            memory_file_path,
            board_context,
        )
    elif mode == "ops":
        return build_ops_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "graph":
        return build_graph_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "deliberation_meteorology":
        return build_deliberation_meteorology_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "deliberation_monitoring":
        return build_deliberation_monitoring_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "deliberation_chemistry":
        return build_deliberation_chemistry_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "deliberation_reviewer":
        return build_deliberation_reviewer_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "memory_consolidator":
        from .memory_consolidator_prompt import build_memory_consolidator_prompt
        return build_memory_consolidator_prompt(filtered_tools)
    else:
        raise ValueError(f"Unknown mode: {mode}")


def estimate_token_count(prompt: str) -> int:
    """
    估算Token数量（粗略估计：1 token ≈ 1.5 字符）
    """
    return int(len(prompt) / 1.5)

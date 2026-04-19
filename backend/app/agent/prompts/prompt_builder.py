"""
ReAct系统提示词构建器（七模式架构）

⚠️ 注意：保留现有的query模式（WEB端问数模式），新增social模式（移动端呼吸式Agent）和chart模式（图表生成模式）
"""

from typing import Literal, List, Optional
from .assistant_prompt import build_assistant_prompt
from .expert_prompt import build_expert_prompt
from .code_prompt import build_code_prompt
from .query_prompt import build_query_prompt
from .report_prompt import build_report_prompt
from .social_prompt import build_social_prompt
from .chart_prompt import build_chart_prompt
from .tool_registry import get_tools_by_mode, get_tool_order
import structlog

logger = structlog.get_logger()

AgentMode = Literal["assistant", "expert", "code", "query", "report", "social", "chart"]


def build_react_system_prompt(
    mode: AgentMode,
    available_tools: Optional[List[str]] = None,
    user_preferences: Optional[dict] = None,
    memory_file_path: Optional[str] = None,
    soul_file_path: Optional[str] = None,  # ✅ 新增：soul.md 文件路径
    user_file_path: Optional[str] = None,  # ✅ 新增：USER.md 文件路径
    memory_context: Optional[str] = None,  # ✅ 记忆上下文内容（MEMORY.md）
    soul_context: Optional[str] = None,  # ✅ 新增：soul.md 内容（助理灵魂档案）
    user_context: Optional[str] = None  # ✅ 新增：用户上下文内容（USER.md）
) -> str:
    """
    构建ReAct系统提示词（七模式架构）

    Args:
        mode: Agent模式 ("assistant" | "expert" | "code" | "query" | "report" | "social" | "chart")
        available_tools: 可用工具列表（如果为None，自动加载该模式的所有工具）
        user_preferences: 用户偏好配置（仅social模式使用）
        memory_file_path: 用户记忆文件路径（仅social模式使用）
        soul_file_path: soul.md 文件路径（仅social模式使用）
        user_file_path: USER.md 文件路径（仅social模式使用）
        memory_context: 记忆上下文内容（从快照获取，直接注入到系统提示词）
        soul_context: soul.md 内容（助理灵魂档案，仅social模式使用）
        user_context: 用户上下文内容（从USER.md获取，仅social模式使用）

    Returns:
        系统提示词字符串
    """
    # 如果未指定工具，加载该模式的默认工具
    if available_tools is None:
        tools_dict = get_tools_by_mode(mode)
        available_tools = list(tools_dict.keys())

    # 过滤：只保留该模式支持的工具
    mode_tools = get_tools_by_mode(mode)
    filtered_tools = [t for t in available_tools if t in mode_tools]

    # 确保call_sub_agent工具在列表中
    if "call_sub_agent" not in filtered_tools:
        filtered_tools.append("call_sub_agent")

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
        has_user_context=user_context is not None  # ✅ 新增日志
    )

    # 根据模式构建Prompt（✅ 统一传递所有路径和上下文）
    if mode == "assistant":
        return build_assistant_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "expert":
        return build_expert_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "code":
        return build_code_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "query":
        return build_query_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "report":
        return build_report_prompt(filtered_tools, memory_context, memory_file_path)
    elif mode == "social":
        return build_social_prompt(filtered_tools, user_preferences, memory_file_path, soul_file_path, user_file_path, memory_context, soul_context, user_context)
    elif mode == "chart":
        return build_chart_prompt(filtered_tools, memory_context, memory_file_path)
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

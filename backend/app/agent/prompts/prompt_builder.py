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
    available_tools: Optional[List[str]] = None
) -> str:
    """
    构建ReAct系统提示词（七模式架构）

    Args:
        mode: Agent模式 ("assistant" | "expert" | "code" | "query" | "report" | "social" | "chart")
        available_tools: 可用工具列表（如果为None，自动加载该模式的所有工具）

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
        tool_count=len(filtered_tools)
    )

    # 根据模式构建Prompt
    if mode == "assistant":
        return build_assistant_prompt(filtered_tools)
    elif mode == "expert":
        return build_expert_prompt(filtered_tools)
    elif mode == "code":
        return build_code_prompt(filtered_tools)
    elif mode == "query":
        return build_query_prompt(filtered_tools)
    elif mode == "report":
        return build_report_prompt(filtered_tools)
    elif mode == "social":
        return build_social_prompt(filtered_tools)
    elif mode == "chart":
        return build_chart_prompt(filtered_tools)
    else:
        raise ValueError(f"Unknown mode: {mode}")


def estimate_token_count(prompt: str) -> int:
    """
    估算Token数量（粗略估计：1 token ≈ 1.5 字符）
    """
    return int(len(prompt) / 1.5)

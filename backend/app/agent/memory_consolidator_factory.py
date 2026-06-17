"""
记忆整合Agent工厂函数
"""
from .react_agent import ReActAgent
from .prompts.tool_registry import MEMORY_CONSOLIDATOR_TOOLS
from app.agent.tool_adapter import get_react_agent_tool_registry
import structlog

logger = structlog.get_logger(__name__)


def create_memory_consolidator_agent(**kwargs) -> ReActAgent:
    """创建记忆整合Agent实例"""
    global_tool_registry = get_react_agent_tool_registry()
    memory_tool_names = set(MEMORY_CONSOLIDATOR_TOOLS)
    tool_registry = {
        name: tool
        for name, tool in global_tool_registry.items()
        if name in memory_tool_names
    }
    missing_tools = sorted(memory_tool_names - set(tool_registry))
    if missing_tools:
        logger.warning(
            "memory_consolidator_tools_missing",
            missing_tools=missing_tools,
        )

    logger.info(
        "memory_consolidator_agent_created",
        tool_count=len(tool_registry),
        tools=sorted(tool_registry),
    )

    agent = ReActAgent(
        tool_registry=tool_registry,
        max_iterations=10,  # 记忆整合最多10步（增加迭代次数以提供更多尝试机会）
        enable_memory=False,  # 记忆整合Agent不需要记忆
        **kwargs
    )

    return agent

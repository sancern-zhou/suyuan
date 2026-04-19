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

    # 过滤只保留记忆管理工具（字典格式）
    memory_tools = {
        name: global_tool_registry[name]
        for name in MEMORY_CONSOLIDATOR_TOOLS.keys()
        if name in global_tool_registry
    }

    logger.info("memory_consolidator_agent_created", tool_count=len(memory_tools))

    agent = ReActAgent(
        tool_registry=memory_tools,
        max_iterations=5,  # 记忆整合最多5步
        enable_memory=False,  # 记忆整合Agent不需要记忆
        **kwargs
    )

    return agent

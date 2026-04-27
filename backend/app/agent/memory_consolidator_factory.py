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
    # 使用完整工具注册表，不限制工具使用
    # 通过系统提示词引导Agent优先使用记忆管理工具
    global_tool_registry = get_react_agent_tool_registry()

    logger.info("memory_consolidator_agent_created", tool_count=len(global_tool_registry))

    agent = ReActAgent(
        tool_registry=global_tool_registry,
        max_iterations=10,  # 记忆整合最多10步（增加迭代次数以提供更多尝试机会）
        enable_memory=False,  # 记忆整合Agent不需要记忆
        **kwargs
    )

    return agent

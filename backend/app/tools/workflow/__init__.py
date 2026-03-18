"""
Workflow Tools 模块

工作流工具是封装了多个原子工具调用的高级工具，用于实现复杂的分析流程。
工作流工具作为ReAct工具注册到全局工具注册表，可以被LLM直接调用。
"""

import structlog
from typing import List

logger = structlog.get_logger()

# 工作流工具类（延迟导入，避免循环依赖）
_WORKFLOW_TOOL_CLASSES = {}

# 工作流工具注册表
WORKFLOW_TOOLS_REGISTRY = {}


def register_workflow_tool(tool_class):
    """
    注册工作流工具类

    Args:
        tool_class: 工作流工具类
    """
    _WORKFLOW_TOOL_CLASSES[tool_class.name] = tool_class
    WORKFLOW_TOOLS_REGISTRY[tool_class.name] = tool_class
    logger_info = f"Registered workflow tool: {tool_class.name}"
    print(logger_info)


def get_workflow_tool(tool_name: str, **kwargs):
    """
    获取工作流工具实例

    Args:
        tool_name: 工具名称
        **kwargs: 工具初始化参数

    Returns:
        工作流工具实例

    Raises:
        ValueError: 如果工具不存在
    """
    tool_class = WORKFLOW_TOOLS_REGISTRY.get(tool_name)
    if not tool_class:
        raise ValueError(f"未知工作流: {tool_name}")

    return tool_class(**kwargs)


def list_workflow_tools() -> List[str]:
    """
    列出所有工作流工具名称

    Returns:
        工作流工具名称列表
    """
    return list(WORKFLOW_TOOLS_REGISTRY.keys())


# 导出函数
__all__ = [
    "register_workflow_tool",
    "get_workflow_tool",
    "list_workflow_tools",
    "WORKFLOW_TOOLS_REGISTRY"
]

# 延迟导入工作流工具类
try:
    from .quick_trace_workflow import QuickTraceWorkflow
    register_workflow_tool(QuickTraceWorkflow)
except ImportError as e:
    print(f"Failed to import QuickTraceWorkflow: {e}")

try:
    from .standard_analysis_workflow import StandardAnalysisWorkflow
    register_workflow_tool(StandardAnalysisWorkflow)
except ImportError as e:
    print(f"Failed to import StandardAnalysisWorkflow: {e}")

try:
    from .deep_trace_workflow import DeepTraceWorkflow
    register_workflow_tool(DeepTraceWorkflow)
except ImportError as e:
    print(f"Failed to import DeepTraceWorkflow: {e}")

try:
    from .knowledge_qa_workflow import KnowledgeQAWorkflow
    register_workflow_tool(KnowledgeQAWorkflow)
except ImportError as e:
    print(f"Failed to import KnowledgeQAWorkflow: {e}")

logger.info(
    "workflow_tools_initialized",
    total_tools=len(WORKFLOW_TOOLS_REGISTRY),
    tools=list(WORKFLOW_TOOLS_REGISTRY.keys())
)

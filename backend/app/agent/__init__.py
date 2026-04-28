"""
Agent Module

ReAct Agent 系统模块导出
"""

__all__ = [
    # Main Agent
    "ReActAgent",
    "create_react_agent",

    # Memory System (Note: WorkingMemory 已合并进 HybridMemoryManager)
    "SessionMemory",
    "HybridMemoryManager",

    # Core Components
    "ReActLoop",
    "ReActPlanner",
    "ToolExecutor",
]


def __getattr__(name):
    """Lazy-load heavyweight agent entrypoints.

    Importing app.agent.runtime.* should not initialize the full tool registry.
    The full ReActAgent import is kept available for existing callers through
    the package-level attributes below.
    """
    if name in {"ReActAgent", "create_react_agent"}:
        from .react_agent import ReActAgent, create_react_agent

        globals()["ReActAgent"] = ReActAgent
        globals()["create_react_agent"] = create_react_agent
        return globals()[name]
    if name in {"SessionMemory", "HybridMemoryManager"}:
        from .memory import SessionMemory, HybridMemoryManager

        globals()["SessionMemory"] = SessionMemory
        globals()["HybridMemoryManager"] = HybridMemoryManager
        return globals()[name]
    if name in {"ReActLoop", "ReActPlanner", "ToolExecutor"}:
        from .core import ReActLoop, ReActPlanner, ToolExecutor

        globals()["ReActLoop"] = ReActLoop
        globals()["ReActPlanner"] = ReActPlanner
        globals()["ToolExecutor"] = ToolExecutor
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

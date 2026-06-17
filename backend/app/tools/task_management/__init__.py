"""
任务管理工具

提供增量任务清单状态管理能力，让LLM可以在ReAct循环中：
- 创建任务
- 更新单个任务状态
- 查看任务清单
- 读取单个任务

核心特性：
- Claude V2 风格的 TaskCreate / TaskUpdate / TaskList / TaskGet
- 增量更新，不再完整替换整个任务列表
- 同时只能1个in_progress
- housekeeping工具：不代表业务进展，不应连续重复调用
"""

from .task_tools import task_create_tool, task_get_tool, task_list_tool, task_update_tool

__all__ = [
    "task_create_tool",
    "task_update_tool",
    "task_list_tool",
    "task_get_tool",
]

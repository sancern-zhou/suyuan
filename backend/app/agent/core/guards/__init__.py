"""
守卫模块

提供任务完成守卫等安全检查机制。
"""

from .task_completion_guard import TaskCompletionGuard

__all__ = [
    "TaskCompletionGuard",
]

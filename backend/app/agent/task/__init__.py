"""
任务管理模块

提供 TodoWrite 工具使用的 TodoList 类（新架构）。
提供 TaskList 类用于专家路由器（旧架构）。
"""

# 新架构（TodoWrite工具使用）
from .todo_models import TodoList, TodoItem, TodoStatus

# 旧架构（ExpertRouterV3使用）
from .models import Task, TaskStatus, TaskTree
from .task_list import TaskList as OldTaskList
from .checkpoint_manager import CheckpointManager, Checkpoint

__all__ = [
    # 新架构
    "TodoList",
    "TodoItem",
    "TodoStatus",
    # 旧架构
    "Task",
    "TaskStatus",
    "TaskTree",
    "OldTaskList",
    "CheckpointManager",
    "Checkpoint"
]

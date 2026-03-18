"""
自动任务执行系统 - 简化版
用于个人助理场景的定时任务调度
"""

__version__ = "1.0.0"

from .service import (
    ScheduledTaskService,
    get_scheduled_task_service,
    init_service,
    start_service,
    stop_service
)
from .models import (
    ScheduledTask,
    TaskStep,
    ScheduleType,
    TaskExecution,
    ExecutionStatus
)

__all__ = [
    "ScheduledTaskService",
    "get_scheduled_task_service",
    "init_service",
    "start_service",
    "stop_service",
    "ScheduledTask",
    "TaskStep",
    "ScheduleType",
    "TaskExecution",
    "ExecutionStatus",
]

"""存储层"""
from .task_storage import TaskStorage
from .execution_storage import ExecutionStorage
from .event_claim_storage import EventClaim, EventClaimStorage
from .task_case_storage import TaskCaseStorage

__all__ = [
    "TaskStorage",
    "ExecutionStorage",
    "EventClaim",
    "EventClaimStorage",
    "TaskCaseStorage",
    "create_execution_storage",
]


def create_execution_storage() -> ExecutionStorage:
    """Return the PostgreSQL execution history.

    数据库不可用、建表失败或存量导入异常时直接抛错，
    让问题在 Worker 启动阶段真实暴露，不做 JSON 回退。
    """
    from .execution_storage_db import ExecutionStorageDB

    return ExecutionStorageDB(import_legacy=True)

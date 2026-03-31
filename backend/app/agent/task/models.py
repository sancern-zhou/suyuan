"""
任务数据模型

定义任务、任务状态、任务树等核心数据结构。
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"        # 待执行
    IN_PROGRESS = "in_progress"  # 执行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    SKIPPED = "skipped"        # 已跳过
    BLOCKED = "blocked"        # 被阻塞


class Task(BaseModel):
    """任务模型"""
    id: str
    content: str
    status: TaskStatus = TaskStatus.PENDING
    parent_id: Optional[str] = None
    children_ids: List[str] = []
    metadata: Dict[str, Any] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        use_enum_values = True


class TaskTree(BaseModel):
    """任务树模型（支持层级任务）"""
    tasks: Dict[str, Task] = {}
    root_task_ids: List[str] = []

    def add_task(self, task: Task) -> None:
        """添加任务到树"""
        self.tasks[task.id] = task
        if not task.parent_id:
            self.root_task_ids.append(task.id)

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self.tasks.get(task_id)

    def get_children(self, task_id: str) -> List[Task]:
        """获取子任务"""
        task = self.get_task(task_id)
        if not task:
            return []
        return [self.tasks[child_id] for child_id in task.children_ids if child_id in self.tasks]

    def update_task_status(self, task_id: str, status: TaskStatus, error_message: Optional[str] = None) -> bool:
        """更新任务状态"""
        task = self.get_task(task_id)
        if not task:
            return False

        task.status = status
        task.updated_at = datetime.now()

        if status == TaskStatus.COMPLETED:
            task.completed_at = datetime.now()
        elif status == TaskStatus.FAILED:
            task.error_message = error_message

        return True

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """转换为字典列表（扁平化）"""
        return [task.dict() for task in self.tasks.values()]

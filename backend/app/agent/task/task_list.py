"""
任务列表管理

提供任务列表的增删改查、状态管理、持久化等功能。
"""

import json
import uuid
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from pathlib import Path
import structlog

from .models import Task, TaskStatus, TaskTree

logger = structlog.get_logger()


class TaskList:
    """
    任务列表管理器

    功能：
    1. 任务增删改查
    2. 任务状态更新
    3. 任务依赖管理
    4. 持久化存储
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        初始化任务列表

        Args:
            storage_path: 持久化存储路径（可选）
        """
        self.tree = TaskTree()
        self.storage_path = storage_path
        self.on_task_update: Optional[Callable] = None  # 任务更新回调函数

        # 如果指定了存储路径，尝试加载
        if storage_path and Path(storage_path).exists():
            self.load()

    def add_task(
        self,
        content: str,
        parent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        添加任务

        Args:
            content: 任务内容
            parent_id: 父任务ID（可选）
            metadata: 元数据（可选）

        Returns:
            任务ID
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        now = datetime.now()

        task = Task(
            id=task_id,
            content=content,
            status=TaskStatus.PENDING,
            parent_id=parent_id,
            metadata=metadata or {},
            created_at=now,
            updated_at=now
        )

        self.tree.add_task(task)

        # 如果有父任务，更新父任务的children_ids
        if parent_id and parent_id in self.tree.tasks:
            parent = self.tree.tasks[parent_id]
            if task_id not in parent.children_ids:
                parent.children_ids.append(task_id)

        # 触发更新回调
        self._notify_update(task)

        logger.debug("task_added", task_id=task_id, content=content[:50])
        return task_id

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: Optional[str] = None
    ) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态
            error_message: 错误信息（可选）

        Returns:
            是否更新成功
        """
        success = self.tree.update_task_status(task_id, status, error_message)

        if success:
            task = self.tree.get_task(task_id)
            self._notify_update(task)

            logger.debug("task_status_updated", task_id=task_id, status=status.value)

        return success

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self.tree.get_task(task_id)

    def get_all_tasks(self) -> List[Task]:
        """获取所有任务"""
        return list(self.tree.tasks.values())

    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """按状态获取任务"""
        return [task for task in self.tree.tasks.values() if task.status == status]

    def get_pending_tasks(self) -> List[Task]:
        """获取待执行任务"""
        return self.get_tasks_by_status(TaskStatus.PENDING)

    def get_in_progress_tasks(self) -> List[Task]:
        """获取执行中任务"""
        return self.get_tasks_by_status(TaskStatus.IN_PROGRESS)

    def get_children(self, task_id: str) -> List[Task]:
        """获取子任务"""
        return self.tree.get_children(task_id)

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务

        Args:
            task_id: 任务ID

        Returns:
            是否删除成功
        """
        if task_id not in self.tree.tasks:
            return False

        # 递归删除子任务
        task = self.tree.tasks[task_id]
        for child_id in task.children_ids:
            self.delete_task(child_id)

        # 从父任务的children_ids中移除
        if task.parent_id and task.parent_id in self.tree.tasks:
            parent = self.tree.tasks[task.parent_id]
            parent.children_ids = [cid for cid in parent.children_ids if cid != task_id]

        # 删除任务
        del self.tree.tasks[task_id]

        # 如果是根任务，从root_task_ids中移除
        if task_id in self.tree.root_task_ids:
            self.tree.root_task_ids = [tid for tid in self.tree.root_task_ids if tid != task_id]

        logger.debug("task_deleted", task_id=task_id)
        return True

    def clear(self) -> None:
        """清空所有任务"""
        self.tree = TaskTree()
        logger.debug("task_list_cleared")

    def count(self) -> int:
        """任务总数"""
        return len(self.tree.tasks)

    def is_empty(self) -> bool:
        """是否为空"""
        return len(self.tree.tasks) == 0

    def is_completed(self) -> bool:
        """是否所有任务都已完成"""
        return all(task.status == TaskStatus.COMPLETED for task in self.tree.tasks.values())

    def get_progress(self) -> Dict[str, int]:
        """
        获取任务进度统计

        Returns:
            包含各状态任务数量的字典
        """
        stats = {
            "total": len(self.tree.tasks),
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "blocked": 0
        }

        for task in self.tree.tasks.values():
            stats[task.status.value] += 1

        return stats

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """转换为字典列表"""
        return self.tree.to_dict_list()

    def save(self) -> bool:
        """
        保存到持久化存储

        Returns:
            是否保存成功
        """
        if not self.storage_path:
            return False

        try:
            Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)

            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict_list(), f, ensure_ascii=False, indent=2, default=str)

            logger.debug("task_list_saved", path=self.storage_path)
            return True

        except Exception as e:
            logger.error("failed_to_save_task_list", error=str(e))
            return False

    def load(self) -> bool:
        """
        从持久化存储加载

        Returns:
            是否加载成功
        """
        if not self.storage_path or not Path(self.storage_path).exists():
            return False

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                tasks_data = json.load(f)

            self.tree = TaskTree()
            for task_data in tasks_data:
                task = Task(**task_data)
                self.tree.add_task(task)

            logger.debug("task_list_loaded", path=self.storage_path, task_count=len(tasks_data))
            return True

        except Exception as e:
            logger.error("failed_to_load_task_list", error=str(e))
            return False

    def _notify_update(self, task: Task) -> None:
        """触发任务更新回调"""
        if self.on_task_update:
            try:
                self.on_task_update(task)
            except Exception as e:
                logger.error("task_update_callback_failed", error=str(e))

    def __repr__(self) -> str:
        progress = self.get_progress()
        return f"TaskList(total={progress['total']}, completed={progress['completed']}, pending={progress['pending']})"

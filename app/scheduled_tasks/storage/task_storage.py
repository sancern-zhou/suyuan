"""
任务存储层 - JSON文件存储
"""
import json
import os
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from ..models.task import ScheduledTask


class TaskStorage:
    """任务存储"""

    def __init__(self, storage_dir: str = "backend_data_registry/scheduled_tasks"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_file = self.storage_dir / "tasks.json"

        # 初始化文件
        if not self.tasks_file.exists():
            self._write_tasks([])

    def _read_tasks(self) -> List[dict]:
        """读取所有任务"""
        try:
            with open(self.tasks_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write_tasks(self, tasks: List[dict]):
        """写入所有任务"""
        with open(self.tasks_file, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2, default=str)

    def create(self, task: ScheduledTask) -> ScheduledTask:
        """创建任务"""
        tasks = self._read_tasks()

        # 检查ID是否已存在
        if any(t["task_id"] == task.task_id for t in tasks):
            raise ValueError(f"Task ID {task.task_id} already exists")

        # 添加任务
        task_dict = task.model_dump(mode="json")
        tasks.append(task_dict)
        self._write_tasks(tasks)

        return task

    def get(self, task_id: str) -> Optional[ScheduledTask]:
        """获取任务"""
        tasks = self._read_tasks()
        for task_dict in tasks:
            if task_dict["task_id"] == task_id:
                return ScheduledTask(**task_dict)
        return None

    def list(
        self,
        enabled_only: bool = False,
        tags: Optional[List[str]] = None
    ) -> List[ScheduledTask]:
        """列出任务"""
        tasks = self._read_tasks()
        result = []

        for task_dict in tasks:
            # 过滤条件
            if enabled_only and not task_dict.get("enabled", True):
                continue

            if tags:
                task_tags = task_dict.get("tags", [])
                if not any(tag in task_tags for tag in tags):
                    continue

            result.append(ScheduledTask(**task_dict))

        return result

    def update(self, task: ScheduledTask) -> ScheduledTask:
        """更新任务"""
        tasks = self._read_tasks()
        updated = False

        for i, task_dict in enumerate(tasks):
            if task_dict["task_id"] == task.task_id:
                # 更新时间戳
                task.updated_at = datetime.now()
                tasks[i] = task.model_dump(mode="json")
                updated = True
                break

        if not updated:
            raise ValueError(f"Task {task.task_id} not found")

        self._write_tasks(tasks)
        return task

    def delete(self, task_id: str) -> bool:
        """删除任务"""
        tasks = self._read_tasks()
        original_len = len(tasks)

        tasks = [t for t in tasks if t["task_id"] != task_id]

        if len(tasks) == original_len:
            return False

        self._write_tasks(tasks)
        return True

    def update_run_stats(
        self,
        task_id: str,
        success: bool,
        next_run_at: Optional[datetime] = None
    ):
        """更新运行统计"""
        task = self.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.last_run_at = datetime.now()
        task.total_runs += 1

        if success:
            task.success_runs += 1
        else:
            task.failed_runs += 1

        if next_run_at:
            task.next_run_at = next_run_at

        self.update(task)

    def get_enabled_tasks(self) -> List[ScheduledTask]:
        """获取所有启用的任务"""
        return self.list(enabled_only=True)

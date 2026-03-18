"""
任务检查点管理器

负责任务清单的持久化、断点恢复等功能。

核心功能：
1. 任务清单持久化（JSON 文件）
2. 检查点保存与加载
3. 断点恢复
4. 与内存 TaskList 同步
"""

import json
import structlog
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

from .models import Task, TaskStatus
from .task_list import TaskList

logger = structlog.get_logger()


class TaskCheckpointManager:
    """
    任务检查点管理器

    负责任务清单的持久化存储和断点恢复。
    """

    def __init__(
        self,
        session_id: str,
        task_list: TaskList,
        base_dir: str = "backend_data_registry/checkpoints"
    ):
        """
        初始化检查点管理器

        Args:
            session_id: 会话ID
            task_list: 内存任务列表
            base_dir: 检查点存储根目录
        """
        self.session_id = session_id
        self.task_list = task_list
        self.base_dir = Path(base_dir)
        self.session_dir = self.base_dir / session_id

        # 创建会话目录
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # 文件路径
        self.tasks_file = self.session_dir / "tasks.json"
        self.checkpoints_dir = self.session_dir / "checkpoints"
        self.checkpoints_dir.mkdir(exist_ok=True)

        logger.info(
            f"TaskCheckpointManager initialized: session_id={session_id}, "
            f"dir={self.session_dir}"
        )

    async def save_checkpoint(
        self,
        checkpoint_type: str = "auto",
        metadata: Optional[Dict] = None
    ) -> str:
        """
        保存检查点

        Args:
            checkpoint_type: 检查点类型
                - "plan_created": 任务清单创建后
                - "before_task": 任务开始前
                - "after_task": 任务完成后
                - "auto": 自动保存
            metadata: 额外的元数据

        Returns:
            checkpoint_id: 检查点ID
        """
        try:
            # 生成检查点ID
            checkpoint_id = f"ckpt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

            # 获取当前会话的所有任务
            tasks = self.task_list.get_tasks(self.session_id)

            if not tasks:
                logger.warning(f"No tasks found for session {self.session_id}, skip checkpoint")
                return None

            # 构建检查点数据
            checkpoint_data = {
                "checkpoint_id": checkpoint_id,
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "type": checkpoint_type,
                "metadata": metadata or {},
                "tasks": [self._serialize_task(task) for task in tasks],
                "completed_tasks": [t.id for t in tasks if t.status == TaskStatus.COMPLETED],
                "in_progress_tasks": [t.id for t in tasks if t.status == TaskStatus.IN_PROGRESS],
                "pending_tasks": [t.id for t in tasks if t.status == TaskStatus.PENDING],
                "failed_tasks": [t.id for t in tasks if t.status == TaskStatus.FAILED]
            }

            # 保存到主任务文件（覆盖）
            with open(self.tasks_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

            # 同时保存到检查点历史（追加）
            checkpoint_file = self.checkpoints_dir / f"{checkpoint_id}.json"
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

            logger.info(
                f"Checkpoint saved: {checkpoint_id}, type={checkpoint_type}, "
                f"tasks={len(tasks)}, completed={len(checkpoint_data['completed_tasks'])}"
            )

            return checkpoint_id

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}", exc_info=True)
            raise

    async def load_checkpoint(
        self,
        checkpoint_id: Optional[str] = None
    ) -> Optional[Dict]:
        """
        加载检查点

        Args:
            checkpoint_id: 检查点ID（None 则加载最新）

        Returns:
            检查点数据，如果不存在返回 None
        """
        try:
            if checkpoint_id:
                # 加载指定检查点
                checkpoint_file = self.checkpoints_dir / f"{checkpoint_id}.json"
                if not checkpoint_file.exists():
                    logger.warning(f"Checkpoint not found: {checkpoint_id}")
                    return None
            else:
                # 加载最新检查点（从主任务文件）
                if not self.tasks_file.exists():
                    logger.info(f"No checkpoint found for session {self.session_id}")
                    return None
                checkpoint_file = self.tasks_file

            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)

            logger.info(
                f"Checkpoint loaded: {checkpoint_data.get('checkpoint_id')}, "
                f"tasks={len(checkpoint_data.get('tasks', []))}"
            )

            return checkpoint_data

        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}", exc_info=True)
            return None

    async def restore_from_checkpoint(
        self,
        checkpoint_id: Optional[str] = None
    ) -> bool:
        """
        从检查点恢复任务清单

        将检查点中的任务恢复到内存 TaskList

        Args:
            checkpoint_id: 检查点ID（None 则恢复最新）

        Returns:
            是否恢复成功
        """
        try:
            # 加载检查点
            checkpoint_data = await self.load_checkpoint(checkpoint_id)

            if not checkpoint_data:
                logger.warning("No checkpoint to restore")
                return False

            # 清除当前会话的任务（避免重复）
            self.task_list.clear_session_tasks(self.session_id)

            # 恢复任务到内存
            tasks_data = checkpoint_data.get("tasks", [])
            restored_count = 0

            for task_data in tasks_data:
                try:
                    task = self._deserialize_task(task_data)

                    # 重新创建任务（使用原有ID）
                    self.task_list.tasks[task.id] = task
                    self.task_list.session_index[self.session_id].append(task.id)

                    restored_count += 1

                except Exception as e:
                    logger.error(f"Failed to restore task {task_data.get('id')}: {e}")
                    continue

            logger.info(
                f"Checkpoint restored: {checkpoint_data.get('checkpoint_id')}, "
                f"restored={restored_count}/{len(tasks_data)} tasks"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to restore from checkpoint: {e}", exc_info=True)
            return False

    async def has_unfinished_tasks(self) -> bool:
        """
        检查是否有未完成的任务

        Returns:
            是否有未完成的任务
        """
        try:
            checkpoint_data = await self.load_checkpoint()

            if not checkpoint_data:
                return False

            # 检查是否有进行中或待执行的任务
            in_progress = checkpoint_data.get("in_progress_tasks", [])
            pending = checkpoint_data.get("pending_tasks", [])

            return len(in_progress) > 0 or len(pending) > 0

        except Exception as e:
            logger.error(f"Failed to check unfinished tasks: {e}")
            return False

    async def get_unfinished_tasks(self) -> List[Task]:
        """
        获取未完成的任务列表

        Returns:
            未完成的任务列表
        """
        try:
            checkpoint_data = await self.load_checkpoint()

            if not checkpoint_data:
                return []

            # 获取未完成的任务ID
            unfinished_ids = (
                checkpoint_data.get("in_progress_tasks", []) +
                checkpoint_data.get("pending_tasks", [])
            )

            # 从检查点数据中提取任务
            tasks_data = checkpoint_data.get("tasks", [])
            unfinished_tasks = []

            for task_data in tasks_data:
                if task_data.get("id") in unfinished_ids:
                    task = self._deserialize_task(task_data)
                    unfinished_tasks.append(task)

            return unfinished_tasks

        except Exception as e:
            logger.error(f"Failed to get unfinished tasks: {e}")
            return []

    async def clear_checkpoint(self) -> bool:
        """
        清除检查点（删除所有检查点文件）

        Returns:
            是否清除成功
        """
        try:
            # 删除主任务文件
            if self.tasks_file.exists():
                self.tasks_file.unlink()

            # 删除所有检查点历史
            for checkpoint_file in self.checkpoints_dir.glob("*.json"):
                checkpoint_file.unlink()

            logger.info(f"Checkpoint cleared for session {self.session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to clear checkpoint: {e}")
            return False

    def _serialize_task(self, task: Task) -> Dict:
        """
        序列化任务对象为字典

        Args:
            task: 任务对象

        Returns:
            任务字典
        """
        return {
            "id": task.id,
            "session_id": task.session_id,
            "subject": task.subject,
            "description": task.description,
            "status": task.status.value,
            "progress": task.progress,
            "depends_on": task.depends_on,
            "blocked_by": task.blocked_by,
            "metadata": task.metadata,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "error_message": task.error_message,
            "result_data_id": task.result_data_id,
            "checkpoint_id": task.checkpoint_id,
            "celery_task_id": task.celery_task_id,
            "expert_type": task.expert_type,
            "tool_name": task.tool_name
        }

    def _deserialize_task(self, task_data: Dict) -> Task:
        """
        反序列化字典为任务对象

        Args:
            task_data: 任务字典

        Returns:
            任务对象
        """
        # 转换时间字符串为 datetime 对象
        def parse_datetime(dt_str):
            if dt_str:
                return datetime.fromisoformat(dt_str)
            return None

        return Task(
            id=task_data["id"],
            session_id=task_data["session_id"],
            subject=task_data["subject"],
            description=task_data["description"],
            status=TaskStatus(task_data["status"]),
            progress=task_data.get("progress", 0),
            depends_on=task_data.get("depends_on", []),
            blocked_by=task_data.get("blocked_by", []),
            metadata=task_data.get("metadata", {}),
            created_at=parse_datetime(task_data.get("created_at")),
            updated_at=parse_datetime(task_data.get("updated_at")),
            started_at=parse_datetime(task_data.get("started_at")),
            completed_at=parse_datetime(task_data.get("completed_at")),
            error_message=task_data.get("error_message"),
            result_data_id=task_data.get("result_data_id"),
            checkpoint_id=task_data.get("checkpoint_id"),
            celery_task_id=task_data.get("celery_task_id"),
            expert_type=task_data.get("expert_type"),
            tool_name=task_data.get("tool_name")
        )

    async def get_checkpoint_info(self) -> Optional[Dict]:
        """
        获取检查点信息（不加载完整数据）

        Returns:
            检查点摘要信息
        """
        try:
            if not self.tasks_file.exists():
                return None

            with open(self.tasks_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)

            return {
                "checkpoint_id": checkpoint_data.get("checkpoint_id"),
                "timestamp": checkpoint_data.get("timestamp"),
                "type": checkpoint_data.get("type"),
                "total_tasks": len(checkpoint_data.get("tasks", [])),
                "completed_tasks": len(checkpoint_data.get("completed_tasks", [])),
                "in_progress_tasks": len(checkpoint_data.get("in_progress_tasks", [])),
                "pending_tasks": len(checkpoint_data.get("pending_tasks", [])),
                "failed_tasks": len(checkpoint_data.get("failed_tasks", []))
            }

        except Exception as e:
            logger.error(f"Failed to get checkpoint info: {e}")
            return None

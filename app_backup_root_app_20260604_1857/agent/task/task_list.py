"""
任务列表管理器

负责任务的创建、更新、查询等核心功能。
用于前端实时进度显示，不用于断点恢复。
"""

import structlog
from typing import Dict, List, Optional, Callable
from datetime import datetime
from collections import defaultdict

from .models import Task, TaskStatus, TaskTree, TaskSummary

logger = structlog.get_logger()


class TaskList:
    """
    任务列表管理器（内存管理）

    功能：
    1. 任务创建与状态管理
    2. 依赖关系追踪
    3. 进度计算
    4. WebSocket 实时推送
    """

    def __init__(self):
        """初始化任务列表"""
        # 任务存储：{task_id: Task}
        self.tasks: Dict[str, Task] = {}

        # 会话任务索引：{session_id: [task_ids]}
        self.session_index: Dict[str, List[str]] = defaultdict(list)

        # 状态变更回调：用于WebSocket推送
        self.on_task_update: Optional[Callable[[Task], None]] = None

        logger.info("TaskList initialized (memory-only)")

    def create_task(
        self,
        session_id: str,
        task_id: str,
        subject: str,
        description: str,
        depends_on: List[str] = None,
        expert_type: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Task:
        """
        创建任务

        Args:
            session_id: 会话ID
            task_id: 任务ID
            subject: 任务标题
            description: 任务描述
            depends_on: 依赖任务ID列表
            expert_type: 专家类型
            metadata: 元数据

        Returns:
            创建的任务对象
        """
        task = Task(
            id=task_id,
            session_id=session_id,
            subject=subject,
            description=description,
            depends_on=depends_on or [],
            expert_type=expert_type,
            metadata=metadata or {}
        )

        self.tasks[task_id] = task
        self.session_index[session_id].append(task_id)

        logger.info(f"Task created: {task_id} - {subject} (session: {session_id})")

        # 触发WebSocket推送
        if self.on_task_update:
            self.on_task_update(task)

        return task

    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[int] = None,
        error_message: Optional[str] = None,
        result_data_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Task:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态
            progress: 进度
            error_message: 错误信息
            result_data_id: 结果数据ID
            metadata: 元数据更新

        Returns:
            更新后的任务对象

        Raises:
            ValueError: 任务不存在
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task not found: {task_id}")

        task = self.tasks[task_id]
        old_status = task.status

        # 更新状态
        if status is not None:
            task.status = status

            # 状态转换时的自动操作
            if status == TaskStatus.IN_PROGRESS and old_status == TaskStatus.PENDING:
                task.mark_started()
            elif status == TaskStatus.COMPLETED:
                task.mark_completed(result_data_id)
            elif status == TaskStatus.FAILED:
                task.mark_failed(error_message or "Unknown error")

        # 更新进度
        if progress is not None:
            task.update_progress(progress)

        # 更新其他字段
        if error_message is not None:
            task.error_message = error_message
        if result_data_id is not None:
            task.result_data_id = result_data_id
        if metadata is not None:
            task.metadata.update(metadata)

        task.updated_at = datetime.now()

        logger.info(
            f"Task updated: {task_id} - {old_status.value} -> {task.status.value} "
            f"(progress: {task.progress}%)"
        )

        # 触发WebSocket推送
        if self.on_task_update:
            self.on_task_update(task)

        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取单个任务"""
        return self.tasks.get(task_id)

    def get_tasks(self, session_id: str) -> List[Task]:
        """
        获取会话的所有任务

        Args:
            session_id: 会话ID

        Returns:
            任务列表（按创建时间排序）
        """
        task_ids = self.session_index.get(session_id, [])
        tasks = [self.tasks[tid] for tid in task_ids if tid in self.tasks]
        return sorted(tasks, key=lambda t: t.created_at)

    def get_tasks_by_status(self, session_id: str, status: TaskStatus) -> List[Task]:
        """
        按状态获取任务

        Args:
            session_id: 会话ID
            status: 任务状态

        Returns:
            任务列表
        """
        return [t for t in self.get_tasks(session_id) if t.status == status]

    def get_ready_tasks(self, session_id: str) -> List[Task]:
        """
        获取可以执行的任务

        条件：
        1. 状态为pending
        2. 所有依赖任务已完成

        Args:
            session_id: 会话ID

        Returns:
            可执行任务列表
        """
        all_tasks = {t.id: t for t in self.get_tasks(session_id)}
        return [
            task for task in all_tasks.values()
            if task.is_ready_to_execute(all_tasks)
        ]

    def build_task_tree(self, session_id: str) -> Optional[TaskTree]:
        """
        构建任务树

        Args:
            session_id: 会话ID

        Returns:
            任务树根节点，如果没有任务则返回None
        """
        tasks = self.get_tasks(session_id)
        if not tasks:
            return None

        # 构建任务映射
        task_map = {t.id: t for t in tasks}

        # 查找根任务（没有依赖的任务）
        root_tasks = [t for t in tasks if not t.depends_on]

        if not root_tasks:
            # 如果没有根任务（存在循环依赖），返回第一个任务
            logger.warning(f"No root tasks found for session {session_id}, possible circular dependency")
            return TaskTree(task=tasks[0], children=[])

        # 递归构建树
        def build_subtree(task: Task) -> TaskTree:
            # 查找依赖当前任务的子任务
            children_tasks = [
                t for t in tasks
                if task.id in t.depends_on
            ]

            children = [build_subtree(child) for child in children_tasks]

            return TaskTree(task=task, children=children)

        # 如果有多个根任务，创建一个虚拟根节点
        if len(root_tasks) == 1:
            return build_subtree(root_tasks[0])
        else:
            # 多个根任务，创建虚拟根
            virtual_root = Task(
                id=f"{session_id}_root",
                session_id=session_id,
                subject="根任务",
                description="虚拟根任务",
                status=TaskStatus.IN_PROGRESS
            )
            children = [build_subtree(root) for root in root_tasks]
            return TaskTree(task=virtual_root, children=children)

    def get_task_summaries(self, session_id: str) -> List[TaskSummary]:
        """
        获取任务摘要列表

        Args:
            session_id: 会话ID

        Returns:
            任务摘要列表
        """
        tasks = self.get_tasks(session_id)
        return [
            TaskSummary(
                id=t.id,
                subject=t.subject,
                status=t.status,
                progress=t.progress,
                depends_on=t.depends_on,
                expert_type=t.expert_type,
                created_at=t.created_at,
                duration=t.get_duration()
            )
            for t in tasks
        ]

    def get_session_progress(self, session_id: str) -> Dict:
        """
        获取会话整体进度

        Args:
            session_id: 会话ID

        Returns:
            进度信息字典
        """
        tasks = self.get_tasks(session_id)
        if not tasks:
            return {
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "pending": 0,
                "failed": 0,
                "overall_progress": 0
            }

        total = len(tasks)
        completed = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
        in_progress = len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS])
        pending = len([t for t in tasks if t.status == TaskStatus.PENDING])
        failed = len([t for t in tasks if t.status == TaskStatus.FAILED])

        # 计算整体进度（加权平均）
        overall_progress = sum(t.progress for t in tasks) / total if total > 0 else 0

        return {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
            "failed": failed,
            "overall_progress": int(overall_progress)
        }

    def clear_session_tasks(self, session_id: str):
        """
        清除会话的所有任务

        Args:
            session_id: 会话ID
        """
        task_ids = self.session_index.get(session_id, [])
        for task_id in task_ids:
            if task_id in self.tasks:
                del self.tasks[task_id]

        if session_id in self.session_index:
            del self.session_index[session_id]

        logger.info(f"Cleared all tasks for session: {session_id}")

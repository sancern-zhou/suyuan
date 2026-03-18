"""
定时任务服务 - 核心服务类
整合调度器、执行器、存储层
"""
import structlog
import asyncio
from typing import Optional

from .models import ScheduledTask
from .storage import TaskStorage, ExecutionStorage
from .scheduler import SimpleScheduler
from .executor import ScheduledTaskExecutor
from .event_bus import get_event_bus  # ✅ 导入EventBus

logger = structlog.get_logger()


class ScheduledTaskService:
    """定时任务服务"""

    def __init__(self, agent_factory: Optional[callable] = None):
        # 初始化存储层
        self.task_storage = TaskStorage()
        self.execution_storage = ExecutionStorage()

        # 初始化执行器
        self.executor = ScheduledTaskExecutor(
            task_storage=self.task_storage,
            execution_storage=self.execution_storage,
            agent_factory=agent_factory
        )

        # 初始化调度器
        self.scheduler = SimpleScheduler(task_storage=self.task_storage)
        self.scheduler.set_task_callback(self.executor.execute_task)

        # 获取事件总线
        self.event_bus = get_event_bus()  # ✅ 获取EventBus实例

        self._started = False

    def _emit_event_background(self, coro):
        """在后台运行异步事件发送（不阻塞）"""
        try:
            # 获取事件循环并创建任务
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，创建任务
                logger.debug("Creating background task for event emission")
                loop.create_task(coro)
            else:
                # 如果没有运行的事件循环，使用run_until_complete
                logger.debug("Running event emission synchronously")
                loop.run_until_complete(coro)
        except RuntimeError as e:
            # 如果没有事件循环，创建新的
            logger.warning(f"No event loop available, creating new loop: {e}")
            asyncio.run(coro)
        except Exception as e:
            logger.error(f"Failed to emit event: {e}", exc_info=True)

    def start(self):
        """启动服务"""
        if self._started:
            logger.warning("ScheduledTaskService already started")
            return

        logger.info("Starting ScheduledTaskService...")
        self.scheduler.start()
        self._started = True
        logger.info("ScheduledTaskService started")

    def stop(self):
        """停止服务"""
        if not self._started:
            return

        logger.info("Stopping ScheduledTaskService...")
        self.scheduler.stop()
        self._started = False
        logger.info("ScheduledTaskService stopped")

    def create_task(self, task: ScheduledTask) -> ScheduledTask:
        """创建任务"""
        # 保存到存储
        task = self.task_storage.create(task)

        # 添加到调度器
        if self._started:
            self.scheduler.add_task(task)

        logger.info(f"Created task: {task.name} ({task.task_id})")

        # ✅ 发送WebSocket事件通知前端
        self._emit_event_background(
            self.event_bus.emit_task_created(task.task_id, task.name)
        )

        return task

    def update_task(self, task: ScheduledTask) -> ScheduledTask:
        """更新任务"""
        # 更新存储
        task = self.task_storage.update(task)

        # 更新调度器
        if self._started:
            self.scheduler.update_task(task)

        logger.info(f"Updated task: {task.name} ({task.task_id})")

        # ✅ 发送WebSocket事件通知前端
        self._emit_event_background(
            self.event_bus.emit_task_updated(task.task_id, task.name)
        )

        return task

    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        # 从调度器移除
        if self._started:
            self.scheduler.remove_task(task_id)

        # 删除执行记录
        self.execution_storage.delete_by_task(task_id)

        # 删除任务
        success = self.task_storage.delete(task_id)

        if success:
            logger.info(f"Deleted task: {task_id}")

            # ✅ 发送WebSocket事件通知前端
            self._emit_event_background(
                self.event_bus.emit_task_deleted(task_id)
            )

        return success

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """获取任务"""
        return self.task_storage.get(task_id)

    def list_tasks(self, enabled_only: bool = False):
        """列出任务"""
        return self.task_storage.list(enabled_only=enabled_only)

    def enable_task(self, task_id: str) -> ScheduledTask:
        """启用任务"""
        task = self.task_storage.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.enabled = True
        return self.update_task(task)

    def disable_task(self, task_id: str) -> ScheduledTask:
        """禁用任务"""
        task = self.task_storage.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.enabled = False
        return self.update_task(task)

    async def execute_task_now(self, task_id: str):
        """
        立即执行任务（手动触发）

        Args:
            task_id: 任务ID

        Returns:
            TaskExecution: 执行记录

        Raises:
            ValueError: 任务不存在
        """
        task = self.task_storage.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        logger.info(f"Manually executing task: {task.name} ({task_id})")

        # 发送执行开始事件
        self._emit_event_background(
            self.event_bus.emit_execution_started(
                execution_id=f"manual_{task_id}",
                task_id=task_id,
                task_name=task.name
            )
        )

        # 执行任务（异步）
        execution = await self.executor.execute_task(task)

        logger.info(f"Manual execution completed: {execution.execution_id}, status: {execution.status}")

        return execution

    def get_execution(self, execution_id: str):
        """获取执行记录"""
        return self.execution_storage.get(execution_id)

    def list_executions(self, task_id: Optional[str] = None, limit: int = 20):
        """列出执行记录"""
        if task_id:
            return self.execution_storage.list_by_task(task_id, limit=limit)
        else:
            return self.execution_storage.list_recent(limit=limit)

    def get_statistics(self, task_id: Optional[str] = None, days: int = 7):
        """获取统计信息"""
        return self.execution_storage.get_statistics(task_id=task_id, days=days)

    def get_scheduler_status(self) -> dict:
        """获取调度器状态"""
        return {
            "started": self._started,
            "running_tasks": self.scheduler.get_running_task_count(),
            "max_concurrent": self.scheduler.MAX_CONCURRENT_TASKS,
            "scheduled_tasks": self.scheduler.get_scheduled_tasks()
        }


# 全局服务实例（延迟初始化）
_service_instance: Optional[ScheduledTaskService] = None


def get_scheduled_task_service() -> ScheduledTaskService:
    """获取服务实例"""
    global _service_instance
    if _service_instance is None:
        raise RuntimeError("ScheduledTaskService not initialized. Call init_service() first.")
    return _service_instance


def init_service(agent_factory: Optional[callable] = None):
    """初始化服务"""
    global _service_instance
    if _service_instance is not None:
        logger.warning("ScheduledTaskService already initialized")
        return _service_instance

    _service_instance = ScheduledTaskService(agent_factory=agent_factory)
    logger.info("ScheduledTaskService initialized")
    return _service_instance


def start_service():
    """启动服务"""
    service = get_scheduled_task_service()
    service.start()


def stop_service():
    """停止服务"""
    service = get_scheduled_task_service()
    service.stop()

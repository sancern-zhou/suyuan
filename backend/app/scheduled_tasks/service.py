"""
定时任务服务 - 核心服务类
整合调度器、执行器、存储层
"""
import structlog
import asyncio
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .models import (
    ExecutionStatus,
    ScheduledTask,
    TaskEvent,
    TaskExecution,
    TriggerType,
)
from .storage import EventClaimStorage, TaskStorage, ExecutionStorage
from .scheduler import SimpleScheduler
from .executor import ScheduledTaskExecutor
from .event_delivery import EventTaskDelivery
from .event_output import parse_event_task_output
from .event_bus import get_event_bus  # ✅ 导入EventBus

logger = structlog.get_logger()


class EventDispatchResult(BaseModel):
    matched_task_ids: list[str] = Field(default_factory=list)
    accepted_task_ids: list[str] = Field(default_factory=list)
    duplicate_task_ids: list[str] = Field(default_factory=list)
    execution_ids: list[str] = Field(default_factory=list)


class ScheduledTaskService:
    """定时任务服务"""

    def __init__(
        self,
        agent_factory: Optional[callable] = None,
        task_storage: TaskStorage | None = None,
        execution_storage: ExecutionStorage | None = None,
        claim_storage: EventClaimStorage | None = None,
        event_delivery: EventTaskDelivery | None = None,
        conversation_persistence=None,
    ):
        # 初始化存储层
        self.task_storage = task_storage or TaskStorage()
        self.execution_storage = execution_storage or ExecutionStorage()
        self.claim_storage = claim_storage or EventClaimStorage()
        self.event_delivery = event_delivery or EventTaskDelivery()

        # 初始化执行器
        self.executor = ScheduledTaskExecutor(
            task_storage=self.task_storage,
            execution_storage=self.execution_storage,
            agent_factory=agent_factory,
            conversation_persistence=conversation_persistence,
        )

        # 初始化调度器
        self.scheduler = SimpleScheduler(task_storage=self.task_storage)
        self.scheduler.set_task_callback(self._execute_scheduled_task)

        # 获取事件总线
        self.event_bus = get_event_bus()  # ✅ 获取EventBus实例

        self._started = False
        self._event_tasks: set[asyncio.Task] = set()

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

    async def stop_async(self):
        """Stop time scheduling and wait for tracked event executions."""
        self.stop()
        if self._event_tasks:
            await asyncio.gather(*list(self._event_tasks), return_exceptions=True)

    def _track_event_task(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        self._event_tasks.add(task)
        task.add_done_callback(self._event_tasks.discard)
        return task

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
        execution = await self._execute_scheduled_task(task)

        logger.info(f"Manual execution completed: {execution.execution_id}, status: {execution.status}")

        return execution

    async def _execute_scheduled_task(self, task: ScheduledTask) -> TaskExecution:
        """Execute scheduled work and deliver its explicit broadcast result."""
        execution: TaskExecution | None = None
        try:
            recipients: list[dict[str, str]] = []
            if task.broadcast_enabled:
                recipients = await self.event_delivery.resolve_recipients(task.target_user_ids)
                if not recipients:
                    raise ValueError("no active bound WeChat recipients")

            execution = await self.executor.execute_task(task, update_stats=False)
            if execution.status != ExecutionStatus.SUCCESS:
                self.task_storage.update_run_stats(task.task_id, success=False)
                return execution

            if task.broadcast_enabled:
                response = execution.steps[-1].agent_response if execution.steps else ""
                output = parse_event_task_output(response or "")
                if not output.success:
                    raise ValueError(output.error or "scheduled Agent returned failure")
                execution.delivery_results = await self.event_delivery.deliver(
                    task=task,
                    event=None,
                    execution=execution,
                    output=output,
                    recipients=recipients,
                )
                if not execution.delivery_results or not any(
                    row.get("sent") for row in execution.delivery_results
                ):
                    raise ValueError("delivery failed for every recipient")
                self.execution_storage.update(execution)

            self.task_storage.update_run_stats(task.task_id, success=True)
            return execution
        except Exception as exc:
            logger.error(
                "scheduled_task_execution_failed",
                task_id=task.task_id,
                error=str(exc),
                exc_info=True,
            )
            if execution is None:
                now = datetime.now()
                execution = TaskExecution(
                    execution_id=self.executor._generate_execution_id(task.task_id),
                    task_id=task.task_id,
                    task_name=task.name,
                    session_id=self.executor._generate_session_id(task.task_id),
                    status=ExecutionStatus.FAILED,
                    started_at=now,
                    completed_at=now,
                    duration_seconds=0,
                    total_steps=len(task.steps),
                    trigger_type="scheduled",
                    error_message=str(exc),
                )
                self.execution_storage.create(execution)
            else:
                execution.status = ExecutionStatus.FAILED
                execution.error_message = str(exc)
                self.execution_storage.update(execution)
            self.task_storage.update_run_stats(task.task_id, success=False)
            return execution

    async def publish_event(
        self,
        event: TaskEvent,
        *,
        wait: bool = False,
        force_retry: bool = False,
        target_task_id: str | None = None,
    ) -> EventDispatchResult:
        """Match and execute enabled event tasks exactly once per event."""
        event = TaskEvent.model_validate(event)
        matching_tasks = [
            task
            for task in self.task_storage.get_enabled_tasks()
            if (target_task_id is None or task.task_id == target_task_id)
            and task.trigger_type == TriggerType.EVENT
            and task.event_type == event.event_type
            and event.matches(task.event_filters)
        ]
        result = EventDispatchResult(
            matched_task_ids=[task.task_id for task in matching_tasks]
        )

        for task in matching_tasks:
            existing = self.claim_storage.get(task.task_id, event.event_id)
            if existing and force_retry and existing.status == "running":
                timeout_seconds = sum(step.timeout_seconds for step in task.steps)
                recovered = self.claim_storage.fail_stale_running(
                    task.task_id,
                    event.event_id,
                    timeout_seconds=timeout_seconds,
                )
                if recovered:
                    existing = recovered
            if existing and force_retry and existing.status == "failed":
                claim = self.claim_storage.retry_failed(task.task_id, event.event_id)
            elif existing:
                result.duplicate_task_ids.append(task.task_id)
                continue
            else:
                claim = self.claim_storage.try_claim(task.task_id, event)
                if claim is None:
                    result.duplicate_task_ids.append(task.task_id)
                    continue

            result.accepted_task_ids.append(task.task_id)
            coroutine = self._execute_event_task(task, event, claim.claim_id)
            if wait:
                execution = await coroutine
                result.execution_ids.append(execution.execution_id)
            else:
                self._track_event_task(coroutine)

        return result

    def _create_failed_event_execution(
        self,
        task: ScheduledTask,
        event: TaskEvent,
        error: str,
    ) -> TaskExecution:
        now = datetime.now()
        execution = TaskExecution(
            execution_id=self.executor._generate_execution_id(task.task_id),
            task_id=task.task_id,
            task_name=task.name,
            session_id=self.executor._generate_session_id(task.task_id),
            status=ExecutionStatus.FAILED,
            started_at=now,
            completed_at=now,
            duration_seconds=0,
            total_steps=len(task.steps),
            trigger_type="event",
            event_id=event.event_id,
            event_type=event.event_type,
            event_attributes=event.attributes,
            error_message=error,
        )
        self.execution_storage.create(execution)
        return execution

    async def _execute_event_task(
        self,
        task: ScheduledTask,
        event: TaskEvent,
        claim_id: str,
    ) -> TaskExecution:
        self.claim_storage.mark_status(claim_id, "running")
        execution: TaskExecution | None = None
        try:
            recipients: list[dict[str, str]] = []
            if task.broadcast_enabled:
                recipients = await self.event_delivery.resolve_recipients(
                    task.target_user_ids
                )
                if not recipients:
                    execution = self._create_failed_event_execution(
                        task,
                        event,
                        "no active bound WeChat recipients",
                    )
                    self.task_storage.update_run_stats(task.task_id, success=False)
                    self.claim_storage.mark_status(
                        claim_id,
                        "failed",
                        execution_id=execution.execution_id,
                    )
                    return execution

            execution = await self.executor.execute_task(
                task,
                event=event,
                update_stats=False,
            )
            self.claim_storage.mark_status(
                claim_id,
                "running",
                execution_id=execution.execution_id,
            )
            if execution.status != ExecutionStatus.SUCCESS:
                self.task_storage.update_run_stats(task.task_id, success=False)
                self.claim_storage.mark_status(claim_id, "failed")
                return execution

            if task.broadcast_enabled:
                response = execution.steps[-1].agent_response if execution.steps else ""
                output = parse_event_task_output(response or "")
                if not output.success:
                    raise ValueError(output.error or "event Agent returned failure")
                execution.delivery_results = await self.event_delivery.deliver(
                    task=task,
                    event=event,
                    execution=execution,
                    output=output,
                    recipients=recipients,
                )
                if not execution.delivery_results:
                    raise ValueError("delivery returned no recipient results")
                if execution.delivery_results and not any(
                    row.get("sent") for row in execution.delivery_results
                ):
                    execution.error_message = (
                        "Agent completed, but delivery failed for every recipient"
                    )
                self.execution_storage.update(execution)

            self.task_storage.update_run_stats(task.task_id, success=True)
            self.claim_storage.mark_status(claim_id, "succeeded")
            return execution
        except Exception as exc:
            logger.error(
                "event_task_execution_failed",
                task_id=task.task_id,
                event_id=event.event_id,
                error=str(exc),
                exc_info=True,
            )
            if execution is None:
                execution = self._create_failed_event_execution(task, event, str(exc))
            else:
                execution.status = ExecutionStatus.FAILED
                execution.error_message = str(exc)
                self.execution_storage.update(execution)
            self.task_storage.update_run_stats(task.task_id, success=False)
            self.claim_storage.mark_status(
                claim_id,
                "failed",
                execution_id=execution.execution_id,
            )
            return execution

    async def retry_failed_delivery(self, execution_id: str) -> dict:
        """Retry only failed recipients using the stored Agent result."""
        execution = self.execution_storage.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")
        task = self.task_storage.get(execution.task_id)
        if not task or not execution.event_id:
            raise ValueError("Execution is not an event task delivery")
        claim = self.claim_storage.get(task.task_id, execution.event_id)
        if not claim:
            raise ValueError("Event claim not found")

        failed_user_ids = [
            row.get("user_id")
            for row in execution.delivery_results
            if not row.get("sent") and row.get("user_id")
        ]
        if not failed_user_ids:
            return {"success": True, "retried_user_ids": [], "delivery_results": []}

        recipients = await self.event_delivery.resolve_recipients(failed_user_ids)
        if not recipients:
            return {
                "success": False,
                "retried_user_ids": failed_user_ids,
                "delivery_results": [],
            }
        event = TaskEvent.model_validate(claim.event_snapshot)
        response = execution.steps[-1].agent_response if execution.steps else ""
        output = parse_event_task_output(response or "")
        retried = await self.event_delivery.deliver(
            task=task,
            event=event,
            execution=execution,
            output=output,
            recipients=recipients,
        )
        retried_by_user = {row.get("user_id"): row for row in retried}
        execution.delivery_results = [
            retried_by_user.get(row.get("user_id"), row)
            for row in execution.delivery_results
        ]
        self.execution_storage.update(execution)
        return {
            "success": all(row.get("sent") for row in retried),
            "retried_user_ids": failed_user_ids,
            "delivery_results": retried,
        }

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


async def stop_service_async():
    """Stop scheduling and wait for in-flight event tasks."""
    service = get_scheduled_task_service()
    await service.stop_async()

"""Subagent manager for background task execution.

Manages lifecycle of background subagents that execute long-running tasks
without blocking the main conversation.
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List

import structlog

from app.agent.react_agent import ReActAgent
from app.social.task_status_store import TaskStatusStore
from app.social.events import OutboundMessage

logger = structlog.get_logger(__name__)


class SubagentManager:
    """
    Manager for background subagent execution.

    Features:
    - Spawn background tasks without blocking main conversation
    - Task isolation (independent session_id)
    - Tool isolation (no spawn/message tools in subagent)
    - Concurrent task limit (5 per user)
    - Auto-cleanup (24 hours)
    - Completion notification via MessageBus
    """

    MAX_CONCURRENT_PER_USER = 5
    DEFAULT_TIMEOUT = 3600  # 1 hour
    MAX_ITERATIONS = 100  # Subagent iteration limit

    def __init__(
        self,
        agent: ReActAgent,
        task_store: TaskStatusStore,
        message_bus=None
    ):
        """
        Initialize subagent manager.

        Args:
            agent: Main ReActAgent instance
            task_store: Task status store
            message_bus: Optional message bus for notifications
        """
        self.agent = agent
        self.task_store = task_store
        self.message_bus = message_bus
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info("subagent_manager_initialized")

    async def start(self) -> None:
        """Start the subagent manager (cleanup task)."""
        if self._running:
            logger.warning("subagent_manager_already_running")
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info("subagent_manager_started")

    async def shutdown(self) -> None:
        """Shutdown the subagent manager."""
        self._running = False

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Wait for running tasks to complete (with timeout)
        if self._running_tasks:
            logger.info(
                "waiting_for_running_tasks",
                count=len(self._running_tasks)
            )
            tasks = list(self._running_tasks.values())
            await asyncio.wait(tasks, timeout=30.0)

        logger.info("subagent_manager_shutdown")

    async def spawn_subagent(
        self,
        task: str,
        social_user_id: str,
        origin_channel: str,
        origin_chat_id: str,
        origin_sender_id: str,
        label: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        manual_mode: str = "assistant"
    ) -> Dict[str, Any]:
        """
        Spawn a background subagent to execute a long-running task.

        Args:
            task: Task description
            social_user_id: User ID (format: {channel}:{bot_account}:{sender_id})
            origin_channel: Origin channel name
            origin_chat_id: Origin chat ID
            origin_sender_id: Origin sender ID
            label: Optional task label
            timeout: Task timeout in seconds (60-86400)
            manual_mode: Background agent mode (assistant/expert/query/code)

        Returns:
            Result dict with task_id and label
        """
        # Validate timeout
        if not (60 <= timeout <= 86400):
            timeout = self.DEFAULT_TIMEOUT

        allowed_modes = {"assistant", "expert", "query", "code"}
        if manual_mode not in allowed_modes:
            manual_mode = "assistant"

        # Check concurrent limit
        user_tasks = await self.task_store.get_user_tasks(
            social_user_id,
            status="running"
        )
        if len(user_tasks) >= self.MAX_CONCURRENT_PER_USER:
            return {
                "status": "failed",
                "success": False,
                "error": f"并发任务数量已达上限（{self.MAX_CONCURRENT_PER_USER}个），请等待现有任务完成"
            }

        # ✅ 修复：Extract bot_account from social_user_id
        # user_id 格式：{channel}:{bot_account}:{sender_id}，channel 本身可能包含 ':'
        parts = social_user_id.rsplit(":", 2)
        bot_account = parts[1] if len(parts) > 1 else "default"

        # Create task record
        task_id = await self.task_store.create_task(
            social_user_id=social_user_id,
            task=task,
            label=label,
            origin_channel=origin_channel,
            origin_chat_id=origin_chat_id,
            origin_sender_id=origin_sender_id,
            bot_account=bot_account
        )

        # Create background task
        background_task = asyncio.create_task(
            self._run_subagent(
                task_id=task_id,
                task=task,
                social_user_id=social_user_id,
                origin_info={
                    "channel": origin_channel,
                    "chat_id": origin_chat_id,
                    "sender_id": origin_sender_id
                },
                timeout=timeout,
                manual_mode=manual_mode
            )
        )

        self._running_tasks[task_id] = background_task

        # Remove from tracking when done
        background_task.add_done_callback(
            lambda t: self._running_tasks.pop(task_id, None)
        )

        logger.info(
            "subagent_spawned",
            task_id=task_id,
            social_user_id=social_user_id,
            label=label,
            manual_mode=manual_mode
        )

        return {
            "status": "success",
            "success": True,
            "task_id": task_id,
            "label": label or task[:50],
            "manual_mode": manual_mode
        }

    async def _run_subagent(
        self,
        task_id: str,
        task: str,
        social_user_id: str,
        origin_info: Dict[str, str],
        timeout: int,
        manual_mode: str
    ) -> None:
        """
        Run subagent in background.

        Args:
            task_id: Task ID
            task: Task description
            social_user_id: User ID
            origin_info: Origin information (channel, chat_id, sender_id)
            timeout: Timeout in seconds
            manual_mode: Background agent mode
        """
        try:
            # Update status to running
            await self.task_store.update_task(task_id, status="running")

            # Create independent session_id
            session_id = f"spawn_{task_id}"

            # Execute subagent with timeout
            result = await asyncio.wait_for(
                self._execute_subagent(task, session_id, manual_mode=manual_mode),
                timeout=timeout
            )

            # Update status to completed
            await self.task_store.update_task(
                task_id,
                status="completed",
                progress=1.0,
                result=result
            )

            # Send completion notification
            await self._send_completion_notification(
                task_id=task_id,
                task=task,
                result=result,
                social_user_id=social_user_id,
                origin_info=origin_info
            )

            logger.info(
                "subagent_completed",
                task_id=task_id,
                social_user_id=social_user_id
            )

        except asyncio.TimeoutError:
            error_msg = f"任务执行超时（{timeout}秒）"
            await self.task_store.update_task(
                task_id,
                status="failed",
                error=error_msg
            )

            await self._send_failure_notification(
                task_id=task_id,
                error=error_msg,
                social_user_id=social_user_id,
                origin_info=origin_info
            )

            logger.warning(
                "subagent_timeout",
                task_id=task_id,
                timeout=timeout
            )

        except Exception as e:
            error_msg = f"任务执行失败: {str(e)}"
            await self.task_store.update_task(
                task_id,
                status="failed",
                error=error_msg
            )

            await self._send_failure_notification(
                task_id=task_id,
                error=error_msg,
                social_user_id=social_user_id,
                origin_info=origin_info
            )

            logger.error(
                "subagent_failed",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )

    async def _execute_subagent(
        self,
        task: str,
        session_id: str,
        manual_mode: str = "assistant"
    ) -> str:
        """
        Execute subagent with tool isolation.

        Args:
            task: Task description
            session_id: Independent session ID
            manual_mode: Background agent mode

        Returns:
            Final answer from subagent
        """
        allowed_modes = {"assistant", "expert", "query", "code"}
        if manual_mode not in allowed_modes:
            manual_mode = "assistant"

        # Create a temporary ReActAgent with side-effect social tools removed.
        # The tool schemas are still mode-filtered by manual_mode, and this
        # executor-level filter protects against accidental or legacy calls.
        from app.agent.react_agent import ReActAgent
        from app.agent.tool_adapter import get_react_agent_tool_registry

        blocked_tools = {"spawn", "send_notification", "schedule_task"}
        full_tool_registry = get_react_agent_tool_registry()
        filtered_tool_registry = {
            name: tool
            for name, tool in full_tool_registry.items()
            if name not in blocked_tools
        }

        subagent = ReActAgent(
            tool_registry=filtered_tool_registry,
            max_iterations=self.MAX_ITERATIONS,
            enable_memory=self.agent.enable_memory,
            memory_manager=self.agent.memory_manager
        )

        events = []
        final_answer = ""

        async for event in subagent.analyze(
            user_query=task,
            session_id=session_id,
            max_iterations=self.MAX_ITERATIONS,
            manual_mode=manual_mode
        ):
            events.append(event)

            # Extract final answer
            if event.get("type") == "complete":
                final_data = event.get("data", {})
                final_answer = (
                    final_data.get("answer")
                    or final_data.get("response")
                    or final_data.get("final_answer")
                    or ""
                )
                break
            elif event.get("type") == "error":
                error_data = event.get("data", {})
                error_msg = error_data.get("error", "Unknown error")
                raise Exception(f"Subagent error: {error_msg}")

        return final_answer or "任务执行完成，但未生成结果"

    async def _send_completion_notification(
        self,
        task_id: str,
        task: str,
        result: str,
        social_user_id: str,
        origin_info: Dict[str, str]
    ) -> None:
        """
        Send completion notification to user.

        Args:
            task_id: Task ID
            task: Task description
            result: Task result
            social_user_id: User ID
            origin_info: Origin information
        """
        if not self.message_bus:
            logger.debug("no_message_bus_skip_notification", task_id=task_id)
            return

        # Get task details for elapsed time
        task_record = await self.task_store.get_task(task_id)
        if not task_record:
            logger.warning("task_not_found_for_notification", task_id=task_id)
            return

        # Calculate elapsed time
        created_at = datetime.fromisoformat(task_record["created_at"])
        completed_at = datetime.fromisoformat(task_record["completed_at"])
        elapsed_seconds = (completed_at - created_at).total_seconds()

        # Format notification message
        label = task_record.get("label", "后台任务")
        notification = f"""【后台任务完成】

任务: {label}
耗时: {elapsed_seconds:.1f}秒

结果:
{result[:500]}{'...' if len(result) > 500 else ''}

任务ID: {task_id}"""

        # Send notification
        try:
            outbound_msg = OutboundMessage(
                channel=origin_info["channel"],
                chat_id=origin_info["chat_id"],
                content=notification,
                reply_to=origin_info["sender_id"]
            )

            await self.message_bus.publish_outbound(outbound_msg)

            logger.info(
                "completion_notification_sent",
                task_id=task_id,
                social_user_id=social_user_id
            )

        except Exception as e:
            logger.error(
                "notification_send_failed",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )

    async def _send_failure_notification(
        self,
        task_id: str,
        error: str,
        social_user_id: str,
        origin_info: Dict[str, str]
    ) -> None:
        """
        Send failure notification to user.

        Args:
            task_id: Task ID
            error: Failure reason
            social_user_id: User ID
            origin_info: Origin information
        """
        if not self.message_bus:
            logger.debug("no_message_bus_skip_failure_notification", task_id=task_id)
            return

        task_record = await self.task_store.get_task(task_id)
        label = task_record.get("label", "后台任务") if task_record else "后台任务"
        safe_error = (error or "未知错误").strip()
        if len(safe_error) > 500:
            safe_error = safe_error[:500] + "..."

        notification = f"""【后台任务失败】

任务: {label}
原因: {safe_error}

任务ID: {task_id}"""

        try:
            outbound_msg = OutboundMessage(
                channel=origin_info["channel"],
                chat_id=origin_info["chat_id"],
                content=notification,
                reply_to=origin_info["sender_id"]
            )

            await self.message_bus.publish_outbound(outbound_msg)

            logger.info(
                "failure_notification_sent",
                task_id=task_id,
                social_user_id=social_user_id
            )

        except Exception as e:
            logger.error(
                "failure_notification_send_failed",
                task_id=task_id,
                error=str(e),
                exc_info=True
            )

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of old tasks."""
        while self._running:
            try:
                # Sleep for 1 hour between cleanups
                await asyncio.sleep(3600)

                # Clean up tasks older than 24 hours
                deleted_count = await self.task_store.cleanup_old_tasks(max_age_hours=24)

                if deleted_count > 0:
                    logger.info("periodic_cleanup_completed", deleted=deleted_count)

            except asyncio.CancelledError:
                logger.info("cleanup_loop_cancelled")
                break
            except Exception as e:
                logger.error(
                    "cleanup_loop_error",
                    error=str(e),
                    exc_info=True
                )

    async def get_running_tasks_count(self, social_user_id: str) -> int:
        """
        Get count of running tasks for a user.

        Args:
            social_user_id: User ID

        Returns:
            Number of running tasks
        """
        tasks = await self.task_store.get_user_tasks(
            social_user_id,
            status="running"
        )
        return len(tasks)

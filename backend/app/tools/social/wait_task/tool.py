"""Generic waiting tool for background tasks."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class WaitTaskTool(LLMTool):
    """Wait for a known background task to reach a terminal status."""

    TERMINAL_STATUSES = {"completed", "failed", "cancelled", "timeout"}

    def __init__(self) -> None:
        function_schema = {
            "name": "wait_task",
            "description": (
                "等待后台任务完成，避免反复轮询状态。适用于 cli_session 返回的 cli_task_* "
                "和 spawn 返回的 spawn_task_*；默认自动识别任务类型。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "后台任务ID，如 cli_task_... 或 spawn_task_..."
                    },
                    "task_type": {
                        "type": "string",
                        "enum": ["auto", "cli", "spawn"],
                        "description": "任务类型，默认auto。无法从ID判断时显式指定。",
                        "default": "auto"
                    },
                    "wait_timeout": {
                        "type": "number",
                        "description": "最多等待秒数，默认60，范围0-3600。",
                        "default": 60
                    },
                    "wait_interval": {
                        "type": "number",
                        "description": "检查间隔秒数，默认2，范围0.2-60。",
                        "default": 2
                    }
                },
                "required": ["task_id"]
            }
        }
        super().__init__(
            name="wait_task",
            description="等待后台任务完成，避免重复轮询状态",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        task_id: str = "",
        task_type: str = "auto",
        wait_timeout: float = 60.0,
        wait_interval: float = 2.0,
        context: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        task_id = (task_id or "").strip()
        if not task_id:
            return self._failed("缺少必填参数：task_id")

        task_type = self._resolve_task_type(task_id, task_type)
        if task_type not in {"cli", "spawn"}:
            return self._failed(f"无法识别任务类型，请显式指定 task_type：{task_id}")

        wait_timeout = self._clamp_float(wait_timeout, 0.0, 3600.0, 60.0)
        wait_interval = self._clamp_float(wait_interval, 0.2, 60.0, 2.0)
        user_key = self._get_user_key(context)

        manager = self._get_manager(task_type)
        if not manager:
            return self._failed(f"{task_type} 任务管理器未初始化")

        return await self._wait_for_task(
            manager=manager,
            task_id=task_id,
            task_type=task_type,
            user_key=user_key,
            wait_timeout=wait_timeout,
            wait_interval=wait_interval,
        )

    async def _wait_for_task(
        self,
        *,
        manager: Any,
        task_id: str,
        task_type: str,
        user_key: str,
        wait_timeout: float,
        wait_interval: float,
    ) -> Dict[str, Any]:
        max_polls = max(1, int(wait_timeout / wait_interval) + 1)
        last_task: Optional[Dict[str, Any]] = None

        for poll_index in range(max_polls):
            task = await manager.get_task(task_id)
            if not task:
                return self._failed(f"后台任务不存在: {task_id}")
            if task.get("social_user_id") and task.get("social_user_id") != user_key:
                return self._failed(f"后台任务不存在: {task_id}")

            last_task = dict(task)
            status = last_task.get("status")
            if status in self.TERMINAL_STATUSES:
                last_task["task_type"] = task_type
                last_task["wait_timed_out"] = False
                last_task["wait_polls"] = poll_index + 1
                return self._success(
                    task_id=task_id,
                    task_type=task_type,
                    task=last_task,
                    wait_timed_out=False,
                    wait_polls=poll_index + 1,
                    summary=f"后台任务 {task_id} 已结束，当前状态: {status}",
                )

            if poll_index < max_polls - 1:
                await asyncio.sleep(wait_interval)

        data = last_task or {"task_id": task_id, "status": "unknown"}
        data["task_type"] = task_type
        data["wait_timed_out"] = True
        data["wait_polls"] = max_polls
        return self._success(
            task_id=task_id,
            task_type=task_type,
            task=data,
            wait_timed_out=True,
            wait_polls=max_polls,
            summary=(
                f"等待后台任务 {task_id} 超过 {wait_timeout:g} 秒，"
                f"当前状态: {data.get('status')}"
            ),
        )

    def _get_manager(self, task_type: str) -> Any:
        if task_type == "cli":
            return self._get_cli_task_manager()
        if task_type == "spawn":
            return self._get_spawn_task_manager()
        return None

    def _get_cli_task_manager(self) -> Any:
        try:
            from app.social.cli_task_singleton import get_cli_task_manager

            manager = get_cli_task_manager()
            if manager:
                return manager
        except Exception:
            pass

        try:
            from app.social.cli_task_manager import CliTaskManager
            from app.social.cli_task_store import CliTaskStore
            from app.social.message_bus_singleton import get_message_bus

            manager = CliTaskManager(task_store=CliTaskStore(), message_bus=get_message_bus())
            from app.social.cli_task_singleton import set_cli_task_manager

            set_cli_task_manager(manager)
            return manager
        except Exception as exc:
            logger.error("wait_task_cli_manager_init_failed", error=str(exc), exc_info=True)
            return None

    def _get_spawn_task_manager(self) -> Any:
        try:
            from app.social.subagent_singleton import get_subagent_manager

            manager = get_subagent_manager()
            if manager:
                return manager
        except Exception:
            pass

        try:
            from app.social.task_status_store import TaskStatusStore

            class SpawnTaskStoreManager:
                def __init__(self) -> None:
                    self.task_store = TaskStatusStore()

                async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
                    return await self.task_store.get_task(task_id)

            return SpawnTaskStoreManager()
        except Exception as exc:
            logger.error("wait_task_spawn_manager_init_failed", error=str(exc), exc_info=True)
            return None

    def _resolve_task_type(self, task_id: str, task_type: str) -> str:
        task_type = (task_type or "auto").strip().lower()
        if task_type != "auto":
            return task_type
        if task_id.startswith("cli_task_"):
            return "cli"
        if task_id.startswith("spawn_task_"):
            return "spawn"
        return "auto"

    def _get_user_key(self, context: Any = None) -> str:
        try:
            from app.social.message_bus_singleton import (
                get_current_bot_account,
                get_current_chat_id,
                get_current_channel,
            )

            channel = get_current_channel()
            chat_id = get_current_chat_id()
            bot = get_current_bot_account() or "default"
            if channel and chat_id:
                return self._safe_name(f"{channel}:{bot}:{chat_id}")
        except Exception:
            pass

        session_id = getattr(context, "session_id", None) if context else None
        return self._safe_name(session_id or "default")

    def _clamp_float(self, value: Any, minimum: float, maximum: float, default: float) -> float:
        try:
            parsed = float(value)
        except Exception:
            return default
        return max(minimum, min(maximum, parsed))

    def _safe_name(self, value: str) -> str:
        import re

        value = str(value or "default").strip()
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
        return safe[:120] or "default"

    def _success(
        self,
        *,
        task_id: str,
        task_type: str,
        task: Dict[str, Any],
        wait_timed_out: bool,
        wait_polls: int,
        summary: str,
    ) -> Dict[str, Any]:
        return {
            "status": "success",
            "success": True,
            "metadata": {
                "tool_name": "wait_task",
                "generator": "wait_task",
                "schema_version": "1.0",
                "task_id": task_id,
                "task_type": task_type,
                "task_status": task.get("status"),
                "wait_timed_out": wait_timed_out,
                "wait_polls": wait_polls,
            },
            "data": task,
            "summary": summary,
        }

    def _failed(self, error: str) -> Dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": error,
            "metadata": {
                "tool_name": "wait_task",
                "generator": "wait_task",
                "schema_version": "1.0",
                "error_type": "VALIDATION_FAILED",
            },
            "data": None,
            "summary": f"等待后台任务失败：{error}",
        }

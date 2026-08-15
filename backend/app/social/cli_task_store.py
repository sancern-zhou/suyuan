"""Persistent status storage for background CLI tasks."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog

from app.utils.path_config import get_data_registry

logger = structlog.get_logger(__name__)


class CliTaskStore:
    """JSON-backed task store for background cli_session executions."""

    def __init__(self, json_path: str | None = None) -> None:
        self.json_path = (
            str(Path(json_path))
            if json_path
            else str(get_data_registry() / "cli_tasks.json")
        )
        self._lock = asyncio.Lock()
        Path(self.json_path).parent.mkdir(parents=True, exist_ok=True)

    async def create_task(
        self,
        *,
        social_user_id: str,
        provider: str,
        session_name: str,
        cwd: str,
        command: list[str],
        label: str | None = None,
        origin_channel: str = "unknown",
        origin_chat_id: str = "unknown",
        origin_sender_id: str = "unknown",
        timeout: int = 600,
    ) -> str:
        async with self._lock:
            now = datetime.now().isoformat()
            task_id = f"cli_task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid4())[:8]}"
            task = {
                "task_id": task_id,
                "social_user_id": social_user_id,
                "provider": provider,
                "session_name": session_name,
                "label": label or f"{provider} CLI 后台任务",
                "cwd": cwd,
                "command": command,
                "status": "pending",
                "progress": 0.0,
                "pid": None,
                "exit_code": None,
                "result": None,
                "error": None,
                "stdout_tail": "",
                "stderr_tail": "",
                "created_at": now,
                "started_at": None,
                "completed_at": None,
                "origin_channel": origin_channel,
                "origin_chat_id": origin_chat_id,
                "origin_sender_id": origin_sender_id,
                "timeout": timeout,
            }
            tasks = await self._load_all_unlocked()
            tasks.append(task)
            await self._write_all_unlocked(tasks)
            return task_id

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            for task in await self._load_all_unlocked():
                if task.get("task_id") == task_id:
                    return task
        return None

    async def list_tasks(
        self,
        *,
        social_user_id: str | None = None,
        status: str | None = None,
    ) -> List[Dict[str, Any]]:
        async with self._lock:
            tasks = await self._load_all_unlocked()
        if social_user_id:
            tasks = [task for task in tasks if task.get("social_user_id") == social_user_id]
        if status:
            tasks = [task for task in tasks if task.get("status") == status]
        tasks.sort(key=lambda task: task.get("created_at") or "", reverse=True)
        return tasks

    async def update_task(self, task_id: str, **updates: Any) -> bool:
        async with self._lock:
            tasks = await self._load_all_unlocked()
            for index, task in enumerate(tasks):
                if task.get("task_id") != task_id:
                    continue
                status = updates.get("status")
                if status == "running" and not task.get("started_at"):
                    updates.setdefault("started_at", datetime.now().isoformat())
                if status in {"completed", "failed", "cancelled", "timeout"}:
                    updates.setdefault("completed_at", datetime.now().isoformat())
                task.update({key: value for key, value in updates.items() if value is not None})
                tasks[index] = task
                await self._write_all_unlocked(tasks)
                return True
        logger.warning("cli_task_not_found_for_update", task_id=task_id)
        return False

    async def mark_stale_running_tasks(self) -> int:
        async with self._lock:
            tasks = await self._load_all_unlocked()
            count = 0
            now = datetime.now().isoformat()
            for task in tasks:
                if task.get("status") in {"pending", "running"}:
                    task["status"] = "failed"
                    task["error"] = "后端重启后任务状态已失效"
                    task["completed_at"] = now
                    count += 1
            if count:
                await self._write_all_unlocked(tasks)
            return count

    async def _load_all_unlocked(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.json_path):
            return []
        try:
            with open(self.json_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            logger.warning("cli_task_json_load_failed", path=self.json_path)
            return []

    async def _write_all_unlocked(self, tasks: List[Dict[str, Any]]) -> None:
        with open(self.json_path, "w", encoding="utf-8") as file:
            json.dump(tasks, file, ensure_ascii=False, indent=2)

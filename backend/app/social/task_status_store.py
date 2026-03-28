"""Task status persistence store for spawn tasks.

Supports both PostgreSQL (production) and JSON file (development) storage.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)


class TaskStatusStore:
    """
    Persistent storage for spawn task status.

    Features:
    - PostgreSQL primary storage with JSON file fallback
    - Thread-safe operations (asyncio.Lock)
    - Auto-cleanup of completed tasks (24 hours)
    - Indexed queries (status, social_user_id)
    """

    def __init__(self, db_manager=None, json_path: str = None):
        """
        Initialize task status store.

        Args:
            db_manager: Database manager for PostgreSQL storage
            json_path: JSON file path for fallback storage
        """
        self.db_manager = db_manager
        self.json_path = json_path or "backend_data_registry/spawn_tasks.json"
        self._lock = asyncio.Lock()
        self._use_json = db_manager is None

        # Ensure JSON directory exists
        if self._use_json:
            Path(self.json_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "task_status_store_initialized",
            storage="json" if self._use_json else "postgresql"
        )

    async def create_task(
        self,
        social_user_id: str,
        task: str,
        label: Optional[str] = None,
        origin_channel: str = "unknown",
        origin_chat_id: str = "unknown",
        origin_sender_id: str = "unknown",
        bot_account: str = "default"
    ) -> str:
        """
        Create a new spawn task.

        Args:
            social_user_id: User ID (format: {channel}:{bot_account}:{sender_id})
            task: Task description
            label: Optional task label (e.g., "PMF源解析")
            origin_channel: Origin channel name
            origin_chat_id: Origin chat ID
            origin_sender_id: Origin sender ID
            bot_account: Bot account ID

        Returns:
            Task ID (format: spawn_task_{timestamp}_{uuid})
        """
        async with self._lock:
            # Generate task ID
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid4())[:8]
            task_id = f"spawn_task_{timestamp}_{unique_id}"

            # Create task record
            task_record = {
                "task_id": task_id,
                "social_user_id": social_user_id,
                "task": task,
                "label": label or task[:50],
                "status": "pending",
                "progress": 0.0,
                "result": None,
                "error": None,
                "created_at": datetime.now().isoformat(),
                "started_at": None,
                "completed_at": None,
                "origin_channel": origin_channel,
                "origin_chat_id": origin_chat_id,
                "origin_sender_id": origin_sender_id,
                "bot_account": bot_account
            }

            # Save to storage
            if self._use_json:
                await self._save_to_json(task_record)
            else:
                await self._save_to_db(task_record)

            logger.info(
                "task_created",
                task_id=task_id,
                social_user_id=social_user_id,
                label=label
            )

            return task_id

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task by ID.

        Args:
            task_id: Task ID

        Returns:
            Task record or None if not found
        """
        if self._use_json:
            return await self._get_from_json(task_id)
        else:
            return await self._get_from_db(task_id)

    async def update_task(
        self,
        task_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        result: Optional[str] = None,
        error: Optional[str] = None
    ) -> bool:
        """
        Update task status.

        Args:
            task_id: Task ID
            status: New status (pending/running/completed/failed)
            progress: Progress value (0.0-1.0)
            result: Task result (JSON string)
            error: Error message (if failed)

        Returns:
            True if updated, False if not found
        """
        async with self._lock:
            task = await self.get_task(task_id)
            if not task:
                logger.warning("task_not_found_for_update", task_id=task_id)
                return False

            # Update fields
            if status:
                task["status"] = status
                if status == "running" and not task.get("started_at"):
                    task["started_at"] = datetime.now().isoformat()
                elif status in ["completed", "failed"]:
                    task["completed_at"] = datetime.now().isoformat()

            if progress is not None:
                task["progress"] = progress

            if result is not None:
                task["result"] = result

            if error is not None:
                task["error"] = error

            # Save updated record
            if self._use_json:
                await self._update_json(task)
            else:
                await self._update_db(task)

            logger.info(
                "task_updated",
                task_id=task_id,
                status=status,
                progress=progress
            )

            return True

    async def get_user_tasks(
        self,
        social_user_id: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all tasks for a user, optionally filtered by status.

        Args:
            social_user_id: User ID
            status: Optional status filter

        Returns:
            List of task records
        """
        if self._use_json:
            tasks = await self._get_all_from_json()
        else:
            tasks = await self._get_all_from_db(social_user_id)

        # Filter by user and status
        filtered = [
            t for t in tasks
            if t["social_user_id"] == social_user_id and
            (status is None or t["status"] == status)
        ]

        # Sort by created_at (newest first)
        filtered.sort(key=lambda x: x["created_at"], reverse=True)

        return filtered

    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """
        Delete completed tasks older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            Number of tasks deleted
        """
        async with self._lock:
            cutoff = datetime.now() - timedelta(hours=max_age_hours)

            if self._use_json:
                return await self._cleanup_json(cutoff)
            else:
                return await self._cleanup_db(cutoff)

    # ===== JSON Storage Implementation =====

    async def _save_to_json(self, task_record: Dict[str, Any]) -> None:
        """Save task to JSON file."""
        tasks = await self._load_all_json()
        tasks.append(task_record)
        await self._write_all_json(tasks)

    async def _get_from_json(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task from JSON file."""
        tasks = await self._load_all_json()
        for task in tasks:
            if task["task_id"] == task_id:
                return task
        return None

    async def _update_json(self, task_record: Dict[str, Any]) -> None:
        """Update task in JSON file."""
        tasks = await self._load_all_json()
        for i, task in enumerate(tasks):
            if task["task_id"] == task_record["task_id"]:
                tasks[i] = task_record
                break
        await self._write_all_json(tasks)

    async def _get_all_from_json(self) -> List[Dict[str, Any]]:
        """Get all tasks from JSON file."""
        return await self._load_all_json()

    async def _cleanup_json(self, cutoff: datetime) -> int:
        """Clean up old tasks from JSON file."""
        tasks = await self._load_all_json()
        original_count = len(tasks)

        # Filter out old completed tasks
        tasks = [
            t for t in tasks
            if not (
                t["status"] in ["completed", "failed"] and
                datetime.fromisoformat(t["created_at"]) < cutoff
            )
        ]

        deleted_count = original_count - len(tasks)
        if deleted_count > 0:
            await self._write_all_json(tasks)
            logger.info("old_tasks_cleaned", count=deleted_count, storage="json")

        return deleted_count

    async def _load_all_json(self) -> List[Dict[str, Any]]:
        """Load all tasks from JSON file."""
        if not os.path.exists(self.json_path):
            return []

        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning("json_load_failed", path=self.json_path)
            return []

    async def _write_all_json(self, tasks: List[Dict[str, Any]]) -> None:
        """Write all tasks to JSON file."""
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)

    # ===== PostgreSQL Storage Implementation =====

    async def _save_to_db(self, task_record: Dict[str, Any]) -> None:
        """Save task to PostgreSQL database."""
        if not self.db_manager:
            raise RuntimeError("Database manager not configured")

        query = """
            INSERT INTO spawn_tasks (
                task_id, social_user_id, task, label, status, progress,
                result, error, created_at, started_at, completed_at,
                origin_channel, origin_chat_id, origin_sender_id, bot_account
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
            )
        """

        await self.db_manager.execute(
            query,
            task_record["task_id"],
            task_record["social_user_id"],
            task_record["task"],
            task_record["label"],
            task_record["status"],
            task_record["progress"],
            task_record["result"],
            task_record["error"],
            task_record["created_at"],
            task_record["started_at"],
            task_record["completed_at"],
            task_record["origin_channel"],
            task_record["origin_chat_id"],
            task_record["origin_sender_id"],
            task_record["bot_account"]
        )

    async def _get_from_db(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task from PostgreSQL database."""
        if not self.db_manager:
            raise RuntimeError("Database manager not configured")

        query = """
            SELECT * FROM spawn_tasks WHERE task_id = $1
        """

        row = await self.db_manager.fetch_one(query, task_id)
        if not row:
            return None

        return dict(row)

    async def _update_db(self, task_record: Dict[str, Any]) -> None:
        """Update task in PostgreSQL database."""
        if not self.db_manager:
            raise RuntimeError("Database manager not configured")

        query = """
            UPDATE spawn_tasks SET
                status = $2, progress = $3, result = $4, error = $5,
                started_at = $6, completed_at = $7
            WHERE task_id = $1
        """

        await self.db_manager.execute(
            query,
            task_record["task_id"],
            task_record["status"],
            task_record["progress"],
            task_record["result"],
            task_record["error"],
            task_record["started_at"],
            task_record["completed_at"]
        )

    async def _get_all_from_db(self, social_user_id: str) -> List[Dict[str, Any]]:
        """Get all tasks for user from PostgreSQL database."""
        if not self.db_manager:
            raise RuntimeError("Database manager not configured")

        query = """
            SELECT * FROM spawn_tasks
            WHERE social_user_id = $1
            ORDER BY created_at DESC
        """

        rows = await self.db_manager.fetch_all(query, social_user_id)
        return [dict(row) for row in rows]

    async def _cleanup_db(self, cutoff: datetime) -> int:
        """Clean up old tasks from PostgreSQL database."""
        if not self.db_manager:
            raise RuntimeError("Database manager not configured")

        query = """
            DELETE FROM spawn_tasks
            WHERE status IN ('completed', 'failed')
            AND created_at < $1
        """

        result = await self.db_manager.execute(query, cutoff)
        deleted_count = result.rowcount if hasattr(result, 'rowcount') else 0

        if deleted_count > 0:
            logger.info("old_tasks_cleaned", count=deleted_count, storage="postgresql")

        return deleted_count

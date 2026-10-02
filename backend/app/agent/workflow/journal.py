"""工作流事件 journal：SQLite 持久化，替代易失的 Redis 事件流。

可观测性地基：节点 started/succeeded/failed、重试扩容、workflow 起止全部落库，
失败原因与进度随手可查（sqlite3 CLI 即可），不再依赖 session 快照或 Redis。
fail-soft：journal 写失败绝不阻断工作流执行。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import structlog

from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    task_id TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_workflow_events_wf
    ON workflow_events(workflow_id, id);
"""


class WorkflowJournal:
    """跨进程安全的 workflow 事件 journal（单 SQLite 文件）。"""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        if db_path is None:
            db_path = Path(get_data_registry()) / "workflow_journal.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_schema(self) -> None:
        try:
            with self._lock, self._connect() as conn:
                conn.executescript(_SCHEMA)
        except Exception as exc:  # noqa: BLE001
            logger.warning("workflow_journal_schema_failed", error=str(exc))

    def append(
        self,
        *,
        workflow_id: str,
        event_type: str,
        task_id: Optional[str] = None,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> None:
        ts = datetime.now().isoformat()
        serialized = json.dumps(payload or {}, ensure_ascii=False, default=str)
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO workflow_events (workflow_id, ts, event_type, task_id, payload)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (str(workflow_id), ts, str(event_type), task_id, serialized),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("workflow_journal_append_failed", event_type=event_type, error=str(exc))

    def recent(
        self,
        workflow_id: str,
        *,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """按时间正序读取某 workflow 的事件（调试与审计入口）。"""
        try:
            with self._lock, self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT ts, event_type, task_id, payload FROM workflow_events"
                    " WHERE workflow_id = ? ORDER BY id LIMIT ?",
                    (str(workflow_id), int(limit)),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            logger.warning("workflow_journal_read_failed", workflow_id=workflow_id, error=str(exc))
            return []
        events = []
        for row in rows:
            try:
                payload = json.loads(row["payload"] or "{}")
            except (TypeError, ValueError):
                payload = {}
            events.append({
                "ts": row["ts"],
                "event_type": row["event_type"],
                "task_id": row["task_id"],
                "payload": payload,
            })
        return events

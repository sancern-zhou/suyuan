from __future__ import annotations

import fcntl
import json
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import structlog

from app.utils.path_config import get_data_registry, resolve_agent_path

logger = structlog.get_logger()


class ToolStatisticsStore:
    """Persist tool execution statistics across processes."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        root = resolve_agent_path(base_dir) if base_dir else get_data_registry()
        self.base_dir = root / "tool_statistics"
        self.stats_path = self.base_dir / "tool_stats.json"
        self.lock_path = self.base_dir / "tool_stats.lock"
        self._lock = threading.Lock()

        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path.touch(exist_ok=True)

    @staticmethod
    def _default_stats() -> Dict[str, Any]:
        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "success_duration_total": 0.0,
            "avg_execution_time": 0.0,
            "last_execution_at": None,
            "updated_at": None,
        }

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self.lock_path.open("r+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_all_unlocked(self) -> Dict[str, Dict[str, Any]]:
        if not self.stats_path.exists():
            return {}
        try:
            with self.stats_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("tool_statistics_read_failed", path=str(self.stats_path), error=str(exc))
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            str(tool_name): self._normalize_stats(stats)
            for tool_name, stats in payload.items()
            if isinstance(stats, dict)
        }

    def _write_all_unlocked(self, payload: Dict[str, Dict[str, Any]]) -> None:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.base_dir,
            delete=False,
        ) as temp_file:
            json.dump(payload, temp_file, ensure_ascii=False, indent=2, default=str)
            temp_path = Path(temp_file.name)
        temp_path.replace(self.stats_path)

    def _normalize_stats(self, stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        normalized = self._default_stats()
        if not isinstance(stats, dict):
            return normalized

        normalized["total"] = int(stats.get("total", 0) or 0)
        normalized["success"] = int(stats.get("success", 0) or 0)
        normalized["failed"] = int(stats.get("failed", 0) or 0)
        stored_duration_total = stats.get("success_duration_total")
        if stored_duration_total is None:
            stored_avg = float(stats.get("avg_execution_time", 0.0) or 0.0)
            stored_duration_total = stored_avg * normalized["success"]
        normalized["success_duration_total"] = float(stored_duration_total or 0.0)
        normalized["last_execution_at"] = stats.get("last_execution_at")
        normalized["updated_at"] = stats.get("updated_at")
        if normalized["success"] > 0:
            normalized["avg_execution_time"] = normalized["success_duration_total"] / normalized["success"]
        else:
            normalized["avg_execution_time"] = float(stats.get("avg_execution_time", 0.0) or 0.0)
        return normalized

    def ensure_tool(self, tool_name: str) -> Dict[str, Any]:
        with self._lock:
            with self._locked():
                stats = self._read_all_unlocked()
                if tool_name not in stats:
                    stats[tool_name] = self._default_stats()
                    stats[tool_name]["updated_at"] = datetime.utcnow().isoformat()
                    self._write_all_unlocked(stats)
                return dict(stats.get(tool_name, self._default_stats()))

    def record_execution(
        self,
        tool_name: str,
        *,
        success: bool,
        execution_time: float | None = None,
    ) -> Dict[str, Any]:
        with self._lock:
            with self._locked():
                stats = self._read_all_unlocked()
                entry = stats.get(tool_name, self._default_stats())
                entry = self._normalize_stats(entry)
                entry["total"] += 1
                if success:
                    entry["success"] += 1
                    if execution_time is not None and execution_time >= 0:
                        entry["success_duration_total"] += float(execution_time)
                    if entry["success"] > 0:
                        entry["avg_execution_time"] = entry["success_duration_total"] / entry["success"]
                else:
                    entry["failed"] += 1
                entry["last_execution_at"] = datetime.utcnow().isoformat()
                entry["updated_at"] = entry["last_execution_at"]
                stats[tool_name] = entry
                self._write_all_unlocked(stats)
                return dict(entry)

    def get_tool_stats(self, tool_name: str) -> Dict[str, Any]:
        with self._lock:
            with self._locked():
                stats = self._read_all_unlocked()
                return dict(stats.get(tool_name, self._default_stats()))

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            with self._locked():
                stats = self._read_all_unlocked()
                return {
                    tool_name: dict(entry)
                    for tool_name, entry in stats.items()
                }


_TOOL_STATS_STORE: ToolStatisticsStore | None = None


def get_tool_statistics_store() -> ToolStatisticsStore:
    global _TOOL_STATS_STORE
    if _TOOL_STATS_STORE is None:
        _TOOL_STATS_STORE = ToolStatisticsStore()
    return _TOOL_STATS_STORE

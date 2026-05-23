"""Read-before-compute state for DataRegistry datasets.

This mirrors the read-before-edit guard used by file tools: tools that compute
from a DataRegistry id must first observe that id through read_data_registry.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class DataRegistryReadRecord:
    timestamp: float
    data_id: str
    view: Optional[str] = None
    fields: Optional[List[str]] = None
    time_range: Optional[str] = None
    jq_filter: Optional[str] = None
    list_fields: bool = False
    list_views: bool = False
    data: Any = None
    metadata: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None

    @property
    def is_data_snapshot(self) -> bool:
        return not self.list_fields and not self.list_views


class DataRegistryReadStateManager:
    DEFAULT_TTL = 3600

    def __init__(self, ttl: int = DEFAULT_TTL):
        self._state: Dict[str, DataRegistryReadRecord] = {}
        self._lock = Lock()
        self._ttl = ttl

    def set(
        self,
        data_id: str,
        *,
        view: Optional[str] = None,
        fields: Optional[List[str]] = None,
        time_range: Optional[str] = None,
        jq_filter: Optional[str] = None,
        list_fields: bool = False,
        list_views: bool = False,
        data: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        summary: Optional[str] = None,
    ) -> None:
        if not data_id:
            return

        with self._lock:
            self._state[data_id] = DataRegistryReadRecord(
                timestamp=time.time(),
                data_id=data_id,
                view=view,
                fields=list(fields) if fields else None,
                time_range=time_range,
                jq_filter=jq_filter,
                list_fields=bool(list_fields),
                list_views=bool(list_views),
                data=copy.deepcopy(data),
                metadata=copy.deepcopy(metadata) if metadata else None,
                summary=summary,
            )
            self._cleanup_expired()

    def get(self, data_id: str) -> Optional[DataRegistryReadRecord]:
        with self._lock:
            self._cleanup_expired()
            record = self._state.get(data_id)
            return copy.deepcopy(record) if record else None

    def exists(self, data_id: str) -> bool:
        return self.get(data_id) is not None

    def clear(self) -> None:
        with self._lock:
            self._state.clear()

    def _cleanup_expired(self) -> None:
        current_time = time.time()
        expired = [
            data_id
            for data_id, record in self._state.items()
            if current_time - record.timestamp > self._ttl
        ]
        for data_id in expired:
            del self._state[data_id]

        if expired:
            logger.debug(
                "data_registry_read_state_cleanup",
                expired_count=len(expired),
                remaining_count=len(self._state),
            )


_global_instance: Optional[DataRegistryReadStateManager] = None
_instance_lock = Lock()


def get_data_registry_read_state() -> DataRegistryReadStateManager:
    global _global_instance

    if _global_instance is None:
        with _instance_lock:
            if _global_instance is None:
                _global_instance = DataRegistryReadStateManager()
                logger.info(
                    "data_registry_read_state_manager_initialized",
                    ttl=_global_instance._ttl,
                )

    return _global_instance


def reset_data_registry_read_state() -> None:
    global _global_instance

    with _instance_lock:
        if _global_instance is not None:
            _global_instance.clear()
        _global_instance = None

    logger.info("data_registry_read_state_manager_reset")

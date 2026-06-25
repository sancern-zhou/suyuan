from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any


class MapProgramReceiptStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._receipts: dict[str, dict[str, dict[str, Any]]] = {}
        self._programs: dict[str, dict[str, dict[str, Any]]] = {}

    def register_pending(self, session_id: str, map_program: dict[str, Any]) -> dict[str, Any]:
        program_id = map_program.get("program_id")
        if not session_id:
            raise ValueError("session_id is required")
        if not program_id:
            raise ValueError("map_program.program_id is required")

        stored = {
            "session_id": session_id,
            "program_id": program_id,
            "status": "pending",
            "map_program": deepcopy(map_program),
            "receipt": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._programs.setdefault(session_id, {})[program_id] = stored
        return deepcopy(stored)

    def record(self, session_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
        program_id = receipt.get("program_id")
        if not session_id:
            raise ValueError("session_id is required")
        if not program_id:
            raise ValueError("receipt.program_id is required")

        stored = {
            **deepcopy(receipt),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._receipts.setdefault(session_id, {})[program_id] = stored
            program = self._programs.setdefault(session_id, {}).get(program_id)
            if program:
                program["status"] = stored.get("status") or "executed"
                program["receipt"] = deepcopy(stored)
                program["updated_at"] = stored["recorded_at"]
        return deepcopy(stored)

    def get(self, session_id: str, program_id: str) -> dict[str, Any] | None:
        with self._lock:
            receipt = self._receipts.get(session_id, {}).get(program_id)
            return deepcopy(receipt) if receipt else None

    def get_program_status(self, session_id: str, program_id: str) -> dict[str, Any] | None:
        with self._lock:
            program = self._programs.get(session_id, {}).get(program_id)
            if program:
                return deepcopy(program)
            receipt = self._receipts.get(session_id, {}).get(program_id)
            if receipt:
                return {
                    "session_id": session_id,
                    "program_id": program_id,
                    "status": receipt.get("status") or "executed",
                    "map_program": None,
                    "receipt": deepcopy(receipt),
                    "created_at": receipt.get("recorded_at"),
                    "updated_at": receipt.get("recorded_at"),
                }
            return None

    def latest_for_session(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            receipts = list(self._receipts.get(session_id, {}).values())
        receipts.sort(key=lambda item: item.get("recorded_at", ""))
        return deepcopy(receipts[-limit:])

    def clear(self) -> None:
        with self._lock:
            self._receipts.clear()
            self._programs.clear()


map_program_receipt_store = MapProgramReceiptStore()

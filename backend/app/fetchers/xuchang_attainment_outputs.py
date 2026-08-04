"""Small, stable JSON outputs for Xuchang attainment-prediction consumers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.utils.path_config import get_data_registry


OUTPUT_ROOT = get_data_registry() / "xuchang_attainment_predictions"


def prediction_output_path(kind: str) -> Path:
    if kind not in {"daily", "annual"}:
        raise ValueError(f"Unsupported attainment prediction output kind: {kind}")
    return OUTPUT_ROOT / kind / "latest.json"


def daily_notification_state_path() -> Path:
    return OUTPUT_ROOT / "daily" / "notification_state.json"


def read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.is_file():
        return default or {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default or {}
    return data if isinstance(data, dict) else (default or {})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    temp_path.replace(path)

"""Simulated Jiangsu device-control backend for demos.

Enabled with ``JIANGSU_DEVICE_CONTROL_SIMULATION=1``.  Used when the upstream
数采 QC link (``GetQCStateInfo``/``CtlDevState``) is unavailable, so the full
质控 process — 状态核查 → 待确认指令 → 平台下发 → 状态回读 → 审计 — can still be
demonstrated end to end.  Every result produced through this module is marked
as simulated so reports and panels can disclose the data source.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog

from app.tools.jiangsu.demo_data import load_device_control_states
from app.utils.path_config import resolve_agent_path

logger = structlog.get_logger(__name__)

SIMULATION_ENV = "JIANGSU_DEVICE_CONTROL_SIMULATION"
STATE_PATH_ENV = "JIANGSU_DEVICE_CONTROL_SIMULATION_STATE"

_DEFAULT_STATE_PATH = "backend/backend_data_registry_jiangsu_ops/device_control_simulation.json"


def simulation_enabled() -> bool:
    """True when the demo simulation flag is set in the environment."""
    raw = (os.getenv(SIMULATION_ENV) or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "是", "开"}


def _state_path() -> Path:
    override = (os.getenv(STATE_PATH_ENV) or "").strip()
    if override:
        return Path(override).expanduser()
    return resolve_agent_path(_DEFAULT_STATE_PATH)


def _load_overlay() -> dict[str, dict[str, str]]:
    """Read the per-station state applied by earlier simulated commands."""
    path = _state_path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("device_control_simulation_state_unreadable", path=str(path))
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_overlay(overlay: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overlay, ensure_ascii=False, indent=2), encoding="utf-8")


def seed_states(station_id: str) -> dict[str, str]:
    """Fixture defaults merged with any per-station seed."""
    dataset = load_device_control_states()
    defaults = dataset.get("defaults") if isinstance(dataset.get("defaults"), dict) else {}
    stations = dataset.get("stations") if isinstance(dataset.get("stations"), dict) else {}
    states = {str(key): str(value) for key, value in defaults.items()}
    entry = stations.get(str(station_id))
    if isinstance(entry, dict) and isinstance(entry.get("states"), dict):
        states.update({str(key): str(value) for key, value in entry["states"].items()})
    return states


def simulated_state(station_id: str) -> dict[str, str]:
    """Current simulated state: fixture seed plus commands applied this demo."""
    states = seed_states(station_id)
    overlay = _load_overlay().get(str(station_id))
    if isinstance(overlay, dict):
        states.update({str(key): str(value) for key, value in overlay.items()})
    return states


def record_state(station_id: str, changes: dict[str, str]) -> dict[str, str]:
    if not changes:
        return simulated_state(station_id)
    overlay = _load_overlay()
    current = overlay.get(str(station_id))
    if not isinstance(current, dict):
        current = {}
    current.update({str(key): str(value) for key, value in changes.items()})
    overlay[str(station_id)] = current
    try:
        _save_overlay(overlay)
    except OSError as exc:
        logger.warning("device_control_simulation_state_write_failed", error=str(exc))
    return simulated_state(station_id)


def reset_station(station_id: str) -> dict[str, str]:
    """Drop commands applied to one station (restores the fixture seed)."""
    overlay = _load_overlay()
    overlay.pop(str(station_id), None)
    try:
        _save_overlay(overlay)
    except OSError as exc:
        logger.warning("device_control_simulation_state_write_failed", error=str(exc))
    return simulated_state(station_id)


def state_envelope(station_id: str) -> dict[str, Any]:
    return {"Result": True, "Data": simulated_state(station_id)}


def command_envelope(station_id: str, changes: dict[str, str]) -> dict[str, Any]:
    record_state(station_id, changes)
    return {"Result": True, "Data": simulated_state(station_id), "Message": "演示模式：指令已受理并生效"}

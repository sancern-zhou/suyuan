"""Persistent episode aggregation for Scenario 1 station deviations."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

from app.utils.path_config import get_data_registry

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _hour(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ_SHANGHAI)
    return parsed.astimezone(TZ_SHANGHAI).replace(minute=0, second=0, microsecond=0)


class XuchangStationDeviationEpisodeService:
    """Collapse consecutive hourly deviations into one notification episode."""

    def __init__(
        self,
        *,
        output_root: Path | None = None,
        close_after_hours: int = 3,
        material_ratio_increase: float = 0.25,
        material_value_increase_ratio: float = 0.2,
    ) -> None:
        self.output_root = output_root or get_data_registry() / "xuchang_station_deviation_alerts"
        self.close_after_hours = close_after_hours
        self.material_ratio_increase = material_ratio_increase
        self.material_value_increase_ratio = material_value_increase_ratio
        self._lock = RLock()

    @property
    def state_path(self) -> Path:
        return self.output_root / "episode_state.json"

    def record(self, alert: dict[str, Any]) -> dict[str, Any]:
        occurred_at = _hour(alert["occurred_at"])
        station_id = str(alert["station_id"])
        pollutant = str(alert["target_pollutant"]).upper()
        key = f"{station_id}::{pollutant}"
        with self._lock:
            state = self._load()
            episode = state["active"].get(key)
            if episode and alert.get("event_id") in episode.get("event_ids", []):
                return {"status": "duplicate", "should_analyze": False, "episode": episode}

            if episode and occurred_at - _hour(episode["last_seen_at"]) >= timedelta(
                hours=self.close_after_hours
            ):
                self._close(state, key, episode, occurred_at, "inactivity")
                episode = None

            if episode is None:
                episode_id = (
                    f"xuchang-station-deviation-episode-{occurred_at:%Y%m%d%H}-"
                    f"{station_id}-{pollutant.lower().replace('.', '')}"
                )
                episode = {
                    "episode_id": episode_id,
                    "status": "active",
                    "city": alert.get("city", "许昌市"),
                    "station_id": station_id,
                    "station_name": alert.get("station_name") or station_id,
                    "target_pollutant": pollutant,
                    "started_at": occurred_at.isoformat(),
                    "last_seen_at": occurred_at.isoformat(),
                    "last_notified_at": occurred_at.isoformat(),
                    "event_ids": [alert.get("event_id")],
                    "hour_count": 1,
                    "notification_count": 1,
                    "peak_station_value": float(alert.get("station_value") or 0),
                    "peak_deviation_ratio": float(alert.get("deviation_ratio") or 0),
                }
                state["active"][key] = episode
                result_status = "started"
                should_analyze = True
                reason = "episode_started"
            else:
                previous_value = float(episode.get("peak_station_value") or 0)
                previous_ratio = float(episode.get("peak_deviation_ratio") or 0)
                current_value = float(alert.get("station_value") or 0)
                current_ratio = float(alert.get("deviation_ratio") or 0)
                material = (
                    current_ratio - previous_ratio >= self.material_ratio_increase
                    or (
                        previous_value > 0
                        and (current_value - previous_value) / previous_value
                        >= self.material_value_increase_ratio
                    )
                )
                episode["last_seen_at"] = occurred_at.isoformat()
                episode["event_ids"].append(alert.get("event_id"))
                episode["hour_count"] = int(episode.get("hour_count", 0)) + 1
                episode["peak_station_value"] = max(previous_value, current_value)
                episode["peak_deviation_ratio"] = max(previous_ratio, current_ratio)
                should_analyze = material
                if material:
                    episode["last_notified_at"] = occurred_at.isoformat()
                    episode["notification_count"] = int(episode.get("notification_count", 0)) + 1
                result_status = "material_update" if material else "suppressed_update"
                reason = "material_worsening" if material else "same_episode"

            state["updated_at"] = datetime.now(TZ_SHANGHAI).isoformat()
            self._save(state)
            return {
                "status": result_status,
                "reason": reason,
                "should_analyze": should_analyze,
                "episode": dict(episode),
            }

    def close_stale(self, now: datetime) -> list[dict[str, Any]]:
        now = _hour(now)
        with self._lock:
            state = self._load()
            closed = []
            for key, episode in list(state["active"].items()):
                if now - _hour(episode["last_seen_at"]) < timedelta(hours=self.close_after_hours):
                    continue
                closed.append(self._close(state, key, episode, now, "inactivity"))
            if closed:
                state["updated_at"] = datetime.now(TZ_SHANGHAI).isoformat()
                self._save(state)
            return closed

    @staticmethod
    def _close(
        state: dict[str, Any], key: str, episode: dict[str, Any], closed_at: datetime, reason: str
    ) -> dict[str, Any]:
        closed = {
            **episode,
            "status": "closed",
            "closed_at": closed_at.isoformat(),
            "closed_reason": reason,
        }
        state["history"].append(closed)
        state["active"].pop(key, None)
        return closed

    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            state = {}
        state.setdefault("schema_version", "xuchang_station_deviation_episodes/v1")
        state.setdefault("active", {})
        state.setdefault("history", [])
        state.setdefault("updated_at", None)
        return state

    def _save(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.state_path.parent, delete=False
        ) as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)
        temp_path.replace(self.state_path)

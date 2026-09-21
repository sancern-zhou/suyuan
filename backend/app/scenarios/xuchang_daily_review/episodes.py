"""Read Scenario-1 episodes as the sole alert source for the daily review.

The review never recomputes alerts. It consumes the persistent episode state
written by ``xuchang_station_deviation`` (fed by the ``alert_created`` and
``episode_closed`` events) and resolves each episode's source evidence package
for traceability.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from threading import RLock
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

SCENARIO1_ALERT_EVENT_TYPE = "xuchang.station_deviation.alert_created"
SCENARIO1_EPISODE_CLOSED_EVENT_TYPE = "xuchang.station_deviation.episode_closed"
ACCEPTED_ALERT_EVENT_TYPES = (
    SCENARIO1_ALERT_EVENT_TYPE,
    SCENARIO1_EPISODE_CLOSED_EVENT_TYPE,
)
EPISODE_EVIDENCE_SCHEMAS = {
    "xuchang_station_deviation_episode_evidence/v1",
    "xuchang_station_deviation_evidence/v2",
    "xuchang_station_deviation_evidence/v3",
}
ANALYSIS_STATE_SCHEMA = "xuchang_daily_review_analysis_state/v1"
REGIONAL_RESPONSE_PROFILE = "xuchang_regional_response_thresholds/v2"


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def normalize_hour(value: Any) -> datetime | None:
    """Normalize any timestamp to a naive Asia/Shanghai hour."""
    parsed: datetime | None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(TZ_SHANGHAI).replace(tzinfo=None)
    return parsed.replace(minute=0, second=0, microsecond=0)


def load_episode_state(state_path: Path) -> dict[str, Any] | None:
    """Load the Scenario-1 episode state; ``None`` when absent or corrupt."""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(state, dict):
        return None
    return state


def iter_episodes(state: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not state:
        return []
    episodes: list[dict[str, Any]] = []
    for bucket in ("active", "history"):
        items = state.get(bucket)
        if isinstance(items, dict):
            episodes.extend(item for item in items.values() if isinstance(item, dict))
        elif isinstance(items, list):
            episodes.extend(item for item in items if isinstance(item, dict))
    return episodes


def episode_intersects_date(episode: dict[str, Any], target_date: date) -> bool:
    start = normalize_hour(episode.get("started_at"))
    end = normalize_hour(episode.get("last_seen_at")) or start
    if start is None:
        return False
    end = max(start, end)
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1) - timedelta(hours=1)
    return start <= day_end and end >= day_start


def _canonical_version_payload(
    episode: dict[str, Any], source_evidence: dict[str, Any] | None = None
) -> str:
    payload: dict[str, Any] = {
        "episode_id": episode.get("episode_id"),
        "event_ids": list(episode.get("event_ids") or []),
        "hour_count": episode.get("hour_count"),
        "peak_station_value": episode.get("peak_station_value"),
        "peak_deviation_ratio": episode.get("peak_deviation_ratio"),
        "last_seen_at": episode.get("last_seen_at"),
        "started_at": episode.get("started_at"),
        "calculation_profile": REGIONAL_RESPONSE_PROFILE,
    }
    if source_evidence is not None:
        alerts = source_evidence.get("matched_alerts") or []
        payload["source_evidence"] = {
            "status": source_evidence.get("status"),
            "matched_alert_count": len(alerts),
            "feature_alert_count": sum(
                1 for alert in alerts
                if isinstance(alert.get("pollutant_source_features"), dict)
            ),
        }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def evidence_version(
    episode: dict[str, Any], source_evidence: dict[str, Any] | None = None
) -> str:
    return hashlib.sha256(
        _canonical_version_payload(episode, source_evidence).encode()
    ).hexdigest()[:12]


def resolve_source_evidence(
    evidence_root: Path, episode: dict[str, Any], target_date: date
) -> dict[str, Any]:
    """Locate the Scenario-1 episode evidence package by matching event ids."""
    event_ids = {str(item) for item in (episode.get("event_ids") or [])}
    if not event_ids or evidence_root is None:
        return {"status": "not_found", "path": None, "matched_alerts": []}
    best: tuple[int, str, list[dict[str, Any]]] | None = None
    for offset in (-1, 0, 1):
        day_dir = evidence_root / (target_date + timedelta(days=offset)).strftime("%Y%m%d")
        try:
            candidates = sorted(day_dir.glob("xuchang-station-episode-*.evidence.json"))
        except OSError:
            continue
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("schema_version") not in EPISODE_EVIDENCE_SCHEMAS:
                continue
            matched = [
                item.get("alert") or {}
                for item in payload.get("alerts") or []
                if isinstance(item, dict) and str(item.get("alert", {}).get("event_id")) in event_ids
            ]
            if matched and (best is None or len(matched) > best[0]):
                best = (len(matched), str(path), matched)
    if best is None:
        return {"status": "not_found", "path": None, "matched_alerts": []}
    return {"status": "found", "path": best[1], "matched_alerts": best[2]}


def _peak_from_alerts(alerts: list[dict[str, Any]]) -> tuple[str | None, float | None]:
    best_time: str | None = None
    best_value: float | None = None
    for alert in alerts:
        value = _number(alert.get("station_value"))
        if value is None:
            value = _number(alert.get("value"))
        occurred = alert.get("occurred_at")
        if value is None or occurred is None:
            continue
        if best_value is None or value > best_value:
            best_value = value
            best_time = occurred
    return best_time, best_value


def build_anchor(
    episode: dict[str, Any], target_date: date, source_evidence: dict[str, Any]
) -> dict[str, Any]:
    alerts = source_evidence.get("matched_alerts") or []
    alert_hours = sorted(
        hour for hour in (
            normalize_hour(alert.get("occurred_at")) for alert in alerts
        )
        if hour is not None
    )
    # The episode state contains suppressed alerts too; use its boundaries so
    # the review window does not shrink to only the alerts copied to evidence.
    state_start = normalize_hour(episode.get("started_at"))
    state_end = normalize_hour(episode.get("last_seen_at"))
    start = state_start or (alert_hours[0] if alert_hours else None)
    end = state_end or (alert_hours[-1] if alert_hours else None)
    if start is None:
        return {}
    end = max(start, end or start)
    peak_time, peak_value = _peak_from_alerts(alerts)
    if peak_time is None:
        peak_time = (alert_hours[-1] if alert_hours else end).isoformat()
        peak_value = _number(episode.get("peak_station_value"))
    source_features = []
    for alert in alerts:
        feature = alert.get("pollutant_source_features")
        if not isinstance(feature, dict):
            continue
        source_features.append({
            key: feature.get(key)
            for key in (
                "status", "sample_count", "required_samples", "classification",
                "components", "flags", "reason",
            )
            if key in feature
        })
    return {
        "episode_id": str(episode.get("episode_id") or ""),
        "episode_status": str(episode.get("status") or "unknown"),
        "station_id": str(episode.get("station_id") or ""),
        "station_name": episode.get("station_name") or episode.get("station_id"),
        "city": episode.get("city", "许昌市"),
        "target_pollutant": str(episode.get("target_pollutant") or "").upper(),
        "alert_type": episode.get("alert_type"),
        "measurement_granularity": episode.get("measurement_granularity"),
        "episode_start": start.isoformat(),
        "episode_end": end.isoformat(),
        "alert_hours": [hour.isoformat() for hour in alert_hours],
        "peak_time": peak_time,
        "peak_value": peak_value,
        "parent_alert_event_ids": list(episode.get("event_ids") or []),
        "hour_count": episode.get("hour_count"),
        "source_evidence_package_path": source_evidence.get("path"),
        "source_evidence_status": source_evidence.get("status"),
        "evidence_version": evidence_version(episode, source_evidence),
        "source_features": source_features,
    }


def load_episode_anchors(
    state_path: Path,
    target_date: date,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    """Return Scenario-1 episode anchors intersecting the review date."""
    from app.scenarios.xuchang_station_deviation.episode_storage_db import query_episodes

    state = load_episode_state(state_path)
    result: dict[str, Any] = {
        "status": "not_found",
        "state_path": str(state_path),
        "accepted_alert_event_types": list(ACCEPTED_ALERT_EVENT_TYPES),
        "episode_source": "none",
        "episodes": [],
    }
    database_episodes = query_episodes(target_date)
    file_episodes = iter_episodes(state)
    # Merge during rollout: the database is authoritative for IDs it has, but
    # file-only episodes remain visible until the historical backfill finishes.
    by_id = {str(item.get("episode_id")): item for item in file_episodes}
    for item in database_episodes or []:
        by_id[str(item.get("episode_id"))] = item
    if database_episodes:
        result["episode_source"] = "database" if not file_episodes else "database_plus_file"
    elif file_episodes:
        result["episode_source"] = "file_fallback"
    episodes = list(by_id.values())
    if not episodes:
        return result
    anchors = []
    for episode in episodes:
        if not episode_intersects_date(episode, target_date):
            continue
        source_evidence = (
            resolve_source_evidence(evidence_root, episode, target_date)
            if evidence_root is not None
            else {"status": "not_scanned", "path": None, "matched_alerts": []}
        )
        anchor = build_anchor(episode, target_date, source_evidence)
        if anchor:
            anchors.append(anchor)
    anchors.sort(key=lambda item: (item["episode_start"], item["station_id"]))
    result["episodes"] = anchors
    result["status"] = "found" if anchors else "not_found"
    return result


class DailyReviewAnalysisState:
    """Idempotent per-episode analysis registry with evidence versions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = RLock()

    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            state = {}
        state.setdefault("schema_version", ANALYSIS_STATE_SCHEMA)
        state.setdefault("episodes", {})
        return state

    def _save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, delete=False
        ) as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)
        temp_path.replace(self.path)

    def resolve(
        self, episode_id: str, evidence_version: str, base_analysis_id: str
    ) -> dict[str, Any]:
        """Register or dedupe an analysis; version bumps keep the parent link."""
        with self._lock:
            state = self._load()
            episodes: dict[str, Any] = state["episodes"]
            existing = episodes.get(episode_id)
            if existing:
                versions = existing.setdefault("versions", [])
                if versions and versions[-1].get("evidence_version") == evidence_version:
                    latest = versions[-1]
                    if latest.get("status") in {None, "completed", "pending"}:
                        return {
                            "analysis_status": "duplicate",
                            "analysis_id": latest["analysis_id"],
                            "parent_analysis_id": None,
                            "version_number": len(versions),
                            "result": latest.get("result"),
                            "pending": latest.get("status") == "pending",
                        }
                parent_analysis_id = versions[-1]["analysis_id"] if versions else None
                analysis_id = f"{base_analysis_id}-v{len(versions) + 1}"
                versions.append({
                    "analysis_id": analysis_id,
                    "evidence_version": evidence_version,
                    "status": "pending",
                    "created_at": datetime.now(TZ_SHANGHAI).isoformat(),
                    "parent_analysis_id": parent_analysis_id,
                })
                self._save(state)
                return {
                    "analysis_status": "new_version",
                    "analysis_id": analysis_id,
                    "parent_analysis_id": parent_analysis_id,
                    "version_number": len(versions),
                }
            episodes[episode_id] = {
                "versions": [{
                    "analysis_id": base_analysis_id,
                    "evidence_version": evidence_version,
                    "status": "pending",
                    "created_at": datetime.now(TZ_SHANGHAI).isoformat(),
                    "parent_analysis_id": None,
                }]
            }
            self._save(state)
            return {
                "analysis_status": "new",
                "analysis_id": base_analysis_id,
                "parent_analysis_id": None,
                "version_number": 1,
            }

    def complete(
        self, episode_id: str, evidence_version: str, analysis_id: str, result: dict[str, Any]
    ) -> None:
        with self._lock:
            state = self._load()
            versions = state.get("episodes", {}).get(episode_id, {}).get("versions", [])
            for version in reversed(versions):
                if (
                    version.get("analysis_id") == analysis_id
                    and version.get("evidence_version") == evidence_version
                ):
                    version["status"] = "completed"
                    version["result"] = result
                    version["completed_at"] = datetime.now(TZ_SHANGHAI).isoformat()
                    self._save(state)
                    return
            raise KeyError(f"analysis version not found: {episode_id}/{analysis_id}")

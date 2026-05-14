"""File-backed lifecycle state for pollution process events."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass
class PollutionEventStateStore:
    """Maintain event de-duplication and lifecycle state in a JSON index."""

    output_root: Path
    merge_gap_hours: int = 3
    inactive_hours: int = 6
    history_limit: int = 500

    @property
    def index_path(self) -> Path:
        return self.output_root / "event_state_index.json"

    def reconcile_event(
        self,
        event: Dict[str, Any],
        run_id: str,
        now: Optional[datetime] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Attach a lifecycle record and canonical ID to a detected event."""

        now = self._normalize_time(now or datetime.now(TZ_SHANGHAI))
        index = self._load()
        active_events = index.setdefault("active_events", [])

        candidate = dict(event)
        detection_event_id = str(candidate.get("event_id") or "")
        start_time = self._parse_time(candidate.get("time_range", {}).get("start"))
        end_time = self._parse_time(candidate.get("time_range", {}).get("end")) or start_time
        if start_time is None:
            start_time = now
        if end_time is None:
            end_time = start_time

        city = str(candidate.get("city") or "").strip()
        pollutant = self._normalize_pollutant(candidate.get("main_pollutant"))
        peak_value, peak_time = self._extract_peak(candidate, pollutant)
        matched = self._find_matching_event(active_events, city, pollutant, start_time, end_time)

        if matched is None:
            record = self._new_state_record(
                event=candidate,
                city=city,
                pollutant=pollutant,
                start_time=start_time,
                end_time=end_time,
                peak_value=peak_value,
                peak_time=peak_time,
                run_id=run_id,
                now=now,
            )
            active_events.append(record)
            transition = "new"
            state_record = record
        else:
            transition = self._merge_state_record(
                record=matched,
                event=candidate,
                start_time=start_time,
                end_time=end_time,
                peak_value=peak_value,
                peak_time=peak_time,
                run_id=run_id,
                now=now,
            )
            state_record = matched

        candidate["detection_event_id"] = detection_event_id or candidate.get("event_id")
        candidate["event_id"] = state_record["event_id"]
        candidate["event_lifecycle"] = self._lifecycle_payload(
            record=state_record,
            transition=transition,
            detection_event_id=detection_event_id,
        )

        self._save(index)
        return candidate, candidate["event_lifecycle"]

    def append_artifact(
        self,
        event_id: str,
        run_id: str,
        evidence_pack: str,
        analysis_request: str,
        event_dir: str,
        now: Optional[datetime] = None,
    ) -> None:
        """Record where the latest evidence for an active event was written."""

        now = self._normalize_time(now or datetime.now(TZ_SHANGHAI))
        index = self._load()
        record = self._find_by_event_id(index.get("active_events", []), event_id)
        if record is None:
            return

        artifacts = record.setdefault("evidence_runs", [])
        artifact = {
            "run_id": run_id,
            "evidence_pack": evidence_pack,
            "analysis_request": analysis_request,
            "event_dir": event_dir,
            "created_at": self._format_time(now),
        }
        if not any(item.get("evidence_pack") == evidence_pack for item in artifacts):
            artifacts.append(artifact)
        record["last_artifact_at"] = self._format_time(now)
        index["updated_at"] = self._format_time(now)
        self._save(index)

    def close_inactive_events(
        self,
        city: Optional[str],
        watermark: datetime,
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Move active events to ended history once no trigger has appeared."""

        now = self._normalize_time(now or datetime.now(TZ_SHANGHAI))
        watermark = self._normalize_time(watermark)
        close_before = watermark - timedelta(hours=max(1, self.inactive_hours))
        index = self._load()
        remaining = []
        ended_now: List[Dict[str, Any]] = []
        city_text = str(city).strip() if city else None

        for record in index.get("active_events", []):
            record_city = str(record.get("city") or "").strip()
            if city_text and record_city != city_text:
                remaining.append(record)
                continue

            end_time = self._parse_time(record.get("end_time"))
            if end_time is not None and end_time <= close_before:
                ended = dict(record)
                ended["status"] = "ended"
                ended["ended_at"] = self._format_time(now)
                ended["close_reason"] = f"no_trigger_for_{self.inactive_hours}_hours"
                ended_now.append(ended)
            else:
                remaining.append(record)

        if ended_now:
            history = index.setdefault("ended_events", [])
            history.extend(ended_now)
            index["ended_events"] = history[-self.history_limit :]
            index["active_events"] = remaining
            index["updated_at"] = self._format_time(now)
            self._save(index)

        return ended_now

    def load_index(self) -> Dict[str, Any]:
        """Return the current state index."""

        return self._load()

    def _new_state_record(
        self,
        event: Dict[str, Any],
        city: str,
        pollutant: str,
        start_time: datetime,
        end_time: datetime,
        peak_value: Optional[float],
        peak_time: Optional[str],
        run_id: str,
        now: datetime,
    ) -> Dict[str, Any]:
        return {
            "event_id": str(event.get("event_id")),
            "status": "ongoing",
            "city": city,
            "main_pollutant": pollutant,
            "event_type": event.get("event_type"),
            "severity": event.get("severity"),
            "confidence": event.get("confidence"),
            "start_time": self._format_time(start_time),
            "end_time": self._format_time(end_time),
            "duration_hours": self._duration_hours(start_time, end_time),
            "peak_value": peak_value,
            "peak_time": peak_time,
            "triggered_by": sorted(set(event.get("triggered_by", []))),
            "first_seen_at": self._format_time(now),
            "last_seen_at": self._format_time(now),
            "last_run_id": run_id,
            "merged_detection_ids": [str(event.get("event_id"))],
            "evidence_runs": [],
        }

    def _merge_state_record(
        self,
        record: Dict[str, Any],
        event: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        peak_value: Optional[float],
        peak_time: Optional[str],
        run_id: str,
        now: datetime,
    ) -> str:
        old_start = self._parse_time(record.get("start_time")) or start_time
        old_end = self._parse_time(record.get("end_time")) or end_time
        changed = False

        if start_time < old_start:
            record["start_time"] = self._format_time(start_time)
            old_start = start_time
            changed = True
        if end_time > old_end:
            record["end_time"] = self._format_time(end_time)
            old_end = end_time
            changed = True

        previous_peak = self._as_number(record.get("peak_value"))
        if peak_value is not None and (previous_peak is None or peak_value > previous_peak):
            record["peak_value"] = peak_value
            record["peak_time"] = peak_time
            changed = True

        previous_triggers = set(record.get("triggered_by", []))
        next_triggers = previous_triggers | set(event.get("triggered_by", []))
        if next_triggers != previous_triggers:
            record["triggered_by"] = sorted(next_triggers)
            changed = True

        detection_id = str(event.get("event_id"))
        merged_ids = record.setdefault("merged_detection_ids", [])
        if detection_id and detection_id not in merged_ids:
            merged_ids.append(detection_id)

        record["duration_hours"] = self._duration_hours(old_start, old_end)
        record["severity"] = self._max_severity(record.get("severity"), event.get("severity"))
        record["confidence"] = self._max_confidence(record.get("confidence"), event.get("confidence"))
        record["last_seen_at"] = self._format_time(now)
        record["last_run_id"] = run_id
        return "updated" if changed else "ongoing"

    def _find_matching_event(
        self,
        records: List[Dict[str, Any]],
        city: str,
        pollutant: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[Dict[str, Any]]:
        merge_gap = timedelta(hours=max(0, self.merge_gap_hours))
        for record in records:
            if record.get("status") != "ongoing":
                continue
            if str(record.get("city") or "").strip() != city:
                continue
            if self._normalize_pollutant(record.get("main_pollutant")) != pollutant:
                continue
            existing_start = self._parse_time(record.get("start_time"))
            existing_end = self._parse_time(record.get("end_time"))
            if existing_start is None or existing_end is None:
                continue
            if start_time <= existing_end + merge_gap and end_time >= existing_start - merge_gap:
                return record
        return None

    def _find_by_event_id(self, records: List[Dict[str, Any]], event_id: str) -> Optional[Dict[str, Any]]:
        for record in records:
            if record.get("event_id") == event_id:
                return record
        return None

    def _lifecycle_payload(
        self,
        record: Dict[str, Any],
        transition: str,
        detection_event_id: str,
    ) -> Dict[str, Any]:
        return {
            "status": transition,
            "canonical_event_id": record.get("event_id"),
            "detection_event_id": detection_event_id,
            "state_time_range": {
                "start": record.get("start_time"),
                "end": record.get("end_time"),
                "duration_hours": record.get("duration_hours"),
            },
            "first_seen_at": record.get("first_seen_at"),
            "last_seen_at": record.get("last_seen_at"),
            "evidence_runs_count": len(record.get("evidence_runs", [])),
            "merged_detection_count": len(record.get("merged_detection_ids", [])),
        }

    def _extract_peak(self, event: Dict[str, Any], pollutant: str) -> Tuple[Optional[float], Optional[str]]:
        for item in event.get("evidence_summary", []):
            if self._normalize_pollutant(item.get("pollutant")) == pollutant:
                value = self._as_number(item.get("peak_value") or item.get("peak"))
                return value, item.get("timestamp") or item.get("peak_time")
        return None, None

    def _load(self) -> Dict[str, Any]:
        if not self.index_path.exists():
            return {
                "schema_version": "pollution_event_state_index/v1",
                "updated_at": None,
                "active_events": [],
                "ended_events": [],
            }
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("schema_version", "pollution_event_state_index/v1")
        data.setdefault("updated_at", None)
        data.setdefault("active_events", [])
        data.setdefault("ended_events", [])
        return data

    def _save(self, index: Dict[str, Any]) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        tmp_path = self.index_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(index, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp_path.replace(self.index_path)

    def _parse_time(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return self._normalize_time(value)
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        text = text.replace("Z", "+00:00")
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f",
        ):
            try:
                return self._normalize_time(datetime.strptime(text, fmt))
            except ValueError:
                continue
        try:
            return self._normalize_time(datetime.fromisoformat(text))
        except ValueError:
            return None

    def _normalize_time(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=TZ_SHANGHAI)
        return value.astimezone(TZ_SHANGHAI)

    def _format_time(self, value: datetime) -> str:
        return self._normalize_time(value).strftime("%Y-%m-%d %H:%M:%S")

    def _duration_hours(self, start_time: datetime, end_time: datetime) -> int:
        return int((end_time - start_time).total_seconds() // 3600) + 1

    def _normalize_pollutant(self, value: Any) -> str:
        return str(value or "").replace(".", "_").upper()

    def _as_number(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                return None
            return float(value)
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return None

    def _max_severity(self, current: Any, incoming: Any) -> str:
        order = {"low": 0, "medium": 1, "high": 2}
        current_text = str(current or "low")
        incoming_text = str(incoming or "low")
        return current_text if order.get(current_text, 0) >= order.get(incoming_text, 0) else incoming_text

    def _max_confidence(self, current: Any, incoming: Any) -> str:
        order = {"low": 0, "medium": 1, "high": 2}
        current_text = str(current or "low")
        incoming_text = str(incoming or "low")
        return current_text if order.get(current_text, 0) >= order.get(incoming_text, 0) else incoming_text

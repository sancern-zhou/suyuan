"""Poll Jiangsu alarms/observations and publish evidence-backed fault events."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.air_quality_data_quality_monitor import (
    AirQualityDataQualityMonitorService,
    DataQualityMonitorConfig,
)
from app.scheduled_tasks.models.event import TaskEvent
from app.tools.jiangsu.alarm_records import JiangsuAlarmRecordsTool
from app.tools.jiangsu.fault_diagnosis import (
    JiangsuAutoInspectionTool,
    JiangsuFaultWorkOrdersTool,
    JiangsuQcTaskHistoryTool,
    JiangsuStationAlarmLogsTool,
)
from app.tools.jiangsu.operations_analysis import JiangsuStationDirectoryTool
from app.tools.jiangsu.station_data import JiangsuStationDataTool
from app.tools.jiangsu.station_type import filter_station_rows
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger(__name__)

EVENT_TYPE = "jiangsu.station_fault.detected"
POLL_SCHEDULE = os.getenv("JIANGSU_STATION_FAULT_POLL_CRON", "*/5 * * * *")
POLL_OVERLAP_MINUTES = int(os.getenv("JIANGSU_STATION_FAULT_POLL_OVERLAP_MINUTES", "15"))
MONITOR_LOOKBACK_HOURS = int(os.getenv("JIANGSU_STATION_FAULT_MONITOR_LOOKBACK_HOURS", "24"))
MONITOR_INTERVAL_MINUTES = int(os.getenv("JIANGSU_STATION_FAULT_MONITOR_INTERVAL_MINUTES", "55"))
STALE_HOURS = float(os.getenv("JIANGSU_STATION_FAULT_STALE_HOURS", "2"))
FLATLINE_POINTS = int(os.getenv("JIANGSU_STATION_FAULT_FLATLINE_POINTS", "6"))
MIN_STATION_COVERAGE = float(os.getenv("JIANGSU_STATION_FAULT_MIN_STATION_COVERAGE", "0.8"))
MAX_NEW_MONITOR_INCIDENTS_PER_POLL = int(
    os.getenv("JIANGSU_STATION_FAULT_MAX_NEW_MONITOR_INCIDENTS_PER_POLL", "20")
)
MAX_ALARM_EVENTS_PER_POLL = int(
    os.getenv("JIANGSU_STATION_FAULT_MAX_ALARM_EVENTS_PER_POLL", "3")
)
PLATFORM_ALARM_COOLDOWN_HOURS = float(
    os.getenv("JIANGSU_STATION_FAULT_ALARM_COOLDOWN_HOURS", "24")
)
MONITOR_INCIDENT_COOLDOWN_HOURS = PLATFORM_ALARM_COOLDOWN_HOURS
MONITOR_INCIDENT_KEY_VERSION = 2
EVIDENCE_MAX_TEXT_CHARS = int(os.getenv("JIANGSU_STATION_FAULT_EVIDENCE_MAX_TEXT_CHARS", "1200"))
EVIDENCE_MAX_WORK_ORDERS = int(os.getenv("JIANGSU_STATION_FAULT_EVIDENCE_MAX_WORK_ORDERS", "5"))
EVIDENCE_MAX_QC_RECORDS = int(os.getenv("JIANGSU_STATION_FAULT_EVIDENCE_MAX_QC_RECORDS", "40"))
# The ops station directory changes rarely; refresh it hourly instead of on
# every poll cycle.  A failed refresh keeps the last snapshot.
OPS_DIRECTORY_TTL_SECONDS = float(os.getenv("JIANGSU_STATION_FAULT_OPS_DIRECTORY_TTL_SECONDS", "3600"))

WEATHER_FIELDS = (
    ("windSpeed", "wind_speed"),
    ("windDirect", "wind_direction"),
    ("temperature", "temperature"),
    ("humidity", "humidity"),
    ("pressure", "pressure"),
    ("rainFall", "rainfall"),
    ("precipitation", "precipitation"),
    ("visibility", "visibility"),
)
WEATHER_TRIGGER_TYPES = {
    "flatline",
    "peer_aggregate_deviation",
    "persistent_peer_bias",
    "trend_inconsistency",
}

JIANGSU_PREFECTURE_CITIES = (
    "南京市",
    "无锡市",
    "徐州市",
    "常州市",
    "苏州市",
    "南通市",
    "连云港市",
    "淮安市",
    "盐城市",
    "扬州市",
    "镇江市",
    "泰州市",
    "宿迁市",
)

POLLUTANTS = {
    "sO2": "SO2",
    "nO2": "NO2",
    "pM10": "PM10",
    "co": "CO",
    "o3": "O3",
    "pM2_5": "PM2.5",
}
QUALITY_RULE_TYPES = {
    "daily_peer_deviation": "peer_aggregate_deviation",
    "persistent_peer_bias": "persistent_peer_bias",
    "trend_inconsistent_with_city": "trend_inconsistency",
}


def _now() -> datetime:
    return datetime.now().astimezone()


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    candidates = [text, text.replace("Z", "+00:00")]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.astimezone() if parsed.tzinfo else parsed.astimezone()
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).astimezone()
        except ValueError:
            pass
    return None


def _number(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if number == -99:
        return None
    return number


def detect_monitoring_anomalies(
    records: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    expected_station_codes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return station-level deterministic findings from a bounded hourly series."""
    now = now or _now()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        code = str(row.get("code") or row.get("stationCode") or "").strip()
        if code:
            grouped[code].append(row)

    anomalies: list[dict[str, Any]] = []
    expected = {
        str(code).strip()
        for code in expected_station_codes or []
        if str(code).strip()
    }
    if expected:
        coverage = len(expected.intersection(grouped)) / len(expected)
        if not records or coverage < MIN_STATION_COVERAGE:
            raise RuntimeError(
                f"江苏小时数据覆盖率异常：{coverage:.1%}，低于 {MIN_STATION_COVERAGE:.0%}，"
                "本轮不生成站点断数事件"
            )
        for missing_code in sorted(expected.difference(grouped)):
            anomalies.append({
                "station_code": missing_code,
                "station_name": None,
                "city_name": None,
                "district_name": None,
                "latest_time": None,
                "findings": [{
                    "type": "data_missing",
                    "severity": "major",
                    "lookback_hours": MONITOR_LOOKBACK_HOURS,
                }],
            })
    station_findings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for code, rows in grouped.items():
        rows.sort(key=lambda item: _parse_datetime(item.get("timePoint")) or datetime.min.astimezone())
        latest = rows[-1]
        latest_at = _parse_datetime(latest.get("timePoint"))
        findings = station_findings[code]
        if latest_at and now - latest_at > timedelta(hours=STALE_HOURS):
            findings.append({
                "type": "data_stale",
                "severity": "major",
                "latest_time": latest_at.isoformat(),
                "stale_hours": round((now - latest_at).total_seconds() / 3600, 2),
            })

        for key, label in POLLUTANTS.items():
            values = [_number(row.get(key)) for row in rows]
            latest_value = values[-1]
            if latest_value is not None and latest_value < 0:
                findings.append({
                    "type": "invalid_value",
                    "severity": "major",
                    "pollutant": label,
                    "value": latest_value,
                })

    peer_findings = _detect_peer_quality_findings(records)
    for code, findings in peer_findings.items():
        station_findings[code].extend(findings)
    flatline_findings = _detect_peer_confirmed_flatlines(grouped)
    for code, findings in flatline_findings.items():
        station_findings[code].extend(findings)

    existing_missing = {item["station_code"] for item in anomalies}
    for code, findings in station_findings.items():
        if not findings or code in existing_missing:
            continue
        rows = grouped[code]
        latest = rows[-1]
        anomalies.append({
            "station_code": code,
            "station_name": latest.get("name") or latest.get("positionName"),
            "city_name": latest.get("cityName"),
            "district_name": latest.get("districtName"),
            "latest_time": latest.get("timePoint"),
            "findings": findings,
        })
    return anomalies


def _detect_peer_quality_findings(
    records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Reuse the shared monitor's same-city spatial/temporal consistency rules."""
    by_city: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        code = str(row.get("code") or row.get("stationCode") or "").strip()
        city = str(row.get("cityName") or "unknown_city").strip()
        timestamp = _parse_datetime(row.get("timePoint"))
        if not code or timestamp is None:
            continue
        by_city[city].append({
            "station_name": code,
            "timestamp": timestamp.isoformat(),
            "measurements": {
                "PM10": _number(row.get("pM10")),
                "PM2_5": _number(row.get("pM2_5")),
                "NO2": _number(row.get("nO2")),
                "O3": _number(row.get("o3")),
                "CO": _number(row.get("co")),
            },
        })

    findings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for city, city_records in by_city.items():
        station_count = len({row["station_name"] for row in city_records})
        if station_count < 3:
            continue
        evaluator = AirQualityDataQualityMonitorService(
            DataQualityMonitorConfig(
                cities=[city],
                hours=MONITOR_LOOKBACK_HOURS,
                min_aggregate_points=12,
                min_trend_points=12,
                persistent_hours=6,
            ),
            rules_only=True,
        )
        for issue in evaluator.evaluate_records(city, city_records):
            code = str(issue.get("station") or "").strip()
            severity = str(issue.get("severity") or "low")
            if not code or severity == "low":
                continue
            rule_id = str(issue.get("rule_id") or "")
            issue_type = next(
                (mapped for suffix, mapped in QUALITY_RULE_TYPES.items() if rule_id.endswith(suffix)),
                "peer_quality_inconsistency",
            )
            finding = {
                "type": issue_type,
                "severity": "major" if severity == "high" else "warning",
                "rule_id": rule_id,
                "pollutant": issue.get("pollutant"),
                "message": issue.get("message"),
                "rule_basis": issue.get("rule_basis"),
            }
            for key in (
                "direction", "station_value", "peer_mean", "deviation",
                "threshold", "start", "end", "duration_hours",
                "correlation", "mean_deviation", "points",
            ):
                if key in issue:
                    finding[key] = issue[key]
            findings[code].append(finding)
    return findings


def _detect_peer_confirmed_flatlines(
    grouped: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Flag a flatline only when at least two same-city peers still vary."""
    findings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for code, rows in grouped.items():
        ordered = sorted(
            rows,
            key=lambda row: _parse_datetime(row.get("timePoint")) or datetime.min.astimezone(),
        )
        latest_rows = ordered[-FLATLINE_POINTS:]
        timestamps = [_parse_datetime(row.get("timePoint")) for row in latest_rows]
        if len(latest_rows) < FLATLINE_POINTS or any(ts is None for ts in timestamps):
            continue
        if any(
            timestamps[index] - timestamps[index - 1] > timedelta(minutes=90)
            for index in range(1, len(timestamps))
        ):
            continue
        city = str(latest_rows[-1].get("cityName") or "")
        target_times = set(timestamps)
        for key, label in POLLUTANTS.items():
            values = [_number(row.get(key)) for row in latest_rows]
            if any(value is None for value in values) or max(values) != min(values):
                continue
            varying_peers = 0
            for peer_code, peer_rows in grouped.items():
                if peer_code == code:
                    continue
                peer_city = str((peer_rows[-1] if peer_rows else {}).get("cityName") or "")
                if peer_city != city:
                    continue
                peer_values = [
                    _number(row.get(key))
                    for row in peer_rows
                    if _parse_datetime(row.get("timePoint")) in target_times
                ]
                peer_values = [value for value in peer_values if value is not None]
                if len(peer_values) >= FLATLINE_POINTS and max(peer_values) != min(peer_values):
                    varying_peers += 1
            if varying_peers >= 2:
                findings[code].append({
                    "type": "flatline",
                    "severity": "warning",
                    "pollutant": label,
                    "value": values[-1],
                    "points": FLATLINE_POINTS,
                    "varying_peer_stations": varying_peers,
                    "rule_basis": "目标站连续恒值且同城至少两个站点同期仍有变化。",
                })
    return findings


class JiangsuStationFaultEventFetcher(DataFetcher):
    """Create immutable diagnosis packages before publishing fault events."""

    def __init__(
        self,
        *,
        registry_root: Path | None = None,
        event_publisher: Callable[[TaskEvent], Awaitable[Any]] | None = None,
        clock: Callable[[], datetime] = _now,
        alarm_tool: JiangsuAlarmRecordsTool | None = None,
        station_tool: JiangsuStationDataTool | None = None,
        station_alarm_tool: JiangsuStationAlarmLogsTool | None = None,
        work_order_tool: JiangsuFaultWorkOrdersTool | None = None,
        inspection_tool: JiangsuAutoInspectionTool | None = None,
        qc_history_tool: JiangsuQcTaskHistoryTool | None = None,
        ops_directory_tool: "JiangsuStationDirectoryTool | None" = None,
    ) -> None:
        super().__init__(
            name="jiangsu_station_fault_event",
            description="轮询江苏告警与监测数据，固化诊断证据包并发布站点故障事件",
            schedule=POLL_SCHEDULE,
            version="1.0.0",
        )
        self.registry_root = registry_root or get_data_registry()
        self.output_root = self.registry_root / "station_fault_events"
        self.state_path = self.output_root / "poll_state.json"
        self.event_publisher = event_publisher or self._publish_event
        self.clock = clock
        self.alarm_tool = alarm_tool or JiangsuAlarmRecordsTool()
        self.station_tool = station_tool or JiangsuStationDataTool()
        self.station_alarm_tool = station_alarm_tool or JiangsuStationAlarmLogsTool()
        self.work_order_tool = work_order_tool or JiangsuFaultWorkOrdersTool()
        self.inspection_tool = inspection_tool or JiangsuAutoInspectionTool()
        self.qc_history_tool = qc_history_tool or JiangsuQcTaskHistoryTool()
        self.ops_directory_tool = ops_directory_tool or JiangsuStationDirectoryTool()
        self._ops_jurisdiction_snapshot: set[str] | None = None
        self._ops_directory_fetched_at = 0.0

    async def _ops_jurisdiction_codes(self) -> set[str] | None:
        """Station codes the operations platform actually manages.

        The monitoring network (air directory, ~1400 stations) is far wider
        than the operations jurisdiction (ops directory, ~290 stations).  Work
        orders can only be created for stations present in the ops directory,
        so events outside it are filtered at the source.  A transient ops
        directory failure keeps the last successful snapshot; if no snapshot
        exists, the monitoring query itself is still constrained to `省控`,
        while platform alarms remain unscoped until the directory recovers.
        """
        now = time.monotonic()
        if self._ops_jurisdiction_snapshot is not None and now - self._ops_directory_fetched_at < OPS_DIRECTORY_TTL_SECONDS:
            return self._ops_jurisdiction_snapshot
        try:
            result = await self.ops_directory_tool.execute()
            directory_rows = [item for item in result.get("data") or [] if isinstance(item, dict)]
            # The fault-event fetcher is intentionally narrower than the
            # interactive station query: it must only monitor provincial-
            # control stations managed by the operations platform.  Keep a
            # compatibility fallback for older directory deployments that do
            # not return any station-type field at all; a mixed directory is
            # filtered strictly and unknown-type rows are excluded.
            filtered_rows, type_filter_applied = filter_station_rows(directory_rows, "省控")
            codes = {
                str(item.get("stationCode") or item.get("StationCode") or "").strip()
                for item in filtered_rows
            }
            codes.discard("")
            if result.get("success") and (codes or type_filter_applied):
                self._ops_jurisdiction_snapshot = codes
                self._ops_directory_fetched_at = now
                logger.info(
                    "jiangsu_ops_directory_scoped_to_provincial_stations",
                    station_count=len(codes),
                    type_filter_applied=type_filter_applied,
                )
                return codes
            logger.warning("jiangsu_ops_directory_empty", station_count=len(codes))
        except Exception as exc:
            logger.warning("jiangsu_ops_directory_unavailable", error=str(exc))
        return self._ops_jurisdiction_snapshot

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.clock()
        state = self._read_state()
        since = now - timedelta(minutes=POLL_OVERLAP_MINUTES)
        if state.get("last_alarm_poll_at"):
            previous = _parse_datetime(state["last_alarm_poll_at"])
            if previous:
                since = previous - timedelta(minutes=POLL_OVERLAP_MINUTES)

        alarms = await self._fetch_alarms(since, now)
        jurisdiction = await self._ops_jurisdiction_codes()
        candidates: list[dict[str, Any]] = []
        filtered_alarm_records = 0
        filtered_out_of_jurisdiction = 0
        for row in alarms:
            candidate = self._alarm_candidate(row)
            if not candidate["station_code"]:
                continue
            if not self._alarm_is_eligible(row):
                filtered_alarm_records += 1
                continue
            if jurisdiction is not None and candidate["station_code"] not in jurisdiction:
                filtered_out_of_jurisdiction += 1
                continue
            if jurisdiction is not None:
                candidate["station_type"] = "省控"
            candidates.append(candidate)

        monitor_due = True
        previous_monitor = _parse_datetime(state.get("last_monitor_poll_at"))
        if previous_monitor:
            monitor_due = now - previous_monitor >= timedelta(minutes=MONITOR_INTERVAL_MINUTES)
        monitoring_records: list[dict[str, Any]] = []
        active_monitor_keys = list(state.get("active_monitor_keys") or [])
        monitor_station_codes = list(state.get("monitor_station_codes") or [])
        suppressed_monitor_events = 0
        monitor_cooldowns = {
            str(key): str(value)
            for key, value in (state.get("monitor_cooldowns") or {}).items()
            if str(key).strip() and str(value).strip()
        }
        monitor_cooldown_cutoff = now - timedelta(hours=MONITOR_INCIDENT_COOLDOWN_HOURS)
        monitor_cooldowns = {
            key: value
            for key, value in monitor_cooldowns.items()
            if (published_at := _parse_datetime(value))
            and published_at >= monitor_cooldown_cutoff
        }
        if monitor_due:
            monitoring_records, _directory_station_codes = await self._fetch_monitoring(now)
            if jurisdiction is not None:
                # Only stations under the operations platform jurisdiction may
                # produce monitoring anomalies; otherwise work-order creation
                # would fail for stations the platform does not manage.
                monitoring_records = [
                    row
                    for row in monitoring_records
                    if str(row.get("code") or row.get("stationCode") or "").strip()
                    in jurisdiction
                ]
                monitor_station_codes = [
                    code for code in monitor_station_codes if code in jurisdiction
                ]
            if not monitoring_records:
                raise RuntimeError("江苏小时数据为空，本轮不生成站点断数事件")
            observed_station_codes = sorted({
                str(row.get("code") or row.get("stationCode") or "").strip()
                for row in monitoring_records
                if str(row.get("code") or row.get("stationCode") or "").strip()
            })
            monitor_candidates = [
                self._monitor_candidate(item)
                for item in detect_monitoring_anomalies(
                    monitoring_records,
                    now=now,
                    # The station directory contains enabled stations that do
                    # not necessarily publish station-hour data.  Establish a
                    # baseline from stations actually observed on the first
                    # successful poll, then detect later disappearances from
                    # that baseline.  This avoids a first-run false-alarm
                    # storm while retaining durable missing-data detection.
                    expected_station_codes=monitor_station_codes or None,
                )
            ]
            for candidate in monitor_candidates:
                candidate["station_type"] = "省控"
            monitor_station_codes = sorted({
                *monitor_station_codes,
                *observed_station_codes,
            })
            # Persist the trustworthy observed-station baseline together with
            # every per-event checkpoint below.  Keep active_monitor_keys for
            # the final commit so an interrupted run still republishes any
            # anomaly whose evidence package was not completed.
            state["monitor_station_codes"] = monitor_station_codes
            previous_active = set(active_monitor_keys)
            current_by_key: dict[str, dict[str, Any]] = {}
            for candidate in monitor_candidates:
                incident_key = self._monitor_incident_key(candidate)
                current_by_key[incident_key] = candidate
            current_active = sorted(current_by_key)
            new_incident_keys = sorted(set(current_active) - previous_active)
            if state.get("monitor_incident_key_version") != MONITOR_INCIDENT_KEY_VERSION:
                suppressed_monitor_events = len(new_incident_keys)
                logger.warning(
                    "jiangsu_station_fault_monitor_baseline_initialized",
                    incident_key_version=MONITOR_INCIDENT_KEY_VERSION,
                    active_incidents=len(current_active),
                    suppressed_events=suppressed_monitor_events,
                )
            elif len(new_incident_keys) > MAX_NEW_MONITOR_INCIDENTS_PER_POLL:
                suppressed_monitor_events = len(new_incident_keys)
                logger.error(
                    "jiangsu_station_fault_event_storm_suppressed",
                    new_incidents=len(new_incident_keys),
                    max_new_incidents=MAX_NEW_MONITOR_INCIDENTS_PER_POLL,
                    active_incidents=len(current_active),
                )
            else:
                for incident_key in new_incident_keys:
                    last_published_at = _parse_datetime(monitor_cooldowns.get(incident_key))
                    if (
                        last_published_at
                        and now - last_published_at
                        < timedelta(hours=MONITOR_INCIDENT_COOLDOWN_HOURS)
                    ):
                        suppressed_monitor_events += 1
                        continue
                    candidate = current_by_key[incident_key]
                    candidate["incident_started_at"] = now.isoformat()
                    candidates.append(candidate)
            active_monitor_keys = current_active
            state["monitor_incident_key_version"] = MONITOR_INCIDENT_KEY_VERSION

        processed_order = list(dict.fromkeys(state.get("processed_fingerprints") or []))
        processed = set(processed_order)
        published = 0
        published_alarm_events = 0
        deferred_alarm_events = 0
        suppressed_alarm_events = 0
        alarm_cooldowns = {
            str(key): str(value)
            for key, value in (state.get("alarm_cooldowns") or {}).items()
            if str(key).strip() and str(value).strip()
        }
        cooldown_cutoff = now - timedelta(hours=PLATFORM_ALARM_COOLDOWN_HOURS)
        alarm_cooldowns = {
            key: value
            for key, value in alarm_cooldowns.items()
            if (published_at := _parse_datetime(value)) and published_at >= cooldown_cutoff
        }
        for candidate in candidates:
            fingerprint = self._fingerprint(candidate)
            is_platform_alarm = candidate.get("source_type") == "platform_alarm"
            alarm_incident_key = None
            if is_platform_alarm:
                # Keep the same event ID during one cooldown window, but make
                # a post-cooldown reminder a new downstream event even when
                # the upstream system reuses its original record ID.
                cooldown_seconds = max(1.0, PLATFORM_ALARM_COOLDOWN_HOURS * 3600)
                fingerprint = hashlib.sha256(
                    f"{fingerprint}:{int(now.timestamp() // cooldown_seconds)}".encode("utf-8")
                ).hexdigest()
                alarm_incident_key = self._alarm_incident_key(candidate)
                last_published_at = _parse_datetime(alarm_cooldowns.get(alarm_incident_key))
                if (
                    last_published_at
                    and now - last_published_at
                    < timedelta(hours=PLATFORM_ALARM_COOLDOWN_HOURS)
                ):
                    suppressed_alarm_events += 1
                    if fingerprint not in processed:
                        processed.add(fingerprint)
                        processed_order.append(fingerprint)
                    continue
            elif fingerprint in processed:
                continue
            if (
                candidate.get("source_type") == "platform_alarm"
                and published_alarm_events >= MAX_ALARM_EVENTS_PER_POLL
            ):
                deferred_alarm_events += 1
                continue
            station_rows = [
                row
                for row in monitoring_records
                if str(row.get("code") or row.get("stationCode") or "").strip()
                == candidate["station_code"]
            ]
            event = await self._write_event_package(candidate, station_rows, now, fingerprint)
            await self.event_publisher(event)
            processed.add(fingerprint)
            processed_order.append(fingerprint)
            published += 1
            if candidate.get("source_type") == "platform_alarm":
                published_alarm_events += 1
                if alarm_incident_key:
                    alarm_cooldowns[alarm_incident_key] = now.isoformat()
            elif candidate.get("source_type") == "monitoring_anomaly":
                monitor_cooldowns[self._monitor_incident_key(candidate)] = now.isoformat()
            # Checkpoint each published fingerprint.  Do not advance poll
            # cursors until the complete cycle succeeds, but make a worker
            # restart resume after the last durable event instead of
            # recollecting and republishing the whole window.
            state["processed_fingerprints"] = processed_order[-10000:]
            state["alarm_cooldowns"] = alarm_cooldowns
            state["monitor_cooldowns"] = monitor_cooldowns
            self._write_json(self.state_path, state)

        last_alarm_poll_at = now.isoformat()
        if deferred_alarm_events:
            last_alarm_poll_at = state.get("last_alarm_poll_at") or (
                since + timedelta(minutes=POLL_OVERLAP_MINUTES)
            ).isoformat()
        state.update({
            "last_alarm_poll_at": last_alarm_poll_at,
            "last_monitor_poll_at": now.isoformat() if monitor_due else state.get("last_monitor_poll_at"),
            "processed_fingerprints": processed_order[-10000:],
            "active_monitor_keys": active_monitor_keys,
            "monitor_station_codes": monitor_station_codes,
            "monitor_station_type": "省控",
            "alarm_cooldowns": alarm_cooldowns,
            "monitor_cooldowns": monitor_cooldowns,
        })
        self._write_json(self.state_path, state)
        result = {
            "alarm_records": len(alarms),
            "monitoring_records": len(monitoring_records),
            "monitor_station_type": "省控",
            "candidates": len(candidates),
            "published_events": published,
            "published_alarm_events": published_alarm_events,
            "deferred_alarm_events": deferred_alarm_events,
            "suppressed_alarm_events": suppressed_alarm_events,
            "filtered_alarm_records": filtered_alarm_records,
            "filtered_out_of_jurisdiction": filtered_out_of_jurisdiction,
            "suppressed_monitor_events": suppressed_monitor_events,
        }
        logger.info("jiangsu_station_fault_poll_completed", **result)
        return result

    async def _fetch_alarms(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        skip_count = 0
        while True:
            result = await self.alarm_tool.execute(
                city_name="江苏省",
                start_time=start.strftime("%Y-%m-%d %H:%M:%S"),
                end_time=end.strftime("%Y-%m-%d %H:%M:%S"),
                alarm_state=1,
                skip_count=skip_count,
                max_result_count=100,
                sorting="id",
            )
            if not result.get("success"):
                raise RuntimeError(result.get("summary") or "江苏告警轮询失败")
            page = [item for item in result.get("data") or [] if isinstance(item, dict)]
            records.extend(page)
            total = int((result.get("metadata") or {}).get("total_count") or len(records))
            if not page or len(records) >= total:
                break
            skip_count += 100
        by_identity = {
            str(item.get("id") or self._fingerprint({"source_record": item})): item
            for item in records
        }
        return list(by_identity.values())

    async def _fetch_monitoring(self, end: datetime) -> tuple[list[dict[str, Any]], list[str]]:
        start = end - timedelta(hours=MONITOR_LOOKBACK_HOURS)
        records_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
        station_codes: set[str] = set()
        for city_name in JIANGSU_PREFECTURE_CITIES:
            city_records, payload = await self.station_tool.fetch_raw_records(
                data_kind="station_hour",
                city_names=[city_name],
                start_time=start.strftime("%Y-%m-%d %H:%M:%S"),
                end_time=end.strftime("%Y-%m-%d %H:%M:%S"),
                data_type=0,
                station_type="省控",
            )
            station_codes.update(
                str(code).strip()
                for code in payload.get("codes") or []
                if str(code).strip()
            )
            for row in city_records:
                code = str(row.get("code") or row.get("stationCode") or "").strip()
                timestamp = str(row.get("timePoint") or "").strip()
                if code and timestamp:
                    records_by_identity[(code, timestamp)] = row

        return list(records_by_identity.values()), sorted(station_codes)

    @staticmethod
    def _alarm_candidate(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_type": "platform_alarm",
            "source_record": row,
            "station_code": str(row.get("stacode") or row.get("stationCode") or "").strip(),
            "station_name": row.get("positionName") or row.get("stationName"),
            "city_name": row.get("areaname") or row.get("cityName"),
            "district_name": row.get("district") or row.get("districtName"),
            "alarm_type": row.get("ddRuleType") or row.get("callType") or "unknown_alarm",
            "severity": row.get("alarmlevel") or "warning",
            "occurred_at": row.get("alarmtime") or row.get("timePoint"),
            "summary": row.get("content") or "江苏站点平台告警",
        }

    @staticmethod
    def _alarm_is_eligible(row: dict[str, Any]) -> bool:
        """Keep active alarms; tolerate fixtures/upstream rows without state."""
        raw_state = row.get("ddalarmstate")
        if raw_state is None or str(raw_state).strip() == "":
            return True
        try:
            if int(raw_state) != 1:
                return False
        except (TypeError, ValueError):
            # Unknown state values should not silently suppress a potentially
            # new alarm.  The upstream state is retained in the evidence pack.
            return True
        return not bool(row.get("removetime"))

    @staticmethod
    def _alarm_incident_key(candidate: dict[str, Any]) -> str:
        """Identify a physical alarm across upstream records with new IDs."""
        source = candidate.get("source_record") or {}
        content = str(candidate.get("summary") or source.get("content") or "")
        # Alarm payloads often contain the current value, limit, date, and
        # hour.  Those values change on every upstream record while the
        # equipment/signal portion remains stable.  Do not replace digits
        # embedded in identifiers such as ``CO-TH-2004H``.
        normalized_content = re.sub(
            r"(?<![A-Za-z0-9])\d+\.\d+(?=(?:年|月|日|时|分|秒|公里|μg|mg|mv|mV|ppm|ppb|%|[^A-Za-z0-9]|$))",
            "#",
            content,
        )
        normalized_content = re.sub(
            r"(?<![A-Za-z0-9])\d+(?=(?:年|月|日|时|分|秒|公里|μg|mg|mv|mV|ppm|ppb|%|[，,。；;：:【】\[\]\s]|$))",
            "#",
            normalized_content,
        )
        identity = {
            "station_code": str(candidate.get("station_code") or "").strip(),
            "alarm_type": str(candidate.get("alarm_type") or "").strip(),
            "call_type": str(source.get("callType") or "").strip(),
            "content": re.sub(r"\s+", " ", normalized_content).strip(),
        }
        encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _monitor_candidate(item: dict[str, Any]) -> dict[str, Any]:
        severities = [finding.get("severity") for finding in item["findings"]]
        return {
            "source_type": "monitoring_anomaly",
            "source_record": item,
            "station_code": item["station_code"],
            "station_type": "省控",
            "station_name": item.get("station_name"),
            "city_name": item.get("city_name"),
            "district_name": item.get("district_name"),
            "alarm_type": ",".join(sorted({finding["type"] for finding in item["findings"]})),
            "severity": "major" if "major" in severities else "warning",
            "occurred_at": item.get("latest_time"),
            "summary": f"监测数据异常：{len(item['findings'])} 项规则命中",
        }

    @staticmethod
    def _monitor_incident_key(candidate: dict[str, Any]) -> str:
        # A station remains one active incident while any deterministic
        # finding is present.  Hourly changes to the finding combination are
        # evidence updates, not new incidents; treating them as new flooded
        # the task queue with thousands of near-duplicate executions.
        encoded = str(candidate.get("station_code") or "").strip()
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _fingerprint(candidate: dict[str, Any]) -> str:
        source = candidate.get("source_record") or {}
        identity = source.get("id") if isinstance(source, dict) else None
        if identity is None:
            identity = {
                "station_code": candidate.get("station_code"),
                "occurred_at": candidate.get("occurred_at"),
                "alarm_type": candidate.get("alarm_type"),
                "source_record": source,
            }
        encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    async def _write_event_package(
        self,
        candidate: dict[str, Any],
        monitoring_rows: list[dict[str, Any]],
        created_at: datetime,
        fingerprint: str,
    ) -> TaskEvent:
        event_id = f"jsfault_{fingerprint[:20]}"
        event_dir = self.output_root / created_at.strftime("%Y/%m/%d") / event_id
        event_dir.mkdir(parents=True, exist_ok=True)
        monitoring_error = None
        station_code = candidate["station_code"]
        station_rows = self._station_rows(monitoring_rows, station_code)
        if not station_rows:
            try:
                fetched_rows, _ = await self.station_tool.fetch_raw_records(
                    data_kind="station_hour",
                    station_codes=[station_code],
                    start_time=(created_at - timedelta(hours=MONITOR_LOOKBACK_HOURS)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    end_time=created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    data_type=0,
                    station_type="省控",
                )
                station_rows = self._station_rows(fetched_rows, station_code)
            except Exception as exc:
                monitoring_error = str(exc)
        station_args = {
            "station_code": candidate["station_code"],
            "station_name": candidate.get("station_name"),
            "city_name": candidate.get("city_name"),
            "district_name": candidate.get("district_name"),
            "station_type": candidate.get("station_type"),
        }
        station_alarm, work_orders, inspection, qc_history = await asyncio.gather(
            self.station_alarm_tool.execute(station_codes=[station_code]),
            self.work_order_tool.execute(
                station_codes=[station_code],
                take=5,
            ),
            self.inspection_tool.execute(
                station_codes=[station_code],
            ),
            self.qc_history_tool.execute(
                station_codes=[station_code],
                start_time=(created_at - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
                end_time=created_at.strftime("%Y-%m-%d %H:%M:%S"),
            ),
            return_exceptions=True,
        )
        weather_required = self._requires_weather(candidate)
        weather_rows = self._weather_rows(station_rows) if weather_required else []
        compact_monitoring_rows = [self._compact_hour_record(row) for row in station_rows]
        evidence = {
            "schema_version": 1,
            "event_id": event_id,
            "created_at": created_at.isoformat(),
            "station": station_args,
            "trigger": candidate,
            "monitoring_hour_records": compact_monitoring_rows,
            "monitoring_collection": {
                "status": (
                    "failed" if monitoring_error else
                    "success" if compact_monitoring_rows else "empty"
                ),
                "success": monitoring_error is None,
                "error": monitoring_error,
                "record_count": len(compact_monitoring_rows),
                "station_code": station_code,
                "data_type": 0,
            },
            "weather_hour_records": weather_rows,
            "weather_collection": {
                "status": (
                    "failed" if weather_required and monitoring_error else
                    "success" if weather_required and weather_rows else
                    "empty" if weather_required else "skipped"
                ),
                "success": monitoring_error is None,
                "required": weather_required,
                "record_count": len(weather_rows),
                "source": "jiangsu_station_hour",
                "endpoint": JiangsuStationDataTool._ENDPOINTS["station_hour"],
                "time_range": self._time_range(station_rows),
                "reason": self._weather_reason(candidate) if weather_required else None,
            },
            "station_alarm_logs": self._compact_result(station_alarm, max_records=40, max_items=20),
            "historical_fault_work_orders": self._compact_result(
                work_orders, max_records=EVIDENCE_MAX_WORK_ORDERS, max_items=8
            ),
            "auto_inspection": self._compact_result(inspection, max_records=10, max_items=20),
            "quality_control_history": self._compact_result(
                qc_history, max_records=EVIDENCE_MAX_QC_RECORDS, max_items=20
            ),
            "collection_notes": [
                "证据包由只读接口自动抓取；事件包保留诊断摘要，不写入工单附件和大字段原文。",
                "诊断结论必须区分已证实事实、推断和待核实项。",
                "污染浓度偏高、偏低、恒值或趋势与城市不一致时，同步提供站点小时气象数据。",
            ],
        }
        evidence_path = event_dir / "diagnosis_evidence_pack.json"
        self._write_json(evidence_path, evidence)
        occurred_at = _parse_datetime(candidate.get("occurred_at")) or created_at
        event = TaskEvent(
            event_id=event_id,
            event_type=EVENT_TYPE,
            occurred_at=occurred_at,
            attributes={
                "source_type": candidate["source_type"],
                "station_code": candidate["station_code"],
                "station_name": candidate.get("station_name"),
                "alarm_type": candidate["alarm_type"],
                "severity": candidate["severity"],
            },
            payload={
                "station": station_args,
                "summary": candidate["summary"],
                "evidence_pack_path": format_agent_path(evidence_path),
                "evidence_dir": format_agent_path(event_dir),
            },
        )
        self._write_json(event_dir / "event.json", event.model_dump(mode="json"))
        return event

    @staticmethod
    def _safe_result(result: Any) -> Any:
        if isinstance(result, BaseException):
            return {"success": False, "status": "failed", "summary": str(result)}
        return result

    @staticmethod
    def _station_rows(rows: list[dict[str, Any]], station_code: str) -> list[dict[str, Any]]:
        code = str(station_code or "").strip()
        return [
            row for row in rows
            if isinstance(row, dict)
            and str(row.get("code") or row.get("stationCode") or "").strip() == code
        ]

    @staticmethod
    def _time_range(rows: list[dict[str, Any]]) -> list[str | None]:
        timestamps = [
            str(row.get("timePoint") or "").strip()
            for row in rows
            if str(row.get("timePoint") or "").strip()
        ]
        return [min(timestamps), max(timestamps)] if timestamps else [None, None]

    @staticmethod
    def _weather_reason(candidate: dict[str, Any]) -> str:
        findings = (candidate.get("source_record") or {}).get("findings") or []
        types = {
            str(item.get("type") or "").strip()
            for item in findings
            if isinstance(item, dict)
        }
        if types.intersection(WEATHER_TRIGGER_TYPES):
            return "污染浓度偏差、恒值或趋势与城市基线不一致"
        return "平台污染浓度偏高或偏低告警"

    @staticmethod
    def _requires_weather(candidate: dict[str, Any]) -> bool:
        source = candidate.get("source_record") or {}
        findings = source.get("findings") or []
        finding_types = {
            str(item.get("type") or "").strip()
            for item in findings
            if isinstance(item, dict)
        }
        if finding_types.intersection(WEATHER_TRIGGER_TYPES):
            return True
        if candidate.get("source_type") != "platform_alarm":
            return False
        alarm_type = str(candidate.get("alarm_type") or "").lower()
        summary = str(candidate.get("summary") or "").lower()
        return "偏差" in alarm_type or any(
            token in summary for token in ("浓度", "偏高", "偏低", "恒值")
        )

    @staticmethod
    def _compact_hour_record(row: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "code", "stationCode", "name", "cityName", "districtName", "timePoint", "dataType",
            "sO2", "nO2", "pM10", "co", "o3", "pM2_5", "no", "nOx",
            "sO2_Mark", "nO2_Mark", "pM10_Mark", "cO_Mark", "o3_Mark", "pM2_5_Mark",
            "qualityType", "aqi", "primaryPollutant", "uniqueCode", "id",
            *(field for field, _ in WEATHER_FIELDS),
        )
        return {key: row[key] for key in fields if key in row}

    @staticmethod
    def _weather_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        weather: list[dict[str, Any]] = []
        for row in rows:
            item = {
                "station_code": row.get("code") or row.get("stationCode"),
                "time_point": row.get("timePoint"),
            }
            for source_key, target_key in WEATHER_FIELDS:
                if source_key in row:
                    item[target_key] = row[source_key]
            if any(
                str(value or "").strip() not in {"", "-", "—", "-99", "-99.000"}
                for key, value in item.items()
                if key not in {"station_code", "time_point"}
            ):
                weather.append(item)
        return weather

    @classmethod
    def _compact_result(
        cls, result: Any, *, max_records: int, max_items: int = 40
    ) -> dict[str, Any]:
        if isinstance(result, BaseException):
            return {"success": False, "status": "failed", "summary": str(result), "data": []}
        if not isinstance(result, dict):
            return {"success": False, "status": "failed", "summary": "补充数据返回格式异常", "data": []}
        compact: dict[str, Any] = {
            "success": result["success"] if "success" in result else False,
            "status": result.get("status"),
            "summary": cls._compact_text(result.get("summary", "")),
            "metadata": cls._compact_value(result.get("metadata", {}), max_items=max_items),
        }
        data = result.get("data")
        if isinstance(data, list):
            compact["data"] = [
                cls._compact_value(item, max_items=max_items) for item in data[:max_records]
            ]
            compact["record_count"] = len(data)
            compact["returned_records"] = min(len(data), max_records)
        elif isinstance(data, dict):
            compact["data"] = cls._compact_value(data, max_items=max_items)
        else:
            compact["data"] = data if data is not None else []
        if result.get("error"):
            compact["error"] = cls._compact_text(result["error"])
        return compact

    @classmethod
    def _compact_value(cls, value: Any, *, depth: int = 0, max_items: int = 40) -> Any:
        if isinstance(value, str):
            return cls._compact_text(value)
        if depth >= 4:
            return "[nested data omitted]" if isinstance(value, (dict, list)) else value
        if isinstance(value, list):
            return [cls._compact_value(item, depth=depth + 1, max_items=max_items) for item in value[:max_items]]
        if isinstance(value, dict):
            compact = {}
            for key, item in value.items():
                key_text = str(key).lower()
                if any(token in key_text for token in ("commonfile", "attachment", "visuals", "resources", "image")):
                    continue
                compact[str(key)] = cls._compact_value(item, depth=depth + 1, max_items=max_items)
            return compact
        return value

    @staticmethod
    def _compact_text(value: Any) -> str:
        text = str(value)
        if len(text) <= EVIDENCE_MAX_TEXT_CHARS:
            return text
        return text[:EVIDENCE_MAX_TEXT_CHARS] + "…[truncated]"

    def _read_state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    @staticmethod
    async def _publish_event(event: TaskEvent) -> Any:
        from app.scheduled_tasks import get_scheduled_task_service

        return await get_scheduled_task_service().publish_event(event)

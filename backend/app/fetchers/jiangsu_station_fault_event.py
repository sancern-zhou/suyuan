"""Poll Jiangsu alarms/observations and publish evidence-backed fault events."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
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
from app.tools.jiangsu.station_data import JiangsuStationDataTool
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
            mark_key = f"{key}_Mark" if key != "co" else "cO_Mark"
            mark = str(latest.get(mark_key) or "").strip()
            if mark and mark not in {"-", "—"}:
                findings.append({
                    "type": "quality_flag",
                    "severity": "warning",
                    "pollutant": label,
                    "flag": mark,
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

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.clock()
        state = self._read_state()
        since = now - timedelta(minutes=POLL_OVERLAP_MINUTES)
        if state.get("last_alarm_poll_at"):
            previous = _parse_datetime(state["last_alarm_poll_at"])
            if previous:
                since = previous - timedelta(minutes=POLL_OVERLAP_MINUTES)

        alarms = await self._fetch_alarms(since, now)
        candidates = [
            candidate
            for row in alarms
            if (candidate := self._alarm_candidate(row))["station_code"]
        ]

        monitor_due = True
        previous_monitor = _parse_datetime(state.get("last_monitor_poll_at"))
        if previous_monitor:
            monitor_due = now - previous_monitor >= timedelta(minutes=MONITOR_INTERVAL_MINUTES)
        monitoring_records: list[dict[str, Any]] = []
        active_monitor_keys = list(state.get("active_monitor_keys") or [])
        monitor_station_codes = list(state.get("monitor_station_codes") or [])
        if monitor_due:
            monitoring_records, _directory_station_codes = await self._fetch_monitoring(now)
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
            current_active: list[str] = []
            for candidate in monitor_candidates:
                incident_key = self._monitor_incident_key(candidate)
                current_active.append(incident_key)
                if incident_key not in previous_active:
                    candidate["incident_started_at"] = now.isoformat()
                    candidates.append(candidate)
            active_monitor_keys = current_active

        processed_order = list(dict.fromkeys(state.get("processed_fingerprints") or []))
        processed = set(processed_order)
        published = 0
        for candidate in candidates:
            fingerprint = self._fingerprint(candidate)
            if fingerprint in processed:
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
            # Checkpoint each published fingerprint.  Do not advance poll
            # cursors until the complete cycle succeeds, but make a worker
            # restart resume after the last durable event instead of
            # recollecting and republishing the whole window.
            state["processed_fingerprints"] = processed_order[-10000:]
            self._write_json(self.state_path, state)

        state.update({
            "last_alarm_poll_at": now.isoformat(),
            "last_monitor_poll_at": now.isoformat() if monitor_due else state.get("last_monitor_poll_at"),
            "processed_fingerprints": processed_order[-10000:],
            "active_monitor_keys": active_monitor_keys,
            "monitor_station_codes": monitor_station_codes,
        })
        self._write_json(self.state_path, state)
        result = {
            "alarm_records": len(alarms),
            "monitoring_records": len(monitoring_records),
            "candidates": len(candidates),
            "published_events": published,
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
        records, payload = await self.station_tool.fetch_raw_records(
            data_kind="station_hour",
            city_names=["江苏省"],
            start_time=start.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=end.strftime("%Y-%m-%d %H:%M:%S"),
            data_type=0,
        )
        return records, list(payload.get("codes") or [])

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
    def _monitor_candidate(item: dict[str, Any]) -> dict[str, Any]:
        severities = [finding.get("severity") for finding in item["findings"]]
        return {
            "source_type": "monitoring_anomaly",
            "source_record": item,
            "station_code": item["station_code"],
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
        findings = (candidate.get("source_record") or {}).get("findings") or []
        signature = sorted(
            (finding.get("type"), finding.get("pollutant"))
            for finding in findings
        )
        encoded = json.dumps(
            [candidate.get("station_code"), signature],
            ensure_ascii=False,
            sort_keys=True,
        )
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
        if not monitoring_rows:
            try:
                monitoring_rows, _ = await self.station_tool.fetch_raw_records(
                    data_kind="station_hour",
                    station_codes=[candidate["station_code"]],
                    start_time=(created_at - timedelta(hours=MONITOR_LOOKBACK_HOURS)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    end_time=created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    data_type=0,
                )
            except Exception as exc:
                monitoring_error = str(exc)
        station_args = {
            "station_code": candidate["station_code"],
            "station_name": candidate.get("station_name"),
            "city_name": candidate.get("city_name"),
            "district_name": candidate.get("district_name"),
        }
        station_alarm, work_orders, inspection, qc_history = await asyncio.gather(
            self.station_alarm_tool.execute(station_code=candidate["station_code"]),
            self.work_order_tool.execute(
                station_name=candidate.get("station_name"),
                city_name=candidate.get("city_name"),
                district_name=candidate.get("district_name"),
                take=5,
            ),
            self.inspection_tool.execute(
                station_name=candidate.get("station_name"),
                city_name=candidate.get("city_name"),
                district_name=candidate.get("district_name"),
            ),
            self.qc_history_tool.execute(
                station_code=candidate["station_code"],
                start_time=(created_at - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
                end_time=created_at.strftime("%Y-%m-%d %H:%M:%S"),
            ),
            return_exceptions=True,
        )
        evidence = {
            "schema_version": 1,
            "event_id": event_id,
            "created_at": created_at.isoformat(),
            "station": station_args,
            "trigger": candidate,
            "monitoring_hour_records": monitoring_rows,
            "monitoring_collection": {
                "success": monitoring_error is None,
                "error": monitoring_error,
                "record_count": len(monitoring_rows),
            },
            "station_alarm_logs": self._safe_result(station_alarm),
            "historical_fault_work_orders": self._safe_result(work_orders),
            "auto_inspection": self._safe_result(inspection),
            "quality_control_history": self._safe_result(qc_history),
            "collection_notes": [
                "证据包由只读接口自动抓取；单个补充接口失败不会丢弃原始事件。",
                "诊断结论必须区分已证实事实、推断和待核实项。",
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

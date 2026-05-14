"""
City pollution process monitor.

This module keeps the deterministic part of proactive pollution analysis out of
the LLM loop:

1. fetch recent city hourly monitoring data;
2. run quality checks and event detection locally;
3. collect supplemental station, weather, and composition data for detected
   events;
4. persist a structured evidence pack for the Agent reasoning skill.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4
from zoneinfo import ZoneInfo

import structlog

from app.agent.context.data_context_manager import DataContextManager
from app.agent.context.execution_context import ExecutionContext
from app.agent.memory.hybrid_manager import HybridMemoryManager
from app.services.pollution_event_state_store import PollutionEventStateStore

logger = structlog.get_logger()


TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class PollutantSpec:
    key: str
    aliases: Sequence[str]
    unit: str
    absolute_threshold: float
    step_threshold: float
    min_meaningful: float = 1.0


POLLUTANTS: Tuple[PollutantSpec, ...] = (
    PollutantSpec("AQI", ("AQI", "aqi"), "", 100.0, 35.0, 10.0),
    PollutantSpec("PM2_5", ("PM2_5", "PM2.5", "pm2_5", "pm25", "pM2_5"), "ug/m3", 75.0, 25.0, 8.0),
    PollutantSpec("PM10", ("PM10", "pm10", "pM10"), "ug/m3", 150.0, 40.0, 10.0),
    PollutantSpec("O3_8h", ("O3_8h", "O3-8h", "o3_8h", "O3", "o3"), "ug/m3", 160.0, 40.0, 20.0),
    PollutantSpec("NO2", ("NO2", "no2", "nO2"), "ug/m3", 100.0, 30.0, 5.0),
    PollutantSpec("SO2", ("SO2", "so2", "sO2"), "ug/m3", 150.0, 35.0, 5.0),
    PollutantSpec("CO", ("CO", "co"), "mg/m3", 4.0, 1.0, 0.1),
)

WEATHER_FIELDS = (
    "wind_speed_10m",
    "wind_direction_10m",
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_gusts_10m",
    "precipitation",
    "cloud_cover",
    "visibility",
    "boundary_layer_height",
)


@dataclass
class MonitorConfig:
    cities: List[str]
    hours: int = 24
    station_type: List[str] = field(default_factory=lambda: ["国控", "省控"])  # 同时抓取国控和省控
    output_root: Optional[Path] = None
    force_collect: bool = False
    include_components: bool = True
    event_context_hours: int = 2
    event_merge_gap_hours: int = 3
    event_inactive_hours: int = 6
    min_event_points: int = 2
    low_wind_speed_threshold: float = 1.5
    end_time: Optional[datetime] = None
    session_id: str = field(default_factory=lambda: f"pollution_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}")


class PollutionEventMonitorService:
    """Fetch, detect, and persist city pollution process evidence packs."""

    def __init__(self, config: MonitorConfig, context: Optional[ExecutionContext] = None):
        self.config = config
        if isinstance(self.config.station_type, str):
            self.config.station_type = [self.config.station_type]
        self.context = context or self._create_context(config.session_id)
        self.backend_dir = Path(__file__).resolve().parents[2]
        self.output_root = self._resolve_output_root(config.output_root)
        self.event_state_store = PollutionEventStateStore(
            output_root=self.output_root,
            merge_gap_hours=self.config.event_merge_gap_hours,
            inactive_hours=self.config.event_inactive_hours,
        )

    async def run(self) -> Dict[str, Any]:
        started_at = datetime.now(TZ_SHANGHAI)
        end_time = self._normalize_end_time(self.config.end_time)
        start_time = end_time - timedelta(hours=max(1, self.config.hours - 1))
        run_id = started_at.strftime("%Y%m%d_%H%M%S")

        logger.info(
            "pollution_event_monitor_started",
            cities=self.config.cities,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            output_root=str(self.output_root),
        )

        city_results = []
        for city in self.config.cities:
            city_result = await self._run_city(city, start_time, end_time, run_id)
            city_results.append(city_result)

        detected_count = sum(len(result.get("events", [])) for result in city_results)
        completed_at = datetime.now(TZ_SHANGHAI)
        return {
            "success": True,
            "run_id": run_id,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "time_range": {
                "start": self._format_api_time(start_time),
                "end": self._format_api_time(end_time),
                "hours": self.config.hours,
            },
            "cities": city_results,
            "detected_event_count": detected_count,
            "output_root": str(self.output_root),
            "summary": self._build_run_summary(city_results, detected_count),
        }

    async def _run_city(
        self,
        city: str,
        start_time: datetime,
        end_time: datetime,
        run_id: str,
    ) -> Dict[str, Any]:
        city_slug = self._safe_name(city)
        run_dir = self.output_root / city_slug / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        city_fetch = self._fetch_city_hour_data(city, start_time, end_time)
        city_records = city_fetch.get("records", [])
        quality_report = self._quality_report(city, city_records, start_time, end_time)
        raw_events = self._detect_events(city, city_records, quality_report)
        events = []
        lifecycle_transitions = []
        for raw_event in raw_events:
            event, lifecycle = self.event_state_store.reconcile_event(raw_event, run_id=run_id)
            events.append(event)
            lifecycle_transitions.append(lifecycle)

        self._write_json(run_dir / "city_hour_monitoring.json", {
            "city": city,
            "source_result": city_fetch.get("source_result"),
            "records": city_records,
        })
        self._write_json(run_dir / "data_quality_report.json", quality_report)
        self._write_json(run_dir / "detected_events.json", {
            "city": city,
            "raw_events": raw_events,
            "events": events,
            "lifecycle_transitions": lifecycle_transitions,
        })

        event_results: List[Dict[str, Any]] = []
        if events or self.config.force_collect:
            target_events = events or [self._build_no_event_collection_window(city, start_time, end_time, city_records)]
            for event in target_events:
                event_result = await self._collect_event_evidence(
                    city=city,
                    event=event,
                    run_dir=run_dir,
                    city_records=city_records,
                    quality_report=quality_report,
                    full_start=start_time,
                    full_end=end_time,
                )
                event_results.append(event_result)
                lifecycle = event.get("event_lifecycle", {})
                if lifecycle.get("status") != "routine" and event_result.get("evidence_pack"):
                    self.event_state_store.append_artifact(
                        event_id=event["event_id"],
                        run_id=run_id,
                        evidence_pack=event_result.get("evidence_pack"),
                        analysis_request=event_result.get("analysis_request"),
                        event_dir=event_result.get("event_dir"),
                    )

        ended_events = self.event_state_store.close_inactive_events(city=city, watermark=end_time)

        run_manifest = {
            "run_id": run_id,
            "city": city,
            "time_range": {
                "start": self._format_api_time(start_time),
                "end": self._format_api_time(end_time),
                "hours": self.config.hours,
            },
            "city_hour_file": str(run_dir / "city_hour_monitoring.json"),
            "quality_file": str(run_dir / "data_quality_report.json"),
            "events_file": str(run_dir / "detected_events.json"),
            "event_count": len(events),
            "events": event_results,
            "lifecycle_transitions": lifecycle_transitions,
            "ended_events": ended_events,
            "event_state_index": str(self.event_state_store.index_path),
            "force_collect": self.config.force_collect,
        }
        self._write_json(run_dir / "run_manifest.json", run_manifest)

        return {
            "city": city,
            "run_dir": str(run_dir),
            "records": len(city_records),
            "quality_status": quality_report.get("status"),
            "quality_issue_count": len(quality_report.get("issues", [])),
            "events": events,
            "event_artifacts": event_results,
            "lifecycle_transitions": lifecycle_transitions,
            "ended_events": ended_events,
            "manifest_file": str(run_dir / "run_manifest.json"),
        }

    def _fetch_city_hour_data(self, city: str, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_station_hour

        result = execute_query_gd_suncere_station_hour(
            cities=[city],
            start_time=self._format_api_time(start_time),
            end_time=self._format_api_time(end_time),
            context=self.context,
            include_weather=True,
        )
        data_id = self._extract_data_id(result)
        records = self._load_data_records(data_id, result)
        return {
            "data_id": data_id,
            "records": records,
            "source_result": self._compact_result(result),
        }

    async def _collect_event_evidence(
        self,
        city: str,
        event: Dict[str, Any],
        run_dir: Path,
        city_records: List[Dict[str, Any]],
        quality_report: Dict[str, Any],
        full_start: datetime,
        full_end: datetime,
    ) -> Dict[str, Any]:
        event_id = event["event_id"]
        event_dir = run_dir / event_id
        event_dir.mkdir(parents=True, exist_ok=True)

        event_start = self._parse_time(event["time_range"]["start"]) or full_start
        event_end = self._parse_time(event["time_range"]["end"]) or full_end
        fetch_start = max(full_start, event_start - timedelta(hours=self.config.event_context_hours))
        fetch_end = min(full_end, event_end + timedelta(hours=self.config.event_context_hours))

        fetch_errors: List[Dict[str, str]] = []

        station_records: List[Dict[str, Any]] = []
        station_result_compact: Dict[str, Any] = {}
        try:
            station_fetch = self._fetch_station_hour_data(city, fetch_start, fetch_end)
            station_records = station_fetch.get("records", [])
            station_result_compact = station_fetch.get("source_result", {})
            self._write_json(event_dir / "station_hour_monitoring.json", {
                "city": city,
                "event_id": event_id,
                "records": station_records,
                "source_result": station_result_compact,
            })
            if not station_records:
                fetch_errors.append({
                    "source": "station_hour",
                    "severity": "warning",
                    "error": station_result_compact.get("summary") or "Station hourly evidence returned no records.",
                })
        except Exception as exc:
            fetch_errors.append({"source": "station_hour", "error": str(exc)})
            logger.warning("station_hour_evidence_fetch_failed", city=city, event_id=event_id, error=str(exc))

        weather_records = self._extract_weather_records(city_records, station_records, fetch_start, fetch_end)
        self._write_json(event_dir / "weather_hourly.json", {
            "city": city,
            "event_id": event_id,
            "records": weather_records,
        })
        if not weather_records:
            fetch_errors.append({
                "source": "weather_hour",
                "severity": "warning",
                "error": "No weather fields were available in city or station hourly evidence.",
            })

        component_results: Dict[str, Any] = {}
        if self.config.include_components:
            component_results = await self._fetch_component_data(city, fetch_start, fetch_end, event_dir, fetch_errors)

        event_city_records = self._filter_records_by_time(city_records, fetch_start, fetch_end)
        event_summary = self._summarize_event_data(event, event_city_records, station_records, weather_records)
        quality_gate = self._build_quality_gate(quality_report, fetch_errors)
        observed_signal_summary = self._build_observed_signal_summary(event, event_summary)
        suggested_evidence_gaps = self._suggest_evidence_gaps(
            event=event,
            event_summary=event_summary,
            fetch_errors=fetch_errors,
            station_records=station_records,
            weather_records=weather_records,
            component_results=component_results,
        )

        evidence_pack = {
            "schema_version": "pollution_event_evidence_pack/v1",
            "schema_features": [
                "event_lifecycle",
                "quality_gate",
                "observed_signal_summary",
                "suggested_evidence_gaps",
            ],
            "created_at": datetime.now(TZ_SHANGHAI).isoformat(),
            "city": city,
            "event": event,
            "collection_window": {
                "start": self._format_api_time(fetch_start),
                "end": self._format_api_time(fetch_end),
            },
            "quality_gate": quality_gate,
            "data_quality": quality_report,
            "data_files": {
                "event": str(event_dir / "event.json"),
                "city_hour_monitoring": str(run_dir / "city_hour_monitoring.json"),
                "station_hour_monitoring": str(event_dir / "station_hour_monitoring.json"),
                "weather_hourly": str(event_dir / "weather_hourly.json"),
                **component_results.get("files", {}),
            },
            "data_refs": {
                "station_hour_data_id": self._extract_data_id(station_result_compact),
                **component_results.get("data_refs", {}),
            },
            "event_summary": event_summary,
            "observed_signal_summary": observed_signal_summary,
            "suggested_evidence_gaps": suggested_evidence_gaps,
            "fetch_errors": fetch_errors,
            "analysis_contract": {
                "skill_name": "city_pollution_process_analysis",
                "skill_file": str(self.backend_dir / "docs" / "skills" / "city_pollution_process_analysis.md"),
                "agent_goal": "Use the project pollution process analysis skill to generate hypotheses, verify them with the evidence pack, optionally collect missing evidence, and write reasoning_analysis.md.",
                "required_outputs": [
                    "observed_facts",
                    "hypothesis_ranking",
                    "evidence_matrix",
                    "counter_evidence",
                    "confidence",
                    "follow_up_actions",
                ],
                "llm_role_limits": [
                    "Do not re-decide deterministic alert triggers.",
                    "Do not assert a source without cited evidence.",
                    "Downgrade conclusions when quality_gate limits confidence.",
                ],
            },
        }

        self._write_json(event_dir / "event.json", event)
        self._write_json(event_dir / "evidence_pack.json", evidence_pack)
        self._write_text(event_dir / "analysis_request.md", self._build_analysis_request(evidence_pack))

        return {
            "event_id": event_id,
            "event_dir": str(event_dir),
            "evidence_pack": str(event_dir / "evidence_pack.json"),
            "analysis_request": str(event_dir / "analysis_request.md"),
            "fetch_errors": fetch_errors,
        }

    def _fetch_station_hour_data(self, city: str, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_station_hour_real

        # 支持多个站点类型：分别调用API并合并结果
        all_records = []
        all_data_ids = []
        source_results = {}

        for station_type in self.config.station_type:
            result = execute_query_gd_suncere_station_hour_real(
                cities=[city],
                stations=None,
                station_type=station_type,
                start_time=self._format_api_time(start_time),
                end_time=self._format_api_time(end_time),
                context=self.context,
                include_weather=True,
            )
            data_id = self._extract_data_id(result)
            records = self._load_data_records(data_id, result)
            all_records.extend(records)
            all_data_ids.append(data_id)
            source_results[station_type] = self._compact_result(result)

            logger.info(
                "station_hour_data_fetched",
                city=city,
                station_type=station_type,
                record_count=len(records),
                data_id=data_id,
            )

        return {
            "data_id": ",".join(all_data_ids),  # 多个data_id用逗号分隔
            "records": all_records,
            "source_result": source_results,
        }

    async def _fetch_component_data(
        self,
        city: str,
        start_time: datetime,
        end_time: datetime,
        event_dir: Path,
        fetch_errors: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        files: Dict[str, str] = {}
        data_refs: Dict[str, Optional[str]] = {}

        start_text = self._format_api_time(start_time)
        end_text = self._format_api_time(end_time)

        try:
            from app.tools.query.get_particulate_components import GetParticulateComponentsTool

            pm_tool = GetParticulateComponentsTool()
            pm_result = await pm_tool.execute(
                context=self.context,
                locations=[city],
                start_time=start_text,
                end_time=end_text,
                data_type=0,
                time_granularity=1,
            )
            pm_data_id = self._extract_data_id(pm_result)
            pm_records = self._load_data_records(pm_data_id, pm_result)
            self._write_json(event_dir / "pm25_components.json", {
                "city": city,
                "records": pm_records,
                "source_result": self._compact_result(pm_result),
            })
            if not pm_records:
                fetch_errors.append({
                    "source": "pm25_components",
                    "severity": "warning",
                    "error": "PM2.5 component evidence returned no records.",
                })
            files["pm25_components"] = str(event_dir / "pm25_components.json")
            data_refs["pm25_components_data_id"] = pm_data_id
        except Exception as exc:
            fetch_errors.append({"source": "pm25_components", "error": str(exc)})
            logger.warning("pm25_component_evidence_fetch_failed", city=city, error=str(exc))

        try:
            from app.tools.query.get_vocs_data import GetVOCsDataTool

            vocs_tool = GetVOCsDataTool()
            vocs_result = await vocs_tool.execute(
                context=self.context,
                locations=[city],
                start_time=start_text,
                end_time=end_text,
                table_type=1,
                data_type=0,
            )
            vocs_data_id = self._extract_data_id(vocs_result)
            vocs_records = self._load_data_records(vocs_data_id, vocs_result)
            self._write_json(event_dir / "vocs_components.json", {
                "city": city,
                "records": vocs_records,
                "source_result": self._compact_result(vocs_result),
            })
            if not vocs_records:
                fetch_errors.append({
                    "source": "vocs_components",
                    "severity": "warning",
                    "error": "VOCs component evidence returned no records.",
                })
            files["vocs_components"] = str(event_dir / "vocs_components.json")
            data_refs["vocs_components_data_id"] = vocs_data_id
        except Exception as exc:
            fetch_errors.append({"source": "vocs_components", "error": str(exc)})
            logger.warning("vocs_component_evidence_fetch_failed", city=city, error=str(exc))

        return {"files": files, "data_refs": data_refs}

    def _quality_report(
        self,
        city: str,
        records: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        issues: List[Dict[str, Any]] = []
        timestamps = [self._record_time(record) for record in records]
        valid_timestamps = [ts for ts in timestamps if ts is not None]
        unique_timestamps = sorted(set(valid_timestamps))
        expected_hours = self._expected_hour_count(start_time, end_time)

        if not records:
            issues.append({
                "severity": "high",
                "issue_type": "no_data",
                "message": "No city hourly monitoring records were returned.",
                "impact": "Event detection cannot run for this city.",
            })
        elif len(unique_timestamps) < expected_hours * 0.75:
            issues.append({
                "severity": "medium",
                "issue_type": "missing_hours",
                "message": f"Only {len(unique_timestamps)} unique hourly timestamps for expected {expected_hours}.",
                "impact": "Process duration and start/end boundaries may be underestimated.",
            })

        duplicate_count = len(valid_timestamps) - len(unique_timestamps)
        if duplicate_count > 0:
            issues.append({
                "severity": "low",
                "issue_type": "duplicate_timestamp",
                "message": f"{duplicate_count} duplicate timestamp records detected.",
                "impact": "Aggregations should deduplicate by city/station and timestamp.",
            })

        pollutant_stats = {}
        for spec in POLLUTANTS:
            series = self._pollutant_series(records, spec)
            values = [value for _, value, _ in series if self._is_valid_number(value)]
            missing_count = len(records) - len(values)
            invalid_count = sum(1 for _, value, _ in series if value is not None and not self._is_valid_number(value))
            stale_streak = self._max_constant_streak(values)
            spike_count = self._spike_count(values, spec)
            pollutant_stats[spec.key] = {
                "valid_count": len(values),
                "missing_count": missing_count,
                "invalid_count": invalid_count,
                "missing_rate": missing_count / len(records) if records else 1.0,
                "max_constant_streak": stale_streak,
                "spike_count": spike_count,
                "median": self._median(values),
                "max": max(values) if values else None,
            }
            if records and missing_count / len(records) > 0.35:
                issues.append({
                    "severity": "medium",
                    "issue_type": "high_missing_rate",
                    "pollutant": spec.key,
                    "message": f"{spec.key} missing rate is {missing_count / len(records):.0%}.",
                    "impact": f"{spec.key} event confidence should be downgraded.",
                })
            if stale_streak >= 6 and len(values) >= 8:
                issues.append({
                    "severity": "medium",
                    "issue_type": "long_constant_value",
                    "pollutant": spec.key,
                    "message": f"{spec.key} has a constant streak of {stale_streak} records.",
                    "impact": "Potential stale data or instrument issue.",
                })
            if spike_count > 0:
                issues.append({
                    "severity": "low",
                    "issue_type": "isolated_spike",
                    "pollutant": spec.key,
                    "message": f"{spec.key} has {spike_count} isolated spike candidates.",
                    "impact": "Short spikes need station and neighboring pollutant confirmation.",
                })

        pm_inversions = self._pm25_gt_pm10_issues(records)
        if pm_inversions:
            issues.append({
                "severity": "medium",
                "issue_type": "pm25_gt_pm10",
                "message": f"PM2.5 is greater than PM10 in {len(pm_inversions)} records.",
                "impact": "Particle event interpretation should check instrument or rounding issues.",
                "samples": pm_inversions[:5],
            })

        weather_missing = self._weather_missing_rate(records)
        if weather_missing > 0.5 and records:
            issues.append({
                "severity": "medium",
                "issue_type": "weather_missing",
                "message": f"Weather field missing rate is {weather_missing:.0%}.",
                "impact": "Wind and dispersion mechanism confidence should be downgraded.",
            })

        high_severity = any(issue["severity"] == "high" for issue in issues)
        medium_severity = any(issue["severity"] == "medium" for issue in issues)
        status = "poor" if high_severity else "usable_with_caution" if medium_severity else "usable"

        return {
            "city": city,
            "status": status,
            "record_count": len(records),
            "expected_hours": expected_hours,
            "unique_timestamps": len(unique_timestamps),
            "time_range": {
                "start": self._format_api_time(start_time),
                "end": self._format_api_time(end_time),
            },
            "issues": issues,
            "pollutant_stats": pollutant_stats,
        }

    def _detect_events(
        self,
        city: str,
        records: List[Dict[str, Any]],
        quality_report: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if not records:
            return []

        timeline_flags: Dict[datetime, List[Dict[str, Any]]] = {}
        pollutant_diagnostics: Dict[str, Dict[str, Any]] = {}

        for spec in POLLUTANTS:
            series = self._pollutant_series(records, spec)
            clean = [(ts, value, record) for ts, value, record in series if ts and self._is_valid_number(value)]
            if len(clean) < 4:
                continue

            values = [value for _, value, _ in clean]
            median = self._median(values)
            mad = self._mad(values, median)
            q75 = self._quantile(values, 0.75)
            dynamic_threshold = max(spec.absolute_threshold * 0.75, q75, median + max(1.4826 * mad * 2.5, spec.step_threshold))

            pollutant_diagnostics[spec.key] = {
                "median": median,
                "mad": mad,
                "q75": q75,
                "dynamic_threshold": dynamic_threshold,
                "absolute_threshold": spec.absolute_threshold,
            }

            previous_value: Optional[float] = None
            for ts, value, record in clean:
                reasons: List[str] = []
                if value >= spec.absolute_threshold:
                    reasons.append("absolute_threshold")
                if mad > 0 and value >= spec.min_meaningful:
                    robust_z = (value - median) / (1.4826 * mad)
                    if robust_z >= 3.0:
                        reasons.append("robust_outlier")
                if value >= dynamic_threshold and value >= spec.min_meaningful:
                    reasons.append("dynamic_threshold")
                if previous_value is not None:
                    delta = value - previous_value
                    pct_delta = delta / max(abs(previous_value), spec.min_meaningful)
                    if delta >= spec.step_threshold and pct_delta >= 0.25:
                        reasons.append("rapid_rise")
                previous_value = value

                if reasons:
                    timeline_flags.setdefault(ts, []).append({
                        "pollutant": spec.key,
                        "value": value,
                        "unit": spec.unit,
                        "reasons": sorted(set(reasons)),
                    })

        # Add sustained windows even when no single point is extreme.
        for spec in POLLUTANTS:
            series = self._pollutant_series(records, spec)
            clean = [(ts, value, record) for ts, value, record in series if ts and self._is_valid_number(value)]
            if len(clean) < 6:
                continue
            values = [value for _, value, _ in clean]
            median = self._median(values)
            threshold = max(self._quantile(values, 0.75), median + spec.step_threshold * 0.6, spec.absolute_threshold * 0.65)
            streak: List[Tuple[datetime, float]] = []
            for ts, value, _ in clean:
                if value >= threshold and value >= spec.min_meaningful:
                    streak.append((ts, value))
                else:
                    self._mark_sustained_streak(timeline_flags, spec, streak, threshold)
                    streak = []
            self._mark_sustained_streak(timeline_flags, spec, streak, threshold)

        if not timeline_flags:
            return []

        segments = self._segments_from_flags(timeline_flags)
        events = []
        for index, segment in enumerate(segments, start=1):
            flags = []
            for ts in segment:
                flags.extend(timeline_flags.get(ts, []))
            if not flags:
                continue

            pollutant_scores: Dict[str, Dict[str, Any]] = {}
            for flag in flags:
                item = pollutant_scores.setdefault(flag["pollutant"], {
                    "count": 0,
                    "peak": None,
                    "unit": flag.get("unit", ""),
                    "reasons": set(),
                })
                item["count"] += 1
                item["peak"] = flag["value"] if item["peak"] is None else max(item["peak"], flag["value"])
                item["reasons"].update(flag.get("reasons", []))

            main_pollutant = max(
                pollutant_scores.items(),
                key=lambda item: (item[1]["count"], item[1]["peak"] or 0),
            )[0]
            event_start = min(segment)
            event_end = max(segment)
            duration_hours = int((event_end - event_start).total_seconds() // 3600) + 1
            event_type = self._classify_event(main_pollutant, duration_hours, flags, records, event_start, event_end)
            severity = self._event_severity(main_pollutant, pollutant_scores)
            confidence = self._event_confidence(quality_report, flags, duration_hours)
            event_id = f"evt_{event_start.strftime('%Y%m%d%H')}_{self._safe_name(city)}_{main_pollutant.lower()}_{index}"

            evidence_summary = []
            for pollutant, score in sorted(pollutant_scores.items(), key=lambda item: item[1]["count"], reverse=True):
                evidence_summary.append({
                    "pollutant": pollutant,
                    "flag_count": score["count"],
                    "peak_value": score["peak"],
                    "unit": score["unit"],
                    "reasons": sorted(score["reasons"]),
                    "diagnostics": pollutant_diagnostics.get(pollutant, {}),
                })

            events.append({
                "event_id": event_id,
                "city": city,
                "event_type": event_type,
                "severity": severity,
                "confidence": confidence,
                "main_pollutant": main_pollutant,
                "time_range": {
                    "start": self._format_api_time(event_start),
                    "end": self._format_api_time(event_end),
                    "duration_hours": duration_hours,
                },
                "evidence_summary": evidence_summary,
                "triggered_by": sorted({reason for flag in flags for reason in flag.get("reasons", [])}),
                "next_data_needed": self._next_data_needed(main_pollutant, event_type),
            })

        return events

    def _build_no_event_collection_window(
        self,
        city: str,
        start_time: datetime,
        end_time: datetime,
        city_records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        peak_info = self._peak_pollutant(city_records)
        main_pollutant = peak_info.get("pollutant") or "AQI"
        event_id = f"evt_{end_time.strftime('%Y%m%d%H')}_{self._safe_name(city)}_routine"
        return {
            "event_id": event_id,
            "city": city,
            "event_type": "routine_collection_no_algorithm_event",
            "severity": "low",
            "confidence": "low",
            "main_pollutant": main_pollutant,
            "time_range": {
                "start": self._format_api_time(start_time),
                "end": self._format_api_time(end_time),
                "duration_hours": self.config.hours,
            },
            "evidence_summary": [peak_info] if peak_info else [],
            "triggered_by": ["force_collect"],
            "next_data_needed": ["Use this as a routine baseline package; do not infer a pollution process without additional evidence."],
            "event_lifecycle": {
                "status": "routine",
                "canonical_event_id": event_id,
                "detection_event_id": event_id,
                "state_time_range": {
                    "start": self._format_api_time(start_time),
                    "end": self._format_api_time(end_time),
                    "duration_hours": self.config.hours,
                },
            },
        }

    def _summarize_event_data(
        self,
        event: Dict[str, Any],
        city_records: List[Dict[str, Any]],
        station_records: List[Dict[str, Any]],
        weather_records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        main = event.get("main_pollutant", "AQI")
        city_peak = self._series_peak(city_records, main)
        station_peaks = self._station_peaks(station_records, main)
        wind_summary = self._wind_summary(weather_records)
        pollutant_correlation = self._pollutant_cochange(city_records, main)
        return {
            "main_pollutant": main,
            "city_peak": city_peak,
            "station_peaks": station_peaks[:10],
            "wind_summary": wind_summary,
            "cochange": pollutant_correlation,
            "record_counts": {
                "city_hour": len(city_records),
                "station_hour": len(station_records),
                "weather_hour": len(weather_records),
            },
        }

    def _build_quality_gate(
        self,
        quality_report: Dict[str, Any],
        fetch_errors: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        status = quality_report.get("status")
        issues = quality_report.get("issues", [])
        high_issues = [issue for issue in issues if issue.get("severity") == "high"]
        medium_issues = [issue for issue in issues if issue.get("severity") == "medium"]
        missing_sources = [
            error.get("source")
            for error in fetch_errors
            if error.get("severity", "warning") in {"warning", "high", "error"}
        ]

        if status == "poor" or high_issues:
            gate_status = "fail"
            max_confidence = "low"
            source_reasoning_allowed = False
        elif status == "usable_with_caution" or medium_issues or missing_sources:
            gate_status = "caution"
            max_confidence = "medium"
            source_reasoning_allowed = True
        else:
            gate_status = "pass"
            max_confidence = "high"
            source_reasoning_allowed = True

        interpretation_limits = []
        for issue in issues:
            message = issue.get("message") or issue.get("issue_type")
            if message:
                interpretation_limits.append({
                    "severity": issue.get("severity"),
                    "issue_type": issue.get("issue_type"),
                    "pollutant": issue.get("pollutant"),
                    "message": message,
                    "impact": issue.get("impact"),
                })
        for error in fetch_errors:
            interpretation_limits.append({
                "severity": error.get("severity", "warning"),
                "issue_type": "evidence_fetch_gap",
                "source": error.get("source"),
                "message": error.get("error"),
                "impact": "Missing evidence should lower confidence for mechanisms that depend on this source.",
            })

        return {
            "status": gate_status,
            "source_reasoning_allowed": source_reasoning_allowed,
            "max_confidence": max_confidence,
            "quality_status": status,
            "issue_count": len(issues),
            "high_issue_count": len(high_issues),
            "medium_issue_count": len(medium_issues),
            "missing_sources": [source for source in missing_sources if source],
            "interpretation_limits": interpretation_limits,
        }

    def _build_observed_signal_summary(
        self,
        event: Dict[str, Any],
        event_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "main_pollutant": event.get("main_pollutant"),
            "event_type": event.get("event_type"),
            "severity": event.get("severity"),
            "confidence": event.get("confidence"),
            "triggered_by": event.get("triggered_by", []),
            "time_range": event.get("time_range", {}),
            "lifecycle": event.get("event_lifecycle", {}),
            "city_peak": event_summary.get("city_peak"),
            "top_station_peaks": event_summary.get("station_peaks", [])[:5],
            "wind_summary": event_summary.get("wind_summary"),
            "cochange": event_summary.get("cochange", [])[:5],
            "record_counts": event_summary.get("record_counts", {}),
        }

    def _suggest_evidence_gaps(
        self,
        event: Dict[str, Any],
        event_summary: Dict[str, Any],
        fetch_errors: List[Dict[str, str]],
        station_records: List[Dict[str, Any]],
        weather_records: List[Dict[str, Any]],
        component_results: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        gaps: List[Dict[str, Any]] = []
        for item in event.get("next_data_needed", []):
            gaps.append({
                "priority": "medium",
                "evidence": item,
                "reason": "deterministic event detector requested this evidence for mechanism checks",
            })

        if not station_records:
            gaps.append({
                "priority": "high",
                "evidence": "station_hour_monitoring",
                "reason": "station synchrony and leading-site checks cannot be verified",
            })
        if not weather_records:
            gaps.append({
                "priority": "high",
                "evidence": "weather_hourly",
                "reason": "wind, dispersion, humidity, precipitation, and boundary-layer mechanisms cannot be verified",
            })

        main_pollutant = event.get("main_pollutant")
        component_files = component_results.get("files", {})
        if main_pollutant in {"PM2_5", "PM10"} and "pm25_components" not in component_files:
            gaps.append({
                "priority": "medium",
                "evidence": "pm25_components",
                "reason": "particle source hypotheses need ions, carbon, crustal, or PMF-related evidence when available",
            })
        if main_pollutant == "O3_8h" and "vocs_components" not in component_files:
            gaps.append({
                "priority": "medium",
                "evidence": "vocs_components",
                "reason": "ozone mechanism hypotheses need VOCs/NOx and photochemical precursor evidence when available",
            })

        for error in fetch_errors:
            gaps.append({
                "priority": "medium" if error.get("severity") == "warning" else "high",
                "evidence": error.get("source"),
                "reason": error.get("error"),
            })

        seen = set()
        deduped = []
        for gap in gaps:
            key = (gap.get("priority"), gap.get("evidence"), gap.get("reason"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(gap)
        return deduped

    def _extract_weather_records(
        self,
        city_records: List[Dict[str, Any]],
        station_records: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict[str, Any]]:
        weather_records: List[Dict[str, Any]] = []
        for source, records in (("city_hour", city_records), ("station_hour", station_records)):
            for record in self._filter_records_by_time(records, start_time, end_time):
                measurements = record.get("measurements", {}) if isinstance(record, dict) else {}
                weather = {field: self._as_number(measurements.get(field) or record.get(field)) for field in WEATHER_FIELDS}
                weather = {key: value for key, value in weather.items() if value is not None}
                if weather:
                    weather_records.append({
                        "timestamp": self._record_time_text(record),
                        "source": source,
                        "station_name": record.get("station_name") or record.get("city") or record.get("name"),
                        "lat": record.get("lat"),
                        "lon": record.get("lon"),
                        "measurements": weather,
                    })
        return weather_records

    def _filter_records_by_time(
        self,
        records: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict[str, Any]]:
        filtered = []
        for record in records:
            ts = self._record_time(record)
            if ts is None or start_time <= ts <= end_time:
                filtered.append(record)
        return filtered

    def _pollutant_series(
        self,
        records: List[Dict[str, Any]],
        spec: PollutantSpec | str,
    ) -> List[Tuple[Optional[datetime], Optional[float], Dict[str, Any]]]:
        if isinstance(spec, str):
            spec = self._spec_by_key(spec)
        series = []
        for record in records:
            ts = self._record_time(record)
            value = self._get_measurement(record, spec.aliases)
            series.append((ts, value, record))
        series.sort(key=lambda item: item[0] or datetime.min.replace(tzinfo=TZ_SHANGHAI))
        return series

    def _segments_from_flags(self, timeline_flags: Dict[datetime, List[Dict[str, Any]]]) -> List[List[datetime]]:
        times = sorted(timeline_flags)
        if not times:
            return []
        segments: List[List[datetime]] = []
        current = [times[0]]
        for ts in times[1:]:
            gap_hours = (ts - current[-1]).total_seconds() / 3600
            if gap_hours <= 2:
                current.append(ts)
            else:
                if len(current) >= self.config.min_event_points:
                    segments.append(current)
                current = [ts]
        if len(current) >= self.config.min_event_points:
            segments.append(current)
        return segments

    def _mark_sustained_streak(
        self,
        timeline_flags: Dict[datetime, List[Dict[str, Any]]],
        spec: PollutantSpec,
        streak: List[Tuple[datetime, float]],
        threshold: float,
    ) -> None:
        if len(streak) < 4:
            return
        values = [value for _, value in streak]
        if max(values) - min(values) < spec.step_threshold * 0.5 and max(values) < spec.absolute_threshold:
            return
        for ts, value in streak:
            timeline_flags.setdefault(ts, []).append({
                "pollutant": spec.key,
                "value": value,
                "unit": spec.unit,
                "reasons": ["sustained_elevated"],
                "threshold": threshold,
            })

    def _classify_event(
        self,
        main_pollutant: str,
        duration_hours: int,
        flags: List[Dict[str, Any]],
        records: List[Dict[str, Any]],
        event_start: datetime,
        event_end: datetime,
    ) -> str:
        reasons = {reason for flag in flags for reason in flag.get("reasons", [])}
        weather = self._extract_weather_records(records, [], event_start, event_end)
        wind = self._wind_summary(weather)
        low_wind = (
            wind.get("mean_wind_speed") is not None
            and wind["mean_wind_speed"] <= self.config.low_wind_speed_threshold
        )
        if main_pollutant == "O3_8h":
            return "ozone_photochemical_or_transport_process"
        if duration_hours <= 2 and "rapid_rise" in reasons:
            return "short_spike_or_impact_process"
        if duration_hours >= 4 and low_wind:
            return "sustained_accumulation_under_low_wind"
        max_wind_speed = wind.get("max_wind_speed") or 0
        if main_pollutant in {"PM10", "PM2_5"} and max_wind_speed >= 4:
            return "particle_process_with_wind_or_dust_signal"
        if duration_hours >= 4:
            return "sustained_pollution_process"
        return "significant_pollutant_change"

    def _event_severity(self, main_pollutant: str, scores: Dict[str, Dict[str, Any]]) -> str:
        aqi_peak = scores.get("AQI", {}).get("peak")
        if aqi_peak is not None:
            if aqi_peak >= 150:
                return "high"
            if aqi_peak >= 100:
                return "medium"
        main_peak = scores.get(main_pollutant, {}).get("peak")
        spec = self._spec_by_key(main_pollutant)
        if main_peak is not None and main_peak >= spec.absolute_threshold * 1.5:
            return "high"
        if main_peak is not None and main_peak >= spec.absolute_threshold:
            return "medium"
        return "low"

    def _event_confidence(self, quality_report: Dict[str, Any], flags: List[Dict[str, Any]], duration_hours: int) -> str:
        if quality_report.get("status") == "poor":
            return "low"
        pollutants = {flag["pollutant"] for flag in flags}
        reasons = {reason for flag in flags for reason in flag.get("reasons", [])}
        if len(pollutants) >= 2 and duration_hours >= 3 and ("absolute_threshold" in reasons or "sustained_elevated" in reasons):
            return "high" if quality_report.get("status") == "usable" else "medium"
        if len(flags) >= 3:
            return "medium"
        return "low"

    def _next_data_needed(self, main_pollutant: str, event_type: str) -> List[str]:
        needs = [
            "station_hour_monitoring for spatial synchrony and leading stations",
            "weather_hourly for wind, humidity, precipitation, and dispersion checks",
        ]
        if main_pollutant in {"PM2_5", "PM10"}:
            needs.append("PM2.5 components including ions, OC/EC, and crustal indicators")
        if main_pollutant == "O3_8h":
            needs.append("VOCs composition, NO2, radiation/temperature, and upwind city timing")
        if "low_wind" in event_type or "accumulation" in event_type:
            needs.append("boundary layer and low-wind persistence evidence")
        return needs

    def _peak_pollutant(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        best: Dict[str, Any] = {}
        for spec in POLLUTANTS:
            peak = self._series_peak(records, spec.key)
            if peak.get("value") is not None and (not best or peak["value"] > best.get("value", -math.inf)):
                best = {
                    "pollutant": spec.key,
                    "peak_value": peak["value"],
                    "unit": spec.unit,
                    "timestamp": peak.get("timestamp"),
                    "reason": "highest_available_peak",
                }
        return best

    def _series_peak(self, records: List[Dict[str, Any]], pollutant: str) -> Dict[str, Any]:
        spec = self._spec_by_key(pollutant)
        best = {"value": None, "timestamp": None}
        for ts, value, _ in self._pollutant_series(records, spec):
            if self._is_valid_number(value) and (best["value"] is None or value > best["value"]):
                best = {"value": value, "timestamp": self._format_api_time(ts) if ts else None}
        return best

    def _station_peaks(self, station_records: List[Dict[str, Any]], pollutant: str) -> List[Dict[str, Any]]:
        spec = self._spec_by_key(pollutant)
        by_station: Dict[str, Dict[str, Any]] = {}
        for record in station_records:
            station = record.get("station_name") or record.get("name") or record.get("station_code") or "unknown"
            value = self._get_measurement(record, spec.aliases)
            ts = self._record_time(record)
            if not self._is_valid_number(value):
                continue
            current = by_station.get(station)
            if current is None or value > current["peak_value"]:
                by_station[station] = {
                    "station_name": station,
                    "peak_value": value,
                    "unit": spec.unit,
                    "timestamp": self._format_api_time(ts) if ts else None,
                    "station_type": record.get("station_type"),
                }
        return sorted(by_station.values(), key=lambda item: item["peak_value"], reverse=True)

    def _wind_summary(self, weather_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        speeds = []
        directions = []
        humidity = []
        precipitation = []
        for record in weather_records:
            measurements = record.get("measurements", {})
            speed = self._as_number(measurements.get("wind_speed_10m"))
            direction = self._as_number(measurements.get("wind_direction_10m"))
            rh = self._as_number(measurements.get("relative_humidity_2m"))
            rain = self._as_number(measurements.get("precipitation"))
            if speed is not None and speed >= 0:
                speeds.append(speed)
            if direction is not None and 0 <= direction <= 360:
                directions.append(direction)
            if rh is not None:
                humidity.append(rh)
            if rain is not None:
                precipitation.append(rain)
        return {
            "mean_wind_speed": self._mean(speeds),
            "max_wind_speed": max(speeds) if speeds else None,
            "prevailing_wind_direction": self._circular_mean(directions),
            "mean_relative_humidity": self._mean(humidity),
            "total_precipitation": sum(precipitation) if precipitation else None,
            "records": len(weather_records),
        }

    def _pollutant_cochange(self, records: List[Dict[str, Any]], main_pollutant: str) -> List[Dict[str, Any]]:
        main_spec = self._spec_by_key(main_pollutant)
        main_values_by_time = {
            ts: value for ts, value, _ in self._pollutant_series(records, main_spec)
            if ts and self._is_valid_number(value)
        }
        cochanges = []
        for spec in POLLUTANTS:
            if spec.key == main_spec.key:
                continue
            other = {
                ts: value for ts, value, _ in self._pollutant_series(records, spec)
                if ts and self._is_valid_number(value)
            }
            common = sorted(set(main_values_by_time) & set(other))
            if len(common) < 4:
                continue
            corr = self._pearson([main_values_by_time[ts] for ts in common], [other[ts] for ts in common])
            if corr is not None:
                cochanges.append({"pollutant": spec.key, "correlation": corr, "points": len(common)})
        return sorted(cochanges, key=lambda item: abs(item["correlation"]), reverse=True)

    def _pm25_gt_pm10_issues(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pm25_spec = self._spec_by_key("PM2_5")
        pm10_spec = self._spec_by_key("PM10")
        issues = []
        for record in records:
            pm25 = self._get_measurement(record, pm25_spec.aliases)
            pm10 = self._get_measurement(record, pm10_spec.aliases)
            if self._is_valid_number(pm25) and self._is_valid_number(pm10) and pm25 > pm10 + 5:
                issues.append({
                    "timestamp": self._record_time_text(record),
                    "PM2_5": pm25,
                    "PM10": pm10,
                })
        return issues

    def _weather_missing_rate(self, records: List[Dict[str, Any]]) -> float:
        if not records:
            return 1.0
        total = len(records) * len(WEATHER_FIELDS)
        missing = 0
        for record in records:
            measurements = record.get("measurements", {}) if isinstance(record, dict) else {}
            for field in WEATHER_FIELDS:
                if self._as_number(measurements.get(field) or record.get(field)) is None:
                    missing += 1
        return missing / total if total else 1.0

    def _get_measurement(self, record: Dict[str, Any], aliases: Sequence[str]) -> Optional[float]:
        measurements = record.get("measurements", {}) if isinstance(record, dict) else {}
        for key in aliases:
            value = measurements.get(key)
            if value is not None:
                return self._as_number(value)
        for key in aliases:
            value = record.get(key)
            if value is not None:
                return self._as_number(value)
        return None

    def _record_time(self, record: Dict[str, Any]) -> Optional[datetime]:
        if not isinstance(record, dict):
            return None
        for key in ("timestamp", "time", "timePoint", "TimePoint", "datetime"):
            if key in record and record[key]:
                return self._parse_time(record[key])
        metadata = record.get("metadata")
        if isinstance(metadata, dict):
            for key in ("timestamp", "time", "timePoint"):
                if metadata.get(key):
                    return self._parse_time(metadata[key])
        return None

    def _record_time_text(self, record: Dict[str, Any]) -> Optional[str]:
        ts = self._record_time(record)
        return self._format_api_time(ts) if ts else None

    def _parse_time(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            dt = value
        elif value is None:
            return None
        else:
            text = str(value).strip()
            if not text:
                return None
            text = text.replace("Z", "+00:00")
            formats = (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d %H:%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%d",
            )
            dt = None
            for fmt in formats:
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if dt is None:
                try:
                    dt = datetime.fromisoformat(text)
                except ValueError:
                    return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=TZ_SHANGHAI)
        return dt.astimezone(TZ_SHANGHAI)

    def _format_api_time(self, value: Optional[datetime]) -> str:
        if value is None:
            return ""
        if value.tzinfo is not None:
            value = value.astimezone(TZ_SHANGHAI)
        return value.strftime("%Y-%m-%d %H:%M:%S")

    def _normalize_end_time(self, end_time: Optional[datetime]) -> datetime:
        if end_time is None:
            end_time = datetime.now(TZ_SHANGHAI)
        elif end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=TZ_SHANGHAI)
        else:
            end_time = end_time.astimezone(TZ_SHANGHAI)
        return end_time.replace(minute=0, second=0, microsecond=0)

    def _expected_hour_count(self, start_time: datetime, end_time: datetime) -> int:
        return int((end_time - start_time).total_seconds() // 3600) + 1

    def _load_data_records(self, data_id: Optional[str], result: Dict[str, Any]) -> List[Dict[str, Any]]:
        if data_id:
            try:
                records = self.context.get_raw_data(str(data_id))
                if isinstance(records, list):
                    return records
            except Exception as exc:
                logger.warning("monitor_context_data_load_failed", data_id=data_id, error=str(exc))
        data = result.get("data", []) if isinstance(result, dict) else []
        return data if isinstance(data, list) else []

    def _extract_data_id(self, result: Dict[str, Any]) -> Optional[str]:
        if not isinstance(result, dict):
            return None
        candidates = [
            result.get("data_id"),
            result.get("data_ref"),
        ]
        metadata = result.get("metadata")
        if isinstance(metadata, dict):
            candidates.extend([metadata.get("data_id"), metadata.get("data_ref")])
        for candidate in candidates:
            if candidate:
                if hasattr(candidate, "data_id"):
                    return str(candidate.data_id)
                if isinstance(candidate, dict):
                    value = candidate.get("data_id")
                    if value:
                        return str(value)
                return str(candidate)
        return None

    def _compact_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return {"raw": str(result)}
        compact = {key: value for key, value in result.items() if key != "data"}
        data = result.get("data")
        if isinstance(data, list):
            compact["sample_data"] = data[:5]
            compact["sample_count"] = min(len(data), 5)
        data_id = self._extract_data_id(result)
        if data_id:
            compact["data_id"] = data_id
        return compact

    def _resolve_output_root(self, output_root: Optional[Path]) -> Path:
        if output_root:
            root = Path(output_root)
            if not root.is_absolute():
                root = self.backend_dir / root
        else:
            root = self.backend_dir / "backend_data_registry" / "pollution_process_events"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _create_context(self, session_id: str) -> ExecutionContext:
        memory = HybridMemoryManager(session_id=session_id)
        data_manager = DataContextManager(memory)
        return ExecutionContext(session_id=session_id, iteration=0, data_manager=data_manager)

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _build_analysis_request(self, evidence_pack: Dict[str, Any]) -> str:
        event = evidence_pack["event"]
        return (
            "# 城市污染过程自动分析请求\n\n"
            f"- 城市: {evidence_pack['city']}\n"
            f"- 事件ID: {event['event_id']}\n"
            f"- 事件类型: {event['event_type']}\n"
            f"- 主污染物: {event['main_pollutant']}\n"
            f"- 时间范围: {event['time_range']['start']} 至 {event['time_range']['end']}\n"
            f"- 事件状态: {event.get('event_lifecycle', {}).get('status', 'unknown')}\n"
            f"- 质量门禁: {evidence_pack.get('quality_gate', {}).get('status', 'unknown')}\n"
            f"- 证据包: {evidence_pack['data_files']['event'].replace('event.json', 'evidence_pack.json')}\n"
            f"- 项目技能文档: {evidence_pack['analysis_contract']['skill_file']}\n\n"
            "请使用项目污染过程自动分析技能执行：先读取 evidence_pack 并列出可引用事实，再提出可检验假设，"
            "必要时主动补证，逐项核验证据和反证，最后在同目录写入 reasoning_analysis.md。\n"
        )

    def _build_run_summary(self, city_results: List[Dict[str, Any]], detected_count: int) -> str:
        parts = [f"Detected {detected_count} pollution process event(s)."]
        for result in city_results:
            parts.append(
                f"{result['city']}: {len(result.get('events', []))} event(s), "
                f"quality={result.get('quality_status')}, dir={result.get('run_dir')}"
            )
        return " ".join(parts)

    def _spec_by_key(self, key: str) -> PollutantSpec:
        normalized = key.replace(".", "_").upper()
        for spec in POLLUTANTS:
            if spec.key.upper() == normalized or key in spec.aliases:
                return spec
        return PollutantSpec(key, (key,), "", 0.0, 0.0)

    def _safe_name(self, value: str) -> str:
        safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value.strip(), flags=re.UNICODE)
        return safe.strip("_") or "unknown"

    def _as_number(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                return None
            return float(value)
        text = str(value).strip()
        if not text or text in {"-", "--", "—", "NA", "N/A", "null", "None"}:
            return None
        text = text.replace(",", "")
        try:
            number = float(text)
        except ValueError:
            return None
        if math.isnan(number) or math.isinf(number):
            return None
        return number

    def _is_valid_number(self, value: Optional[float]) -> bool:
        return value is not None and not math.isnan(value) and not math.isinf(value) and value >= 0

    def _median(self, values: Sequence[float]) -> Optional[float]:
        if not values:
            return None
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2

    def _mad(self, values: Sequence[float], median: Optional[float]) -> float:
        if not values or median is None:
            return 0.0
        deviations = [abs(value - median) for value in values]
        return self._median(deviations) or 0.0

    def _quantile(self, values: Sequence[float], q: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        pos = (len(ordered) - 1) * q
        lower = math.floor(pos)
        upper = math.ceil(pos)
        if lower == upper:
            return ordered[int(pos)]
        return ordered[lower] * (upper - pos) + ordered[upper] * (pos - lower)

    def _mean(self, values: Sequence[float]) -> Optional[float]:
        return sum(values) / len(values) if values else None

    def _circular_mean(self, degrees: Sequence[float]) -> Optional[float]:
        if not degrees:
            return None
        sin_sum = sum(math.sin(math.radians(value)) for value in degrees)
        cos_sum = sum(math.cos(math.radians(value)) for value in degrees)
        angle = math.degrees(math.atan2(sin_sum / len(degrees), cos_sum / len(degrees)))
        return (angle + 360) % 360

    def _pearson(self, xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
        if len(xs) != len(ys) or len(xs) < 3:
            return None
        mean_x = self._mean(xs)
        mean_y = self._mean(ys)
        if mean_x is None or mean_y is None:
            return None
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
        denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
        if denom_x == 0 or denom_y == 0:
            return None
        return numerator / (denom_x * denom_y)

    def _max_constant_streak(self, values: Sequence[float]) -> int:
        if not values:
            return 0
        max_streak = 1
        streak = 1
        for prev, current in zip(values, values[1:]):
            if abs(current - prev) < 1e-9:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 1
        return max_streak

    def _spike_count(self, values: Sequence[float], spec: PollutantSpec) -> int:
        if len(values) < 5:
            return 0
        median = self._median(values)
        mad = self._mad(values, median)
        count = 0
        for i in range(1, len(values) - 1):
            neighbor_avg = (values[i - 1] + values[i + 1]) / 2
            if values[i] - neighbor_avg >= max(spec.step_threshold * 1.8, 1.4826 * mad * 4):
                count += 1
        return count


async def run_pollution_event_monitor(config: MonitorConfig, context: Optional[ExecutionContext] = None) -> Dict[str, Any]:
    service = PollutionEventMonitorService(config=config, context=context)
    return await service.run()


def run_pollution_event_monitor_sync(config: MonitorConfig, context: Optional[ExecutionContext] = None) -> Dict[str, Any]:
    return asyncio.run(run_pollution_event_monitor(config=config, context=context))

"""Run quality-gated Scenario 2 trajectories for confirmed station-day pollution."""

from __future__ import annotations

import asyncio
import json
import math
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.tools.analysis.trajectory_source_analysis.trajectory_runner import TrajectoryRunner
from app.utils.path_config import format_agent_path, get_data_registry

from .cwt_analysis import XuchangStationConcentrationLoader, calculate_wcwt
from .interactive_map import build_transport_map_programs, write_transport_map_programs
from .spatial_analysis import (
    TrajectoryEnterpriseScreener,
    identify_transport_corridors_by_height,
)
from .visualization import generate_transport_maps

logger = structlog.get_logger()
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
REQUESTED_EVENT_TYPE = "xuchang.station_daily_source_analysis.requested"
COMPLETED_EVENT_TYPE = "xuchang.station_daily_source_analysis.completed"


@dataclass(frozen=True)
class PollutantTransportProfile:
    backtrack_hours: int
    heights_m_agl: tuple[int, int, int]
    local_evidence_hours: int
    local_evidence_max_height_m: int


POLLUTANT_TRANSPORT_PROFILES = {
    "PM2.5": PollutantTransportProfile(48, (100, 500, 1000), 6, 500),
    "O3": PollutantTransportProfile(48, (100, 500, 1000), 6, 500),
    "NOX": PollutantTransportProfile(24, (100, 300, 500), 6, 300),
}
CONTROL_LOOKBACK_HOURS = 6
MINIMUM_CLUSTER_TRAJECTORIES_PER_HEIGHT = 16
RECOMMENDED_CLUSTER_TRAJECTORIES_PER_HEIGHT = 30


def _parse_hour(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ_SHANGHAI)
    return parsed.astimezone(TZ_SHANGHAI).replace(minute=0, second=0, microsecond=0)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    value = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(value))


def assess_trajectory_quality(
    trajectory_result: dict[str, Any],
    *,
    expected_trajectories: int,
    backtrack_hours: int,
) -> dict[str, Any]:
    """Require enough complete endpoint series before interpreting transport."""
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for endpoint in trajectory_result.get("endpoints", []):
        key = (int(endpoint.get("batch_index", 0)), int(endpoint.get("trajectory_id", 1)))
        grouped[key].append(endpoint)

    minimum_coverage = backtrack_hours * 0.8
    complete_keys = []
    for key, endpoints in grouped.items():
        coverage = max((abs(float(item.get("age_hours", 0))) for item in endpoints), default=0.0)
        if coverage >= minimum_coverage:
            complete_keys.append(key)

    valid_trajectories = len(complete_keys)
    success_rate = valid_trajectories / expected_trajectories if expected_trajectories else 0.0
    sufficient = valid_trajectories >= 6 and success_rate >= 0.8
    return {
        "status": "sufficient" if sufficient else "insufficient",
        "expected_trajectories": expected_trajectories,
        "returned_trajectories": len(grouped),
        "valid_trajectories": valid_trajectories,
        "success_rate": round(success_rate, 3),
        "minimum_success_rate": 0.8,
        "minimum_valid_trajectories": 6,
        "minimum_coverage_hours": round(minimum_coverage, 1),
    }


def diagnose_transport_tendency(
    endpoints: list[dict[str, Any]],
    *,
    receptor_lat: float,
    receptor_lon: float,
    local_evidence_hours: int,
    max_height_m: float,
    quality: dict[str, Any],
) -> dict[str, Any]:
    """Produce a preliminary path tendency, never a causal contribution."""
    if quality.get("status") != "sufficient":
        return {
            "classification": "insufficient_evidence",
            "confidence": "low",
            "is_preliminary": True,
            "reason": "trajectory_quality_gate_not_met",
        }

    recent = [
        endpoint
        for endpoint in endpoints
        if abs(float(endpoint.get("age_hours", 0))) <= local_evidence_hours
        and float(endpoint.get("height", 0)) <= max_height_m
    ]
    if not recent:
        return {
            "classification": "insufficient_evidence",
            "confidence": "low",
            "is_preliminary": True,
            "reason": "no_recent_trajectory_endpoints",
        }

    local_count = sum(
        _haversine_km(
            receptor_lat,
            receptor_lon,
            float(endpoint["lat"]),
            float(endpoint["lon"]),
        )
        <= 50.0
        for endpoint in recent
    )
    local_residence_ratio = local_count / len(recent)
    if local_residence_ratio >= 0.6:
        classification = "local_accumulation"
    elif local_residence_ratio <= 0.35:
        classification = "regional_transport"
    else:
        classification = "mixed"
    return {
        "classification": classification,
        "confidence": "low",
        "is_preliminary": True,
        "local_radius_km": 50.0,
        "evidence_window_hours": local_evidence_hours,
        "maximum_evidence_height_m_agl": max_height_m,
        "local_residence_ratio": round(local_residence_ratio, 3),
        "interpretation_limit": (
            "仅表示后向轨迹停留特征；尚未融合周边城市时序、历史CWT和排放清单，"
            "不得解释为本地或区域污染贡献率。"
        ),
    }


class XuchangTransportEscalationService:
    """Create idempotent station-day analyses and execute pending NOAA jobs."""

    def __init__(
        self,
        output_root: Path | None = None,
        trajectory_runner: TrajectoryRunner | None = None,
        enterprise_screener: TrajectoryEnterpriseScreener | None = None,
        cwt_concentration_loader: XuchangStationConcentrationLoader | None = None,
        meteo_source: str = "gdas1",
        min_data_rate: float = 0.8,
        max_attempts: int = 6,
    ) -> None:
        self.output_root = output_root or get_data_registry() / "xuchang_transport_analysis"
        self.trajectory_runner = trajectory_runner
        self.enterprise_screener = enterprise_screener
        self.cwt_concentration_loader = (
            cwt_concentration_loader or XuchangStationConcentrationLoader()
        )
        self.meteo_source = meteo_source
        self.min_data_rate = min_data_rate
        self.max_attempts = max_attempts
        self._lock = RLock()

    @property
    def state_path(self) -> Path:
        return self.output_root / "process_state.json"

    def ingest_scenario_1_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        """Compatibility boundary: hourly Scenario 1 alerts never trigger Scenario 2."""
        return {
            "status": "ignored",
            "reason": "scenario_2_requires_confirmed_station_daily_exceedance",
            "job": None,
        }

    def ingest_daily_exceedance(self, event: dict[str, Any]) -> dict[str, Any]:
        """Create one idempotent daily analysis for station, pollutant and date."""
        pollutant = str(event.get("target_pollutant") or "").upper().replace("_8H", "")
        if pollutant not in POLLUTANT_TRANSPORT_PROFILES:
            return {"status": "ignored", "reason": "unsupported_pollutant", "job": None}
        if event.get("status") != "confirmed":
            return {"status": "ignored", "reason": "daily_exceedance_not_confirmed", "job": None}
        if (
            event.get("source_granularity") != "station_day"
            and float(event.get("data_rate") or 0) < self.min_data_rate
        ):
            return {"status": "ignored", "reason": "insufficient_data_rate", "job": None}
        station_id = str(event.get("station_id") or "").strip()
        target_date = str(event.get("target_date") or "").strip()
        if not station_id or not target_date:
            return {"status": "ignored", "reason": "missing_daily_identity", "job": None}
        try:
            day = datetime.fromisoformat(target_date).date()
            lat = float(event["lat"])
            lon = float(event["lon"])
        except (KeyError, TypeError, ValueError):
            return {"status": "ignored", "reason": "invalid_daily_identity", "job": None}

        pollutant_slug = pollutant.lower().replace(".", "")
        analysis_id = f"xuchang-daily-{day:%Y%m%d}-{station_id}-{pollutant_slug}"
        job_id = f"{analysis_id}-analysis"
        with self._lock:
            state = self._load_state()
            existing = state["daily_analyses"].get(analysis_id)
            if existing:
                return {
                    "status": "duplicate",
                    "analysis": existing,
                    "job": None,
                }

            day_start = datetime.combine(day, datetime.min.time(), tzinfo=TZ_SHANGHAI)
            hourly_rows = event.get("hourly_rows") or []
            concentrations = {}
            for row in hourly_rows:
                try:
                    hour = _parse_hour(row["time"])
                    value = row.get("concentration")
                    if hour.date() == day and value is not None:
                        concentrations[hour.isoformat()] = float(value)
                except (KeyError, TypeError, ValueError):
                    continue
            event_hours = [
                (day_start + timedelta(hours=hour)).isoformat()
                for hour in range(24)
            ]
            control_hours = [
                (day_start - timedelta(hours=offset)).isoformat()
                for offset in range(CONTROL_LOOKBACK_HOURS, 0, -1)
            ]
            profile = POLLUTANT_TRANSPORT_PROFILES[pollutant]
            analysis = {
                "analysis_id": analysis_id,
                "status": "pending",
                "city": event.get("city", "许昌市"),
                "station_id": station_id,
                "station_name": event.get("station_name") or station_id,
                "target_date": day.isoformat(),
                "target_pollutant": pollutant,
                "daily_value": event.get("daily_value"),
                "limit": event.get("limit"),
                "parent_event_id": event.get("event_id"),
                "job_id": job_id,
            }
            job = {
                "job_id": job_id,
                "event_id": job_id,
                "event_type": REQUESTED_EVENT_TYPE,
                "status": "pending",
                "attempts": 0,
                "created_at": datetime.now(TZ_SHANGHAI).isoformat(),
                "process_id": analysis_id,
                "analysis_id": analysis_id,
                "parent_event_ids": [event.get("event_id")],
                "city": analysis["city"],
                "station_id": station_id,
                "station_name": analysis["station_name"],
                "lat": lat,
                "lon": lon,
                "target_date": day.isoformat(),
                "target_pollutant": pollutant,
                "observed_indicator": event.get("observed_indicator"),
                "daily_value": event.get("daily_value"),
                "limit": event.get("limit"),
                "valid_hours": event.get("valid_hours"),
                "data_rate": event.get("data_rate"),
                "station_hourly": list(hourly_rows),
                "peer_station_daily": list(event.get("peer_station_daily") or []),
                "event_hours": event_hours,
                "event_concentrations": {
                    hour: concentrations.get(hour) for hour in event_hours
                },
                "control_event_hours": control_hours,
                "window_policy": "daily_hourly_arrivals_with_pre_day_control",
                "backtrack_hours": profile.backtrack_hours,
                "heights_m_agl": list(profile.heights_m_agl),
                "meteo_source": self.meteo_source,
            }
            state["daily_analyses"][analysis_id] = analysis
            state["jobs"][job_id] = job
            state["updated_at"] = datetime.now(TZ_SHANGHAI).isoformat()
            self._save_state(state)
            return {"status": "requested", "analysis": analysis, "job": job}

    async def run_pending(self, limit: int = 1) -> list[dict[str, Any]]:
        """Run a bounded number of pending jobs so NOAA load remains controlled."""
        jobs = self._claim_pending(limit)
        results = []
        trajectory_runner = self.trajectory_runner or TrajectoryRunner(max_concurrent=3)
        enterprise_screener = self.enterprise_screener or TrajectoryEnterpriseScreener()
        for job in jobs:
            try:
                event_hours = [_parse_hour(value) for value in job["event_hours"]]
                incremental_result = await trajectory_runner.run_event_trajectories(
                    lat=float(job["lat"]),
                    lon=float(job["lon"]),
                    event_times=event_hours,
                    pollutant=job["target_pollutant"],
                    meteo_source=job["meteo_source"],
                )
                control_hours = [_parse_hour(value) for value in job.get("control_event_hours", [])]
                control_result = None
                if control_hours:
                    control_result = await trajectory_runner.run_event_trajectories(
                        lat=float(job["lat"]),
                        lon=float(job["lon"]),
                        event_times=control_hours,
                        pollutant=job["target_pollutant"],
                        meteo_source=job["meteo_source"],
                    )
                trajectory_cache = self._merge_trajectory_cache(
                    job,
                    incremental_result=incremental_result,
                    event_hours=event_hours,
                    control_result=control_result,
                    control_hours=control_hours,
                )
                trajectory_result = trajectory_cache["pollution"]
                endpoints = trajectory_result.get("endpoints", [])
                cwt = await self._update_and_calculate_cwt(job, trajectory_cache)
                corridors_by_height = identify_transport_corridors_by_height(
                    endpoints,
                    heights_m_agl=job["heights_m_agl"],
                    receptor_lat=float(job["lat"]),
                    receptor_lon=float(job["lon"]),
                )
                primary_height = str(job["heights_m_agl"][0])
                corridors = corridors_by_height.get(primary_height, [])
                try:
                    enterprise_screening = await enterprise_screener.screen(
                        endpoints,
                        pollutant=job["target_pollutant"],
                        receptor_lat=float(job["lat"]),
                        receptor_lon=float(job["lon"]),
                    )
                except Exception as exc:
                    logger.exception(
                        "xuchang_transport_enterprise_screening_failed", job_id=job["job_id"]
                    )
                    enterprise_screening = {
                        "enterprises": [],
                        "coverage": {"status": "failed", "error": str(exc)},
                    }
                output_dir = self._output_dir(job)
                map_artifacts = generate_transport_maps(
                    output_dir=output_dir,
                    job_id=job["job_id"],
                    endpoints=endpoints,
                    corridors=corridors,
                    enterprise_screening=enterprise_screening,
                    receptor_lat=float(job["lat"]),
                    receptor_lon=float(job["lon"]),
                    pollutant=job["target_pollutant"],
                )
                map_programs = build_transport_map_programs(
                    job_id=job["job_id"],
                    station_name=job["station_name"],
                    pollutant=job["target_pollutant"],
                    endpoints=endpoints,
                    corridors=corridors,
                    enterprise_screening=enterprise_screening,
                    receptor_lat=float(job["lat"]),
                    receptor_lon=float(job["lon"]),
                )
                map_artifacts.extend(
                    write_transport_map_programs(
                        output_dir=output_dir,
                        job_id=job["job_id"],
                        programs=map_programs,
                    )
                )
                output = self._build_output(
                    job,
                    trajectory_result,
                    corridors=corridors,
                    corridors_by_height=corridors_by_height,
                    enterprise_screening=enterprise_screening,
                    map_artifacts=map_artifacts,
                    map_programs=map_programs,
                    trajectory_cache=trajectory_cache,
                    cwt=cwt,
                )
                output_path = self._write_output(job, output)
                output["output_path"] = format_agent_path(output_path)
                self._complete_job(job["job_id"], output)
                results.append(output)
            except Exception as exc:
                logger.exception("xuchang_transport_job_failed", job_id=job["job_id"])
                self._fail_job(job["job_id"], str(exc))
                results.append({"job_id": job["job_id"], "status": "failed", "error": str(exc)})
        return results

    def _build_output(
        self,
        job: dict[str, Any],
        trajectory_result: dict[str, Any],
        *,
        corridors: list[dict[str, Any]],
        corridors_by_height: dict[str, list[dict[str, Any]]],
        enterprise_screening: dict[str, Any],
        map_artifacts: list[dict[str, Any]],
        map_programs: dict[str, dict[str, Any]],
        trajectory_cache: dict[str, Any],
        cwt: dict[str, Any],
    ) -> dict[str, Any]:
        pollution_event_hours = trajectory_cache["pollution"]["event_hours"]
        control_event_hours = trajectory_cache["control"]["event_hours"]
        expected = len(pollution_event_hours) * len(job["heights_m_agl"])
        quality = assess_trajectory_quality(
            trajectory_result,
            expected_trajectories=expected,
            backtrack_hours=int(job["backtrack_hours"]),
        )
        control_quality = (
            assess_trajectory_quality(
                trajectory_cache["control"],
                expected_trajectories=len(control_event_hours) * len(job["heights_m_agl"]),
                backtrack_hours=int(job["backtrack_hours"]),
            )
            if control_event_hours
            else None
        )
        profile = POLLUTANT_TRANSPORT_PROFILES[job["target_pollutant"]]
        diagnosis = diagnose_transport_tendency(
            trajectory_result.get("endpoints", []),
            receptor_lat=float(job["lat"]),
            receptor_lon=float(job["lon"]),
            local_evidence_hours=profile.local_evidence_hours,
            max_height_m=profile.local_evidence_max_height_m,
            quality=quality,
        )
        return {
            "schema_version": "xuchang_station_daily_source_analysis/v2",
            "status": "completed" if quality["status"] == "sufficient" else "insufficient_evidence",
            "event_id": job["event_id"],
            "event_type": COMPLETED_EVENT_TYPE,
            "process_id": job["process_id"],
            "analysis_id": job.get("analysis_id", job["process_id"]),
            "parent_event_ids": job["parent_event_ids"],
            "city": job["city"],
            "station_id": job["station_id"],
            "station_name": job["station_name"],
            "target_pollutant": job["target_pollutant"],
            "target_date": job.get("target_date"),
            "daily_evaluation": {
                "value": job.get("daily_value"),
                "limit": job.get("limit"),
                "valid_hours": job.get("valid_hours"),
                "data_rate": job.get("data_rate"),
                "status": "confirmed_exceedance",
            },
            "station_hourly": job.get("station_hourly", []),
            "peer_station_daily": job.get("peer_station_daily", []),
            "observed_indicator": job.get("observed_indicator"),
            "trajectory_request": {
                "event_hours": pollution_event_hours,
                "incremental_event_hours": job["event_hours"],
                "control_event_hours": control_event_hours,
                "arrival_time_interval_hours": 1,
                "window_policy": job.get("window_policy"),
                "backtrack_hours": job["backtrack_hours"],
                "heights_m_agl": job["heights_m_agl"],
                "meteo_source": job["meteo_source"],
            },
            "trajectory_quality": quality,
            "control_trajectory_quality": control_quality,
            "transport_diagnosis": diagnosis,
            "trajectory_endpoints": trajectory_result.get("endpoints", []),
            "control_trajectory_endpoints": trajectory_cache["control"].get("endpoints", []),
            "transport_corridors": corridors,
            "transport_corridors_by_height": corridors_by_height,
            "primary_corridor_height_m_agl": job["heights_m_agl"][0],
            "trajectory_clustering_readiness": self._clustering_readiness(
                trajectory_result.get("endpoints", []),
                job["heights_m_agl"],
                int(job["backtrack_hours"]),
            ),
            "cwt": cwt,
            "enterprise_screening": enterprise_screening,
            "map_program": map_programs["regional"],
            "map_programs": map_programs,
            "visualizations": [
                {**artifact, "path": format_agent_path(artifact["path"])}
                for artifact in map_artifacts
            ],
            "noaa_jobs": trajectory_result.get("successful_jobs", []),
            "failed_noaa_jobs": trajectory_result.get("failed_jobs", []),
            "generated_at": datetime.now(TZ_SHANGHAI).isoformat(),
        }

    def _cwt_archive_path(self, job: dict[str, Any]) -> Path:
        pollutant = job["target_pollutant"].lower().replace(".", "")
        return self.output_root / "cwt_archives" / f"{job['station_id']}-{pollutant}.json"

    async def _update_and_calculate_cwt(
        self,
        job: dict[str, Any],
        trajectory_cache: dict[str, Any],
    ) -> dict[str, Any]:
        if job["target_pollutant"] != "PM2.5":
            return {
                "status": "not_enabled_for_pollutant",
                "enabled_pollutants": ["PM2.5"],
                "reason": "first_phase_pm25_only",
            }

        archive_path = self._cwt_archive_path(job)
        with self._lock:
            if archive_path.exists():
                try:
                    archive = json.loads(archive_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    archive = {}
            else:
                archive = {}
            archive.setdefault("schema_version", "xuchang_cwt_archive/v1")
            archive.setdefault("station_id", job["station_id"])
            archive.setdefault("station_name", job["station_name"])
            archive.setdefault("target_pollutant", job["target_pollutant"])
            samples = archive.setdefault("samples", {})
            for sample_group in ("control", "pollution"):
                group = trajectory_cache[sample_group]
                endpoints_by_hour: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for endpoint in group.get("endpoints", []):
                    endpoints_by_hour[endpoint["arrival_time"]].append(endpoint)
                for arrival_time in group.get("event_hours", []):
                    existing = samples.get(arrival_time, {})
                    if sample_group == "control" and existing.get("sample_group") == "pollution":
                        continue
                    concentration = group.get("concentrations", {}).get(arrival_time)
                    samples[arrival_time] = {
                        "arrival_time": arrival_time,
                        "sample_group": sample_group,
                        "concentration": (
                            concentration
                            if concentration is not None
                            else existing.get("concentration")
                        ),
                        "endpoints": endpoints_by_hour.get(arrival_time, []),
                    }
            archive["updated_at"] = datetime.now(TZ_SHANGHAI).isoformat()
            self._write_json(archive_path, archive)

        sample_count = len(samples)
        minimum_samples = RECOMMENDED_CLUSTER_TRAJECTORIES_PER_HEIGHT
        base = {
            "archive_path": format_agent_path(archive_path),
            "archive_sample_count": sample_count,
            "minimum_samples_per_height": minimum_samples,
            "sample_groups": {
                group: sum(sample.get("sample_group") == group for sample in samples.values())
                for group in ("pollution", "control")
            },
        }
        if sample_count < minimum_samples:
            return {
                **base,
                "status": "accumulating_samples",
                "remaining_samples": minimum_samples - sample_count,
            }

        event_hours = sorted(samples)
        try:
            concentrations = await asyncio.to_thread(
                self.cwt_concentration_loader.load,
                station_id=job["station_id"],
                pollutant=job["target_pollutant"],
                event_hours=event_hours,
            )
        except Exception as exc:
            logger.exception("xuchang_cwt_concentration_load_failed", station_id=job["station_id"])
            return {
                **base,
                "status": "concentration_data_unavailable",
                "error": str(exc),
            }

        for arrival_time, concentration in concentrations.items():
            if arrival_time in samples:
                samples[arrival_time]["concentration"] = concentration
        with self._lock:
            archive["updated_at"] = datetime.now(TZ_SHANGHAI).isoformat()
            self._write_json(archive_path, archive)

        result = calculate_wcwt(
            list(samples.values()),
            heights_m_agl=job["heights_m_agl"],
            backtrack_hours=int(job["backtrack_hours"]),
            minimum_trajectories_per_height=minimum_samples,
        )
        concentration_count = sum(
            isinstance(sample.get("concentration"), (int, float)) for sample in samples.values()
        )
        return {
            **base,
            **result,
            "concentration_coverage": round(concentration_count / sample_count, 3),
            "scope": "accumulated_pollution_events_and_pre_event_controls",
        }

    @staticmethod
    def _clustering_readiness(
        endpoints: list[dict[str, Any]],
        heights_m_agl: list[int],
        backtrack_hours: int,
    ) -> dict[str, Any]:
        grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for endpoint in endpoints:
            grouped[
                (int(endpoint.get("batch_index", 0)), int(endpoint.get("trajectory_id", 1)))
            ].append(endpoint)
        minimum_coverage = backtrack_hours * 0.8
        counts = {
            str(height): sum(
                max(
                    (
                        abs(float(item.get("age_hours", 0)))
                        for item in grouped.get((batch, trajectory_id), [])
                    ),
                    default=0.0,
                )
                >= minimum_coverage
                for batch in {key[0] for key in grouped}
            )
            for trajectory_id, height in enumerate(heights_m_agl, 1)
        }
        minimum_count = min(counts.values(), default=0)
        if minimum_count >= RECOMMENDED_CLUSTER_TRAJECTORIES_PER_HEIGHT:
            status = "recommended_sample_reached"
        elif minimum_count >= MINIMUM_CLUSTER_TRAJECTORIES_PER_HEIGHT:
            status = "minimum_sample_reached"
        else:
            status = "directional_screening_only"
        return {
            "status": status,
            "valid_trajectories_per_height": counts,
            "minimum_coverage_hours": minimum_coverage,
            "minimum_trajectories_per_height": MINIMUM_CLUSTER_TRAJECTORIES_PER_HEIGHT,
            "recommended_trajectories_per_height": RECOMMENDED_CLUSTER_TRAJECTORIES_PER_HEIGHT,
            "heights_clustered_separately": True,
            "interpretation_limit": (
                "低于最低样本量时仅输出逐时轨迹和方向走廊初筛，不宣称完成正式轨迹聚类。"
            ),
        }

    def _trajectory_cache_path(self, process_id: str) -> Path:
        return self.output_root / "process_trajectory_cache" / f"{process_id}.json"

    def _merge_trajectory_cache(
        self,
        job: dict[str, Any],
        *,
        incremental_result: dict[str, Any],
        event_hours: list[datetime],
        control_result: dict[str, Any] | None,
        control_hours: list[datetime],
    ) -> dict[str, Any]:
        path = self._trajectory_cache_path(job["process_id"])
        with self._lock:
            if path.exists():
                try:
                    cache = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    cache = {}
            else:
                cache = {}
            cache.setdefault("schema_version", "xuchang_transport_trajectory_cache/v1")
            cache.setdefault("process_id", job["process_id"])
            cache.setdefault("pollution", self._empty_trajectory_group())
            cache.setdefault("control", self._empty_trajectory_group())
            cache["pollution"] = self._merge_trajectory_group(
                cache["pollution"],
                incremental_result,
                event_hours,
                concentrations=job.get("event_concentrations", {}),
            )
            if control_result is not None:
                cache["control"] = self._merge_trajectory_group(
                    cache["control"], control_result, control_hours, concentrations={}
                )
            cache["updated_at"] = datetime.now(TZ_SHANGHAI).isoformat()
            self._write_json(path, cache)
        return cache

    @staticmethod
    def _empty_trajectory_group() -> dict[str, Any]:
        return {
            "event_hours": [],
            "endpoints": [],
            "successful_jobs": [],
            "failed_jobs": [],
            "concentrations": {},
        }

    @staticmethod
    def _merge_trajectory_group(
        existing: dict[str, Any],
        incremental: dict[str, Any],
        event_hours: list[datetime],
        *,
        concentrations: dict[str, float | None],
    ) -> dict[str, Any]:
        new_hour_keys = [hour.isoformat() for hour in event_hours]
        replacement_hours = set(new_hour_keys)
        retained = [
            endpoint
            for endpoint in existing.get("endpoints", [])
            if endpoint.get("arrival_time") not in replacement_hours
        ]
        annotated = []
        for endpoint in incremental.get("endpoints", []):
            batch_index = int(endpoint.get("batch_index", 0))
            if not 0 <= batch_index < len(new_hour_keys):
                continue
            annotated.append(
                {
                    **endpoint,
                    "arrival_time": new_hour_keys[batch_index],
                }
            )
        all_hours = sorted(set(existing.get("event_hours", [])) | set(new_hour_keys))
        batch_by_hour = {hour: index for index, hour in enumerate(all_hours)}
        endpoints = retained + annotated
        for endpoint in endpoints:
            endpoint["batch_index"] = batch_by_hour[endpoint["arrival_time"]]
        endpoints.sort(
            key=lambda item: (
                item["batch_index"],
                int(item.get("trajectory_id", 1)),
                abs(float(item.get("age_hours", 0))),
            )
        )
        successful_jobs = list(existing.get("successful_jobs", []))
        successful_jobs.extend(incremental.get("successful_jobs", []))
        failed_jobs = list(existing.get("failed_jobs", []))
        failed_jobs.extend(incremental.get("failed_jobs", []))
        merged_concentrations = dict(existing.get("concentrations", {}))
        merged_concentrations.update(
            {
                hour: float(value)
                for hour, value in concentrations.items()
                if value is not None and float(value) >= 0
            }
        )
        return {
            "event_hours": all_hours,
            "endpoints": endpoints,
            "successful_jobs": successful_jobs,
            "failed_jobs": failed_jobs,
            "concentrations": merged_concentrations,
        }

    @staticmethod
    def _evidence_snapshot(alert: dict[str, Any], occurred_at: datetime) -> dict[str, Any]:
        return {
            "event_id": alert.get("event_id"),
            "occurred_at": occurred_at.isoformat(),
            "station_value": alert.get("station_value"),
            "peer_baseline": alert.get("peer_baseline"),
            "absolute_delta": alert.get("absolute_delta"),
            "deviation_ratio": alert.get("deviation_ratio"),
            "data_rate": alert.get("data_rate"),
            "source_screening_status": alert.get("source_screening_status"),
        }

    def _claim_pending(self, limit: int) -> list[dict[str, Any]]:
        with self._lock:
            state = self._load_state()
            claimed = []
            for job in state["jobs"].values():
                if len(claimed) >= max(0, limit):
                    break
                if job.get("status") not in {"pending", "pending_retry"}:
                    continue
                if int(job.get("attempts", 0)) >= self.max_attempts:
                    continue
                job["status"] = "processing"
                job["attempts"] = int(job.get("attempts", 0)) + 1
                job["started_at"] = datetime.now(TZ_SHANGHAI).isoformat()
                claimed.append(dict(job))
            self._save_state(state)
            return claimed

    def _complete_job(self, job_id: str, output: dict[str, Any]) -> None:
        with self._lock:
            state = self._load_state()
            job = state["jobs"][job_id]
            job["status"] = "completed"
            job["completed_at"] = datetime.now(TZ_SHANGHAI).isoformat()
            job["result_status"] = output["status"]
            job["output_path"] = output["output_path"]
            analysis = state.get("daily_analyses", {}).get(job.get("analysis_id"))
            if analysis is not None:
                analysis["status"] = "completed"
                analysis["result_status"] = output["status"]
                analysis["output_path"] = output["output_path"]
                analysis["completed_at"] = job["completed_at"]
            self._save_state(state)

    def _fail_job(self, job_id: str, error: str) -> None:
        with self._lock:
            state = self._load_state()
            job = state["jobs"][job_id]
            job["last_error"] = error
            job["status"] = (
                "pending_retry" if int(job.get("attempts", 0)) < self.max_attempts else "failed"
            )
            analysis = state.get("daily_analyses", {}).get(job.get("analysis_id"))
            if analysis is not None:
                analysis["status"] = job["status"]
                analysis["last_error"] = error
            self._save_state(state)

    def _write_output(self, job: dict[str, Any], output: dict[str, Any]) -> Path:
        path = self._output_dir(job) / f"{job['job_id']}.json"
        output["output_path"] = format_agent_path(path)
        output["evidence_package_path"] = output["output_path"]
        self._write_json(path, output)
        return path

    def _output_dir(self, job: dict[str, Any]) -> Path:
        occurred_at = _parse_hour(job["event_hours"][-1])
        return self.output_root / occurred_at.strftime("%Y%m%d")

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {
                "schema_version": "xuchang_transport_process_state/v1",
                "updated_at": None,
                "active_processes": {},
                "process_history": [],
                "daily_analyses": {},
                "jobs": {},
            }
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
        state.setdefault("schema_version", "xuchang_transport_process_state/v1")
        state.setdefault("updated_at", None)
        state.setdefault("active_processes", {})
        state.setdefault("process_history", [])
        state.setdefault("daily_analyses", {})
        state.setdefault("jobs", {})
        return state

    def _save_state(self, state: dict[str, Any]) -> None:
        self._write_json(self.state_path, state)

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)
        temp_path.replace(path)

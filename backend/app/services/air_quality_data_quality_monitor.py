"""
Air quality data quality monitor.

The service runs deterministic station-level data quality checks on recent
hourly monitoring data. It only persists an issue package when suspicious data
quality signals are found; clean runs are returned as summaries without storing
extra packages.
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

logger = structlog.get_logger()

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class MetricSpec:
    key: str
    aliases: Sequence[str]
    aggregation: str = "mean"
    unit: str = "ug/m3"


METRICS: Tuple[MetricSpec, ...] = (
    MetricSpec("PM10", ("PM10", "pm10", "pM10")),
    MetricSpec("PM2_5", ("PM2_5", "PM2.5", "pm25", "pm2_5", "pM2_5")),
    MetricSpec("NO2", ("NO2", "no2", "nO2")),
    MetricSpec("O3_8h", ("O3_8h", "O3-8h", "o3_8h", "O3", "o3"), aggregation="max"),
    MetricSpec("CO", ("CO", "co"), unit="mg/m3"),
)


@dataclass
class DataQualityMonitorConfig:
    cities: List[str]
    hours: int = 24
    station_type: str = "国控"
    output_root: Optional[Path] = None
    end_time: Optional[datetime] = None
    min_points: int = 6
    min_aggregate_points: int = 12
    min_trend_points: int = 12
    persistent_hours: int = 6
    session_id: str = field(default_factory=lambda: f"data_quality_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}")


class AirQualityDataQualityMonitorService:
    """Fetch station hourly data, flag suspicious quality issues, and persist issue packages."""

    def __init__(self, config: DataQualityMonitorConfig, context: Optional[ExecutionContext] = None):
        self.config = config
        self.context = context or self._create_context(config.session_id)
        self.backend_dir = Path(__file__).resolve().parents[2]
        self.output_root = self._resolve_output_root(config.output_root)

    async def run(self) -> Dict[str, Any]:
        started_at = datetime.now(TZ_SHANGHAI)
        end_time = self._normalize_end_time(self.config.end_time)
        start_time = end_time - timedelta(hours=max(1, self.config.hours - 1))
        run_id = started_at.strftime("%Y%m%d_%H%M%S")

        logger.info(
            "air_quality_data_quality_monitor_started",
            cities=self.config.cities,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            output_root=str(self.output_root),
        )

        city_results = []
        for city in self.config.cities:
            city_results.append(self._run_city(city, start_time, end_time, run_id))

        issue_count = sum(result.get("issue_count", 0) for result in city_results)
        packages = [
            package
            for result in city_results
            for package in result.get("issue_packages", [])
        ]
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
            "issue_count": issue_count,
            "issue_packages": packages,
            "output_root": str(self.output_root),
            "summary": self._build_summary(city_results, issue_count),
        }

    def _run_city(self, city: str, start_time: datetime, end_time: datetime, run_id: str) -> Dict[str, Any]:
        fetch = self._fetch_station_hour_data(city, start_time, end_time)
        records = fetch.get("records", [])
        issues = self.evaluate_records(city, records)

        issue_packages: List[Dict[str, Any]] = []
        if issues:
            issue_packages.append(self._persist_issue_package(
                city=city,
                run_id=run_id,
                start_time=start_time,
                end_time=end_time,
                records=records,
                issues=issues,
                source_result=fetch.get("source_result", {}),
                data_id=fetch.get("data_id"),
            ))

        return {
            "city": city,
            "records": len(records),
            "station_count": len(self._group_by_station(records)),
            "issue_count": len(issues),
            "issue_packages": issue_packages,
            "discarded_clean_data": not bool(issues),
        }

    def evaluate_records(self, city: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not records:
            return [{
                "severity": "high",
                "rule_id": "no_station_hour_data",
                "city": city,
                "message": "No station hourly monitoring data was returned.",
                "recommendation": "Check data acquisition, station mapping, and API availability before judging environmental mechanisms.",
            }]

        issues: List[Dict[str, Any]] = []
        grouped = self._group_by_station(records)
        if len(grouped) < 3:
            issues.append({
                "severity": "medium",
                "rule_id": "too_few_peer_stations",
                "city": city,
                "station_count": len(grouped),
                "message": "Fewer than 3 stations were available; peer-comparison checks are weak.",
            })

        for spec in METRICS:
            issues.extend(self._daily_deviation_issues(city, grouped, spec))
            issues.extend(self._persistent_bias_issues(city, grouped, spec))
            issues.extend(self._trend_inconsistency_issues(city, grouped, spec))

        issues.extend(self._pm_cochange_issues(city, grouped))
        issues.extend(self._no2_o3_pattern_issues(city, grouped))
        return sorted(issues, key=lambda item: {"high": 0, "medium": 1, "low": 2}.get(item.get("severity"), 3))

    def _daily_deviation_issues(
        self,
        city: str,
        grouped: Dict[str, List[Dict[str, Any]]],
        spec: MetricSpec,
    ) -> List[Dict[str, Any]]:
        if spec.key not in {"PM10", "PM2_5", "NO2", "O3_8h"}:
            return []

        issues = []
        station_values = {}
        for station, records in grouped.items():
            values = [self._get_value(record, spec.aliases) for record in records]
            values = [value for value in values if self._is_valid_number(value)]
            if len(values) >= self.config.min_aggregate_points:
                station_values[station] = max(values) if spec.aggregation == "max" else sum(values) / len(values)

        if len(station_values) < 3:
            return []

        for station, value in station_values.items():
            peers = [peer_value for peer, peer_value in station_values.items() if peer != station]
            peer_mean = sum(peers) / len(peers)
            threshold = self._deviation_threshold(spec.key, value, peer_mean)
            if threshold is None:
                continue
            deviation = self._relative_deviation(value, peer_mean)
            if deviation is not None and deviation >= threshold:
                direction = "higher" if value > peer_mean else "lower"
                issues.append({
                    "severity": "high" if deviation >= threshold * 1.5 else "medium",
                    "rule_id": f"{spec.key.lower()}_daily_peer_deviation",
                    "city": city,
                    "station": station,
                    "pollutant": spec.key,
                    "direction": direction,
                    "station_value": round(value, 3),
                    "peer_mean": round(peer_mean, 3),
                    "deviation": round(deviation, 4),
                    "threshold": threshold,
                    "message": f"{station} {spec.key} aggregate deviates from same-city peers by {deviation:.0%}.",
                    "rule_basis": "参考文档：站点日均值/日最大值与同城其他站点偏差较大。",
                })
        return issues

    def _persistent_bias_issues(
        self,
        city: str,
        grouped: Dict[str, List[Dict[str, Any]]],
        spec: MetricSpec,
    ) -> List[Dict[str, Any]]:
        if spec.key not in {"PM10", "PM2_5", "NO2", "O3_8h"}:
            return []

        timelines = self._aligned_station_series(grouped, spec)
        issues = []
        for station, series in timelines.items():
            signed_flags: List[Tuple[datetime, float]] = []
            for ts, value in series:
                peer_values = [
                    peer_series.get(ts)
                    for peer, peer_series in self._series_maps(timelines).items()
                    if peer != station and peer_series.get(ts) is not None
                ]
                if len(peer_values) < 2:
                    self._append_persistent_issue(city, station, spec, signed_flags, issues)
                    signed_flags = []
                    continue
                peer_mean = sum(peer_values) / len(peer_values)
                threshold = self._deviation_threshold(spec.key, value, peer_mean) or 0.3
                deviation = self._relative_deviation(value, peer_mean)
                if deviation is not None and deviation >= threshold:
                    signed_flags.append((ts, 1.0 if value > peer_mean else -1.0))
                else:
                    self._append_persistent_issue(city, station, spec, signed_flags, issues)
                    signed_flags = []
            self._append_persistent_issue(city, station, spec, signed_flags, issues)
        return issues

    def _append_persistent_issue(
        self,
        city: str,
        station: str,
        spec: MetricSpec,
        flags: List[Tuple[datetime, float]],
        issues: List[Dict[str, Any]],
    ) -> None:
        if len(flags) < self.config.persistent_hours:
            return
        direction_sum = sum(flag for _, flag in flags)
        if abs(direction_sum) < len(flags) * 0.7:
            return
        direction = "higher" if direction_sum > 0 else "lower"
        issues.append({
            "severity": "medium",
            "rule_id": f"{spec.key.lower()}_persistent_peer_bias",
            "city": city,
            "station": station,
            "pollutant": spec.key,
            "direction": direction,
            "start": self._format_api_time(flags[0][0]),
            "end": self._format_api_time(flags[-1][0]),
            "duration_hours": len(flags),
            "message": f"{station} {spec.key} stayed {direction} than same-city peers for {len(flags)} hourly points.",
            "rule_basis": "参考文档：站点数据持续低于/高于同城其他站点。",
        })

    def _trend_inconsistency_issues(
        self,
        city: str,
        grouped: Dict[str, List[Dict[str, Any]]],
        spec: MetricSpec,
    ) -> List[Dict[str, Any]]:
        if spec.key not in {"PM10", "PM2_5", "NO2", "O3_8h"}:
            return []

        timelines = self._aligned_station_series(grouped, spec)
        series_maps = self._series_maps(timelines)
        issues = []
        for station, station_map in series_maps.items():
            xs = []
            ys = []
            for ts, value in station_map.items():
                peers = [
                    peer_map.get(ts)
                    for peer, peer_map in series_maps.items()
                    if peer != station and peer_map.get(ts) is not None
                ]
                if len(peers) >= 2 and value is not None:
                    xs.append(value)
                    ys.append(sum(peers) / len(peers))
            if len(xs) < self.config.min_trend_points:
                continue
            corr = self._corr(xs, ys)
            mean_deviation = self._relative_deviation(sum(xs) / len(xs), sum(ys) / len(ys))
            if corr is not None and mean_deviation is not None and corr < 0.0 and mean_deviation >= 0.15:
                issues.append({
                    "severity": "medium",
                    "rule_id": f"{spec.key.lower()}_trend_inconsistent_with_city",
                    "city": city,
                    "station": station,
                    "pollutant": spec.key,
                    "correlation": round(corr, 4),
                    "mean_deviation": round(mean_deviation, 4),
                    "points": len(xs),
                    "message": f"{station} {spec.key} trend is inconsistent with same-city peers.",
                    "rule_basis": "参考文档：站点数据与城市整体变化趋势不一致。",
                })
        return issues

    def _pm_cochange_issues(self, city: str, grouped: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        issues = []
        pm25 = self._spec("PM2_5")
        pm10 = self._spec("PM10")
        for station, records in grouped.items():
            xs, ys = self._paired_values(records, pm25.aliases, pm10.aliases)
            if len(xs) < self.config.min_trend_points:
                continue
            corr = self._corr(xs, ys)
            if corr is not None and corr < 0.2:
                issues.append({
                    "severity": "low",
                    "rule_id": "pm25_pm10_cochange_weak",
                    "city": city,
                    "station": station,
                    "pollutants": ["PM2_5", "PM10"],
                    "correlation": round(corr, 4),
                    "points": len(xs),
                    "message": f"{station} PM2.5 and PM10 do not show the expected co-change pattern.",
                    "rule_basis": "参考文档：PM10、PM2.5一般同步升高同步下降。",
                })
        return issues

    def _no2_o3_pattern_issues(self, city: str, grouped: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        issues = []
        no2 = self._spec("NO2")
        o3 = self._spec("O3_8h")
        for station, records in grouped.items():
            xs, ys = self._paired_values(records, no2.aliases, o3.aliases)
            if len(xs) < self.config.min_trend_points:
                continue
            corr = self._corr(xs, ys)
            if corr is not None and corr > 0.35:
                issues.append({
                    "severity": "low",
                    "rule_id": "no2_o3_expected_inverse_weak",
                    "city": city,
                    "station": station,
                    "pollutants": ["NO2", "O3_8h"],
                    "correlation": round(corr, 4),
                    "points": len(xs),
                    "message": f"{station} NO2 and O3 do not show the expected inverse pattern.",
                    "rule_basis": "参考文档：一般情况下 NO2 与 O3 负相关较好。",
                })
        return issues

    def _persist_issue_package(
        self,
        city: str,
        run_id: str,
        start_time: datetime,
        end_time: datetime,
        records: List[Dict[str, Any]],
        issues: List[Dict[str, Any]],
        source_result: Dict[str, Any],
        data_id: Optional[str],
    ) -> Dict[str, Any]:
        package_id = f"dq_{end_time.strftime('%Y%m%d%H')}_{self._safe_name(city)}"
        package_dir = self.output_root / self._safe_name(city) / run_id / package_id
        package_dir.mkdir(parents=True, exist_ok=True)

        station_summary = self._station_summary(records)
        quality_package = {
            "schema_version": "air_quality_data_quality_issue/v1",
            "created_at": datetime.now(TZ_SHANGHAI).isoformat(),
            "package_id": package_id,
            "city": city,
            "time_range": {
                "start": self._format_api_time(start_time),
                "end": self._format_api_time(end_time),
                "hours": self.config.hours,
            },
            "rule_source": "C:/Users/47688/Desktop/2异常数据判断规则和数据规律-2020.9.22.doc",
            "data_files": {
                "station_hour_monitoring": str(package_dir / "station_hour_monitoring.json"),
                "issues": str(package_dir / "issues.json"),
                "station_summary": str(package_dir / "station_summary.json"),
                "quality_package": str(package_dir / "quality_package.json"),
            },
            "data_refs": {
                "station_hour_data_id": data_id,
            },
            "issue_count": len(issues),
            "issues_by_severity": self._count_by(issues, "severity"),
            "top_issues": issues[:10],
            "analysis_contract": {
                "skill_file": str(self.backend_dir / "docs" / "skills" / "air_quality_data_quality_analysis.md"),
                "agent_goal": "Validate suspected data quality issues, distinguish instrument/data problems from real pollution, and write data_quality_analysis.md.",
                "required_outputs": [
                    "suspected_invalid_periods",
                    "rule_validation_matrix",
                    "environmental_counter_evidence",
                    "recommended_audit_action",
                    "confidence",
                ],
            },
        }

        self._write_json(package_dir / "station_hour_monitoring.json", {
            "city": city,
            "records": records,
            "source_result": source_result,
        })
        self._write_json(package_dir / "issues.json", {"issues": issues})
        self._write_json(package_dir / "station_summary.json", station_summary)
        self._write_json(package_dir / "quality_package.json", quality_package)
        self._write_text(package_dir / "analysis_request.md", self._build_analysis_request(quality_package))

        return {
            "package_id": package_id,
            "package_dir": str(package_dir),
            "quality_package": str(package_dir / "quality_package.json"),
            "analysis_request": str(package_dir / "analysis_request.md"),
            "issue_count": len(issues),
            "highest_severity": issues[0].get("severity") if issues else None,
        }

    def _fetch_station_hour_data(self, city: str, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        from app.tools.query.query_gd_suncere import execute_query_gd_suncere_station_hour_real

        result = execute_query_gd_suncere_station_hour_real(
            cities=[city],
            stations=None,
            station_type=self.config.station_type,
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

    def _deviation_threshold(self, pollutant: str, station_value: float, peer_value: float) -> Optional[float]:
        basis = max(station_value, peer_value)
        if pollutant == "PM10":
            return 0.30 if basis <= 70 else 0.20
        if pollutant == "PM2_5":
            if basis <= 35:
                return None
            return 0.20 if min(station_value, peer_value) > 35 else 0.30
        if pollutant == "O3_8h":
            return 0.30 if station_value <= 80 else 0.15
        if pollutant == "NO2":
            return 0.30
        return None

    def _relative_deviation(self, value: float, reference: float) -> Optional[float]:
        denominator = max(abs(reference), 1e-9)
        if denominator <= 0:
            return None
        return abs(value - reference) / denominator

    def _aligned_station_series(
        self,
        grouped: Dict[str, List[Dict[str, Any]]],
        spec: MetricSpec,
    ) -> Dict[str, List[Tuple[datetime, float]]]:
        aligned = {}
        for station, records in grouped.items():
            series = []
            for record in records:
                ts = self._record_time(record)
                value = self._get_value(record, spec.aliases)
                if ts and self._is_valid_number(value):
                    series.append((ts, value))
            aligned[station] = sorted(series, key=lambda item: item[0])
        return aligned

    def _series_maps(self, timelines: Dict[str, List[Tuple[datetime, float]]]) -> Dict[str, Dict[datetime, float]]:
        return {station: dict(series) for station, series in timelines.items()}

    def _paired_values(
        self,
        records: List[Dict[str, Any]],
        x_aliases: Sequence[str],
        y_aliases: Sequence[str],
    ) -> Tuple[List[float], List[float]]:
        xs = []
        ys = []
        for record in records:
            x = self._get_value(record, x_aliases)
            y = self._get_value(record, y_aliases)
            if self._is_valid_number(x) and self._is_valid_number(y):
                xs.append(x)
                ys.append(y)
        return xs, ys

    def _station_summary(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        grouped = self._group_by_station(records)
        summary = {}
        for station, station_records in grouped.items():
            item = {"record_count": len(station_records), "pollutants": {}}
            for spec in METRICS:
                values = [self._get_value(record, spec.aliases) for record in station_records]
                values = [value for value in values if self._is_valid_number(value)]
                if values:
                    item["pollutants"][spec.key] = {
                        "count": len(values),
                        "mean": round(sum(values) / len(values), 3),
                        "min": round(min(values), 3),
                        "max": round(max(values), 3),
                    }
            summary[station] = item
        return summary

    def _group_by_station(self, records: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for record in records:
            station = (
                record.get("station_name")
                or record.get("name")
                or record.get("station")
                or record.get("station_code")
                or "unknown_station"
            )
            grouped.setdefault(str(station), []).append(record)
        return grouped

    def _record_time(self, record: Dict[str, Any]) -> Optional[datetime]:
        for key in ("timestamp", "time", "time_point", "TimePoint", "monitor_time"):
            value = record.get(key)
            if value:
                return self._parse_time(value)
        return None

    def _get_value(self, record: Dict[str, Any], aliases: Sequence[str]) -> Optional[float]:
        measurements = record.get("measurements", {}) if isinstance(record.get("measurements"), dict) else {}
        for alias in aliases:
            for source in (measurements, record):
                if alias in source:
                    return self._as_number(source.get(alias))
        return None

    def _spec(self, key: str) -> MetricSpec:
        for spec in METRICS:
            if spec.key == key:
                return spec
        raise KeyError(key)

    def _corr(self, xs: List[float], ys: List[float]) -> Optional[float]:
        if len(xs) != len(ys) or len(xs) < 2:
            return None
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
        denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
        if denom_x == 0 or denom_y == 0:
            return None
        return numerator / (denom_x * denom_y)

    def _as_number(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(number) or math.isinf(number):
            return None
        return number

    def _is_valid_number(self, value: Any) -> bool:
        return isinstance(value, (int, float)) and not math.isnan(float(value)) and not math.isinf(float(value))

    def _parse_time(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip().replace("T", " ")
            dt = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
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

    def _normalize_end_time(self, end_time: Optional[datetime]) -> datetime:
        if end_time is None:
            end_time = datetime.now(TZ_SHANGHAI)
        elif end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=TZ_SHANGHAI)
        else:
            end_time = end_time.astimezone(TZ_SHANGHAI)
        return end_time.replace(minute=0, second=0, microsecond=0)

    def _format_api_time(self, value: Optional[datetime]) -> str:
        if value is None:
            return ""
        if value.tzinfo is not None:
            value = value.astimezone(TZ_SHANGHAI)
        return value.strftime("%Y-%m-%d %H:%M:%S")

    def _extract_data_id(self, result: Dict[str, Any]) -> Optional[str]:
        if not isinstance(result, dict):
            return None
        candidates = [result.get("data_id"), result.get("data_ref")]
        metadata = result.get("metadata")
        if isinstance(metadata, dict):
            candidates.extend([metadata.get("data_id"), metadata.get("data_ref")])
        for candidate in candidates:
            if candidate:
                if hasattr(candidate, "data_id"):
                    return str(candidate.data_id)
                if isinstance(candidate, dict) and candidate.get("data_id"):
                    return str(candidate["data_id"])
                return str(candidate)
        return None

    def _load_data_records(self, data_id: Optional[str], result: Dict[str, Any]) -> List[Dict[str, Any]]:
        if data_id:
            try:
                records = self.context.get_raw_data(str(data_id))
                if isinstance(records, list):
                    return records
            except Exception as exc:
                logger.warning("data_quality_monitor_context_load_failed", data_id=data_id, error=str(exc))
        data = result.get("data", []) if isinstance(result, dict) else []
        return data if isinstance(data, list) else []

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

    def _count_by(self, items: List[Dict[str, Any]], key: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in items:
            value = str(item.get(key, "unknown"))
            counts[value] = counts.get(value, 0) + 1
        return counts

    def _safe_name(self, value: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value, flags=re.UNICODE).strip("_") or "unknown"

    def _resolve_output_root(self, output_root: Optional[Path]) -> Path:
        if output_root:
            root = Path(output_root)
            if not root.is_absolute():
                root = self.backend_dir / root
        else:
            root = self.backend_dir / "backend_data_registry" / "data_quality_issues"
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

    def _build_analysis_request(self, quality_package: Dict[str, Any]) -> str:
        return f"""# 空气质量数据质量自动分析请求

- 城市: {quality_package["city"]}
- 问题包ID: {quality_package["package_id"]}
- 时间范围: {quality_package["time_range"]["start"]} 至 {quality_package["time_range"]["end"]}
- 疑似问题数: {quality_package["issue_count"]}
- 问题包: {quality_package["data_files"]["quality_package"]}
- 技能文档: {quality_package["analysis_contract"]["skill_file"]}

请按技能文档执行：先读取 quality_package，再核查规则命中是否成立，区分仪器/质控问题与真实环境污染影响，最后在同目录写入 data_quality_analysis.md。
"""

    def _build_summary(self, city_results: List[Dict[str, Any]], issue_count: int) -> str:
        parts = [f"Detected {issue_count} suspected data quality issue(s)."]
        for result in city_results:
            if result.get("issue_count"):
                package_paths = [item.get("quality_package") for item in result.get("issue_packages", [])]
                parts.append(f"{result['city']}: {result['issue_count']} issue(s), packages={package_paths}")
            else:
                parts.append(f"{result['city']}: no suspected issues, clean data discarded")
        return " ".join(parts)


async def run_air_quality_data_quality_monitor(
    config: DataQualityMonitorConfig,
    context: Optional[ExecutionContext] = None,
) -> Dict[str, Any]:
    service = AirQualityDataQualityMonitorService(config=config, context=context)
    return await service.run()


def run_air_quality_data_quality_monitor_sync(
    config: DataQualityMonitorConfig,
    context: Optional[ExecutionContext] = None,
) -> Dict[str, Any]:
    return asyncio.run(run_air_quality_data_quality_monitor(config=config, context=context))

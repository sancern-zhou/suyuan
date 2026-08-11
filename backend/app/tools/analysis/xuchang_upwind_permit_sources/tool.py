"""Strict Scenario-1 upwind permit-source analysis for Xuchang."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

from .engine import (
    MAX_WIND_DIRECTION_DIFFERENCE_DEG,
    MIN_WIND_SPEED_MS,
    XUCHANG_WEATHER_STATIONS,
    bearing_deg,
    candidate_hour_score,
    circular_difference_deg,
    classify_stability,
    dispersion_weight,
    haversine_km,
    industry_factor,
    nearest_station,
    pollutant_relevance,
    pollutant_relevance_factor,
    strict_hour_weather,
)
from .repository import XuchangUpwindPermitRepository

logger = structlog.get_logger()
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
TOOL_NAME = "analyze_xuchang_upwind_permit_sources"


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING_TZ)
    return parsed.astimezone(BEIJING_TZ)


def _hour_key(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=BEIJING_TZ)
    return value.astimezone(BEIJING_TZ).replace(minute=0, second=0, microsecond=0)


def _query_time(value: datetime) -> datetime:
    """Observed NMC rows are stored as Asia/Shanghai timestamps."""
    return value.astimezone(BEIJING_TZ)


def _event_hours(start_time: datetime, end_time: datetime) -> list[datetime]:
    start = _hour_key(start_time)
    end = _hour_key(end_time)
    return [start + timedelta(hours=index) for index in range(int((end - start).total_seconds() // 3600) + 1)]


def _stability_record(records: list[Any], hour: datetime, receptor_lat: float, receptor_lon: float) -> Any | None:
    matching = [record for record in records if _hour_key(record.time) == hour]
    if not matching:
        return None
    return min(
        matching,
        key=lambda record: haversine_km(receptor_lat, receptor_lon, float(record.lat), float(record.lon)),
    )


class AnalyzeXuchangUpwindPermitSourcesTool(LLMTool):
    """Return strict spatial-temporal candidate evidence from Xuchang permits."""

    def __init__(self, repository: XuchangUpwindPermitRepository | None = None) -> None:
        super().__init__(
            name="analyze_xuchang_upwind_permit_sources",
            description=(
                "基于许昌、禹州、长葛气象观测与有效排污许可证，严格筛选已知异常受体点"
                "在给定时段的上风向许可证企业。仅返回空间-时间一致性事实，不返回贡献率、责任或处置建议。"
            ),
            category=ToolCategory.ANALYSIS,
            version="1.0.0",
            function_schema={
                "name": "analyze_xuchang_upwind_permit_sources",
                "description": "许昌场景一：严格代表站上风向许可证企业空间-时间一致性分析。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "station_name": {"type": "string", "description": "异常受体站名称"},
                        "lat": {"type": "number", "description": "异常受体纬度"},
                        "lon": {"type": "number", "description": "异常受体经度"},
                        "pollutant": {"type": "string", "enum": ["PM2.5", "O3", "NOX"]},
                        "start_time": {"type": "string", "description": "事件窗口开始，ISO-8601 或 YYYY-MM-DD HH:MM:SS"},
                        "end_time": {"type": "string", "description": "事件窗口结束，ISO-8601 或 YYYY-MM-DD HH:MM:SS"},
                        "candidate_radius_km": {"type": "number", "default": 5, "minimum": 1, "maximum": 50},
                        "top_n": {"type": "integer", "default": 15, "minimum": 1, "maximum": 50},
                        "event_context": {"type": "object", "description": "事件脚本已确认的站点偏差等上下文；工具仅原样回传"},
                    },
                    "required": ["station_name", "lat", "lon", "pollutant", "start_time", "end_time"],
                },
            },
        )
        self.repository = repository or XuchangUpwindPermitRepository()

    async def execute(
        self,
        station_name: str,
        lat: float,
        lon: float,
        pollutant: str,
        start_time: str,
        end_time: str,
        candidate_radius_km: float = 5.0,
        top_n: int = 15,
        event_context: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return self._failure("invalid_receptor_coordinates")
        if pollutant not in {"PM2.5", "O3", "NOX"}:
            return self._failure("unsupported_pollutant")
        if not 1 <= candidate_radius_km <= 50:
            return self._failure("candidate_radius_km_must_be_between_1_and_50")

        try:
            start = _parse_time(start_time)
            end = _parse_time(end_time)
        except ValueError:
            return self._failure("invalid_time_format")
        if end < start or end - start > timedelta(hours=24):
            return self._failure("event_window_must_be_between_0_and_24_hours")

        representative = nearest_station(lat, lon)
        observed, era5 = await self.repository.load_weather(
            station_ids=[station.station_id for station in XUCHANG_WEATHER_STATIONS],
            start_time=_query_time(start),
            end_time=_query_time(end),
            receptor_lat=lat,
            receptor_lon=lon,
        )
        candidates = await self.repository.load_candidates(
            receptor_lat=lat,
            receptor_lon=lon,
            radius_km=candidate_radius_km,
        )
        historical_wind_speed_ms, historical_wind_source = await self._historical_wind_mean(
            representative.station_id, start
        )

        observed_by_hour: dict[datetime, dict[str, dict[str, Any]]] = {}
        for record in observed:
            observed_by_hour.setdefault(_hour_key(record.time), {})[record.station_id] = {
                "wind_speed_10m": record.wind_speed_10m,
                "wind_direction_10m": record.wind_direction_10m,
                "data_quality": record.data_quality,
            }

        hourly = []
        usable_hours = []
        for hour in _event_hours(start, end):
            weather = strict_hour_weather(
                timestamp=hour,
                representative=representative,
                station_records=observed_by_hour.get(hour, {}),
                min_wind_speed_ms=MIN_WIND_SPEED_MS,
                max_direction_difference_deg=MAX_WIND_DIRECTION_DIFFERENCE_DEG,
            )
            era5_record = _stability_record(era5, hour, lat, lon)
            if weather["usable"]:
                stability = classify_stability(
                    boundary_layer_height_m=getattr(era5_record, "boundary_layer_height", None),
                    cloud_cover_pct=getattr(era5_record, "cloud_cover", None),
                    timestamp=hour,
                    latitude_deg=lat,
                    wind_speed_ms=weather["wind_speed_ms"],
                )
                stability["source"] = "ERA5" if era5_record else None
                weather["stability"] = stability
                usable_hours.append(weather)
            else:
                weather["stability"] = {"status": "not_assessed", "stability_class": None}
            hourly.append(weather)

        # Scenario 1 is an hourly, rapid response. A validated current hour is
        # sufficient; multi-hour persistence belongs to Scenario 2.
        min_required_hours = 1
        if len(usable_hours) < min_required_hours:
            return {
                "status": "insufficient_meteorology",
                "success": False,
                "summary": f"严格风场校验后仅有{len(usable_hours)}个有效小时，少于{min_required_hours}个，未生成企业候选排序。",
                "metadata": self._result_metadata(candidate_count=0, total_candidate_count=0),
                "data": {
                    "trigger_context": event_context or {},
                    "weather_selection": self._weather_selection(representative, lat, lon, hourly),
                    "hourly_meteorology": hourly,
                    "candidates": [],
                },
            }

        matched = self._score_candidates(
            candidates=candidates,
            usable_hours=usable_hours,
            receptor_lat=lat,
            receptor_lon=lon,
            pollutant=pollutant,
            radius_km=candidate_radius_km,
            historical_wind_speed_ms=historical_wind_speed_ms,
        )
        matched.sort(key=lambda item: item["final_score"], reverse=True)
        enterprises_in_fan = len(matched)
        matched = matched[:max(1, min(int(top_n), 50))]
        scenario_output = self._scenario_output(
            event_context=event_context or {},
            usable_hours=usable_hours,
            candidates=matched,
            enterprises_in_fan=enterprises_in_fan,
            radius_km=candidate_radius_km,
            historical_wind_speed_ms=historical_wind_speed_ms,
            historical_wind_source=historical_wind_source,
        )
        payload = {
            "trigger_context": event_context or {},
            "receptor": {"station_name": station_name, "lat": lat, "lon": lon},
            "pollutant": pollutant,
            "event_window": {"start_time": start.isoformat(), "end_time": end.isoformat()},
            "weather_selection": self._weather_selection(representative, lat, lon, hourly),
            "hourly_meteorology": hourly,
            "analysis_quality": {
                "valid_hours": len(usable_hours),
                "total_hours": len(hourly),
                "weather_coverage": round(len(usable_hours) / len(hourly), 3),
                "stability_hours_available": sum(1 for item in usable_hours if item["stability"]["status"] == "available"),
                "permit_candidates_in_radius": len(candidates),
                "limitations": [
                    "许可证信息不代表事件时段实际排放或生产工况。",
                    "许可证公开数据没有企业年排放量；候选排序不使用或推断年排放量。",
                    "结果仅用于现场核查优先级，不输出企业贡献率或责任结论。",
                ] + (["NOX类别使用站点NO2小时浓度作为空间异常代理，不代表总NOx实测浓度。"] if pollutant == "NOX" else []),
            },
            "candidates": matched,
            "scenario_1_output": scenario_output,
            "method": {
                "scenario": "local_station_deviation_upwind_source_screening",
                "wind_mode": "nearest_station_strict",
                "fallbacks": "disabled",
                "sector_half_angle_deg": "dynamic_30_45_60",
                "score_type": "dimensionless_evidence_score_not_contribution",
                "algorithm_version": self.version,
            },
        }
        return {
            "status": "success",
            "success": True,
            "summary": f"{station_name}在严格风场校验后有{len(usable_hours)}个有效小时，发现{enterprises_in_fan}家空间-时间一致的许可证企业。",
            "metadata": self._result_metadata(
                candidate_count=len(matched),
                total_candidate_count=enterprises_in_fan,
            ),
            "data": payload,
        }

    def _result_metadata(self, *, candidate_count: int, total_candidate_count: int) -> dict[str, Any]:
        return {
            "schema_version": "v1.0",
            "tool_name": TOOL_NAME,
            "generator": TOOL_NAME,
            "algorithm_version": self.version,
            "candidate_count": candidate_count,
            "total_candidate_count": total_candidate_count,
        }

    @staticmethod
    def _weather_selection(representative: Any, lat: float, lon: float, hourly: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "representative_station": representative.station_name,
            "representative_station_id": representative.station_id,
            "selection_method": "nearest_station_strict",
            "distance_to_receptor_km": round(haversine_km(lat, lon, representative.lat, representative.lon), 2),
            "matched_hours": sum(1 for item in hourly if item["usable"]),
            "excluded_hours": [
                {"time": item["time"], "reason": item["reason"]}
                for item in hourly if not item["usable"]
            ],
        }

    @staticmethod
    def _score_candidates(
        *,
        candidates: list[dict[str, Any]],
        usable_hours: list[dict[str, Any]],
        receptor_lat: float,
        receptor_lon: float,
        pollutant: str,
        radius_km: float,
        historical_wind_speed_ms: float,
    ) -> list[dict[str, Any]]:
        results = []
        for candidate in candidates:
            distance_km = haversine_km(receptor_lat, receptor_lon, candidate["latitude"], candidate["longitude"])
            if distance_km > radius_km:
                continue
            bearing = bearing_deg(receptor_lat, receptor_lon, candidate["latitude"], candidate["longitude"])
            hour_matches = []
            for weather in usable_hours:
                difference = circular_difference_deg(bearing, weather["wind_from_deg"])
                sector_half_angle = weather["sector_half_angle_deg"]
                if difference > sector_half_angle:
                    continue
                hour_matches.append({
                    "time": weather["time"],
                    "angle_difference_deg": round(difference, 1),
                    "sector_half_angle_deg": sector_half_angle,
                    "score": round(candidate_hour_score(distance_km=distance_km, angle_difference_deg=difference, sector_half_angle_deg=sector_half_angle), 4),
                })
            if not hour_matches:
                continue
            permit_text = " ".join(filter(None, [candidate.get("permit_pollutants"), candidate.get("main_pollutant_categories")]))
            relevance = pollutant_relevance(pollutant, permit_text)
            relevance_factor = pollutant_relevance_factor(pollutant, relevance, bool(permit_text.strip()))
            longest = AnalyzeXuchangUpwindPermitSourcesTool._longest_consecutive_hours(hour_matches)
            dispersion_scores = []
            for item in hour_matches:
                weather = next(weather for weather in usable_hours if weather["time"] == item["time"])
                dispersion_scores.append(dispersion_weight(
                    distance_km=distance_km,
                    angle_difference_deg=item["angle_difference_deg"],
                    wind_speed_ms=weather["wind_speed_ms"],
                    historical_wind_speed_ms=historical_wind_speed_ms,
                    stability=weather["stability"].get("stability_class") or "D",
                ))
            sector_score = sum(item["score"] for item in hour_matches) / len(usable_hours)
            sector = candidate.get("industry_category") or "其他"
            sector_factor = industry_factor(sector)
            # Industry is a weak prior, not a substitute for source-specific
            # emission evidence. Limit it to a quarter of the configured effect.
            industry_prior = 1 + (sector_factor - 1) * 0.25
            final_score = sector_score * relevance_factor * industry_prior
            level = (
                "strong"
                if len(hour_matches) >= 3 and longest >= 2 and relevance != "no_recorded_match"
                else "moderate"
                if len(hour_matches) >= 2 and relevance != "no_recorded_match"
                else "weak"
            )
            results.append({
                **candidate,
                "distance_km": round(distance_km, 2),
                "bearing_deg": round(bearing, 1),
                "upwind_matched_hours": len(hour_matches),
                "longest_consecutive_hours": longest,
                "mean_angle_difference_deg": round(sum(item["angle_difference_deg"] for item in hour_matches) / len(hour_matches), 1),
                "pollutant_relevance": relevance,
                "pollutant_relevance_factor": relevance_factor,
                "spatial_temporal_score": round(sector_score, 4),
                "dispersion_weight": sum(dispersion_scores) / len(dispersion_scores),
                "industry_factor": sector_factor,
                "industry_prior": round(industry_prior, 4),
                "emission_pmf": None,
                "emission_norm": None,
                "emission_data_status": "unavailable_in_permit_data",
                "final_score": round(final_score, 6),
                "evidence_level": level,
                "evidence_items": hour_matches,
            })
        return results

    async def _historical_wind_mean(self, station_id: str, event_hour: datetime) -> tuple[float, str]:
        loader = getattr(self.repository, "load_historical_wind_speeds", None)
        if loader is not None:
            records = await loader(station_id=station_id, event_hour=_query_time(event_hour))
            cutoff_30 = event_hour - timedelta(days=30)
            cutoff_7 = event_hour - timedelta(days=7)
            valid = [
                (_hour_key(timestamp), float(speed))
                for timestamp, speed in records
                if speed is not None and float(speed) > 0
            ]
            same_time = [
                (timestamp, speed) for timestamp, speed in valid
                if min(abs(timestamp.hour - event_hour.hour), 24 - abs(timestamp.hour - event_hour.hour)) <= 2
            ]
            last_30 = [speed for timestamp, speed in same_time if timestamp >= cutoff_30]
            if len(last_30) >= 10:
                return sum(last_30) / len(last_30), "30day_same_hour_plus_minus_2h"
            last_7 = [speed for timestamp, speed in same_time if timestamp >= cutoff_7]
            if len(last_7) >= 5:
                return sum(last_7) / len(last_7), "7day_same_hour_plus_minus_2h"
            if same_time:
                speeds = [speed for _, speed in same_time]
                return sum(speeds) / len(speeds), "annual_same_hour_plus_minus_2h"
            if valid:
                speeds = [speed for _, speed in valid]
                return sum(speeds) / len(speeds), "annual_all_hour_mean"
        # No historical wind baseline must not suppress a valid rapid alert.
        return 1.0, "default_1ms_missing_historical_wind"

    @staticmethod
    def _scenario_output(
        *,
        event_context: dict[str, Any],
        usable_hours: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        enterprises_in_fan: int,
        radius_km: float,
        historical_wind_speed_ms: float,
        historical_wind_source: str,
    ) -> dict[str, Any]:
        weather = usable_hours[-1]
        stability = weather["stability"].get("stability_class") or "D"
        top1 = candidates[0] if candidates else None
        top2 = candidates[1] if len(candidates) > 1 else None
        margin = None
        if top1 and top2 and top2["final_score"] > 0:
            margin = (top1["final_score"] - top2["final_score"]) / top2["final_score"] * 100
        confidence = "low"
        if (
            candidates
            and weather["wind_speed_ms"] <= 5
            and candidates[0]["pollutant_relevance"] != "no_recorded_match"
            and (event_context.get("data_rate") or 0) >= 0.8
        ):
            confidence = "medium"
        # Annual emissions are unavailable by design, so the scheme cannot
        # claim the plan's high-confidence source attribution category.
        trigger = {
            "type": "spatial_deviation",
            "station": event_context.get("station_name"),
            "lon": event_context.get("lon"),
            "lat": event_context.get("lat"),
            "station_value": event_context.get("station_value"),
            "city_mean_excluding": event_context.get("peer_mean"),
            "deviation_pct": event_context.get("deviation_percent"),
            "threshold_pct": (event_context.get("threshold") or 0) * 100,
            "indicator": event_context.get("target_pollutant"),
            "observed_indicator": event_context.get("observed_indicator"),
            "trigger_time": event_context.get("occurred_at"),
            "valid_stations_count": event_context.get("available_station_count"),
        }
        ranked = [
            {
                "rank": rank,
                "name": item["enterprise_name"],
                "sector": item.get("industry_category") or "其他",
                "distance_km": item["distance_km"],
                "direction_deg": item["bearing_deg"],
                "emission_pmf": None,
                "emission_norm": None,
                "industry_factor": item["industry_factor"],
                "pollutant_relevance": item["pollutant_relevance"],
                "pollutant_relevance_factor": item["pollutant_relevance_factor"],
                "final_score": item["final_score"],
                "contribution_level": "candidate_only",
            }
            for rank, item in enumerate(candidates, start=1)
        ]
        return {
            "scenario": 1,
            "trigger": trigger,
            "meteorology": {
                "wind_direction_deg": weather["wind_from_deg"],
                "wind_speed_ms": weather["wind_speed_ms"],
                "wind_speed_historical_mean_ms": round(historical_wind_speed_ms, 3),
                "wind_speed_data_source": historical_wind_source,
                "stability": stability,
                "stability_source": weather["stability"].get("source") or "default_D_missing_ERA5",
                "fan_radius_km": radius_km,
                "fan_half_angle_deg": weather["sector_half_angle_deg"],
            },
            "analysis": {
                "enterprises_in_fan": enterprises_in_fan,
                "top1": ranked[0] if ranked else None,
                "top_n": ranked,
                "confidence": confidence,
                "confidence_cap_reason": "annual_emission_inventory_unavailable",
                "score_interpretation": "dimensionless_screening_evidence_not_emission_contribution",
                "top1_top2_margin_pct": round(margin, 1) if margin is not None else None,
            },
            "recommendation": "优先核查上风向候选企业的设施运行状态和排放台账；该清单不构成排放贡献或责任认定。",
        }

    @staticmethod
    def _longest_consecutive_hours(matches: list[dict[str, Any]]) -> int:
        times = sorted(datetime.fromisoformat(item["time"]) for item in matches)
        longest = current = 1
        for previous, current_time in zip(times, times[1:], strict=False):
            if current_time - previous == timedelta(hours=1):
                current += 1
            else:
                current = 1
            longest = max(longest, current)
        return longest

    @staticmethod
    def _failure(reason: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": reason,
            "summary": f"许昌上风向许可证企业分析失败：{reason}",
            "metadata": {
                "schema_version": "v1.0",
                "tool_name": TOOL_NAME,
                "generator": TOOL_NAME,
            },
            "data": None,
        }

"""Build the yesterday Xuchang daily review from Scenario-1 episodes.

The review is a read-only consumer of ``xuchang.station_deviation`` episodes:
it never recomputes alerts, never republishes confirmed/requested events and
never adds township stations to the alert baseline. It loads surrounding
station hourly data (regular + township), computes the deterministic regional
response per episode and writes one evidence package for the report Agent.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

import pyodbc
import structlog
from config.settings import settings

from app.db.repositories.weather_repo import WeatherRepository
from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.xcai_station_sql import xcai_connection_string
from app.scenarios.xuchang_daily_review.episodes import (
    DailyReviewAnalysisState,
    load_episode_anchors,
)
from app.scenarios.xuchang_daily_review.map_frames import build_pollutant_map_frames
from app.scenarios.xuchang_daily_review.report_events import build_report_events
from app.scenarios.xuchang_daily_review.regional_response import (
    _bearing_deg,
    _haversine_km,
    calculate_regional_response,
)
from app.scenarios.xuchang_daily_review.township_hourly import load_township_hourly_rows
from app.scheduled_tasks.models import TaskEvent
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger()
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
DAILY_REVIEW_EVENT_TYPE = "xuchang.station_daily_pollution.review_completed"
TARGET_STATION_CODES = ("1003A", "1005A", "1008A", "1009A", "1011A", "1012A")
STATION_COORDINATES = {
    "3337A": (34.036, 113.852),
    "3338A": (34.0825, 113.8428),
    "3134A": (34.04, 113.85),
    "1008A": (34.0443, 113.8611),
    "1009A": (34.0825, 113.8428),
    "1005A": (34.0339, 113.8172),
    "1003A": (34.036, 113.852),
    "1011A": (34.036, 113.852),
    "1012A": (34.04, 113.85),
}
REGIONAL_COMPARISON_CITIES = {
    "郑州市", "开封市", "平顶山市", "漯河市", "周口市", "商丘市", "驻马店市",
}
HENAN_CITY_NAMES = {
    "郑州市", "开封市", "洛阳市", "平顶山市", "安阳市", "鹤壁市", "新乡市",
    "焦作市", "濮阳市", "许昌市", "漯河市", "三门峡市", "南阳市", "商丘市",
    "信阳市", "周口市", "驻马店市", "济源市",
}
XUCHANG_ERA5_GRID_POINT = (34.0, 113.75)
SCHEMA_VERSION = "xuchang_station_daily_review/v7"
REGIONAL_ANALYSIS_VERSION = "regional_response_with_township_coordinates/v2"
WINDOW_EXTENSION_HOURS = 3


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def build_city_daily_ranking(rows: list[dict[str, Any]], target_date: date) -> dict[str, Any]:
    """Calculate Henan city daily PM ranks while retaining no raw peer rows."""
    normalized = []
    for row in rows:
        city = str(row.get("city") or row.get("area") or "").strip()
        if city not in HENAN_CITY_NAMES:
            continue
        pm25 = _number(row.get("pm25"))
        pm10 = _number(row.get("pm10"))
        if pm25 is None and pm10 is None:
            continue
        normalized.append({
            "city": city, "pm25": pm25, "pm10": pm10,
            "data_source": str(row.get("data_source") or ""),
        })
    # One row per city; duplicate platform rows are resolved by the last row.
    by_city = {row["city"]: row for row in normalized}
    cities = list(by_city.values())

    def rank_for(field: str) -> tuple[float | None, int | None]:
        value = by_city.get("许昌市", {}).get(field)
        if value is None:
            return None, None
        ordered = sorted(
            (row[field] for row in cities if row.get(field) is not None),
            reverse=True,
        )
        return value, ordered.index(value) + 1

    pm25, pm25_rank = rank_for("pm25")
    pm10, pm10_rank = rank_for("pm10")
    result: dict[str, Any] = {
        "target_date": target_date.isoformat(),
        "source": (
            "各城市:dbo.CityDayAQIPublishHistory（城市日发布历史）；"
            "中大平台日数据已停止采集"
        ),
        "ranking_direction": "desc",
        "city_count": len(cities),
        "coverage": {
            "pm25_city_count": sum(row.get("pm25") is not None for row in cities),
            "pm10_city_count": sum(row.get("pm10") is not None for row in cities),
        },
        "xuchang": {
            "city": "许昌市",
            "pm25": pm25,
            "pm25_rank": pm25_rank,
            "pm10": pm10,
            "pm10_rank": pm10_rank,
            "value_source": by_city.get("许昌市", {}).get("data_source"),
        },
        "note": (
            "排名按浓度从高到低，1为浓度最高；各城市日均统一取发布历史日数据；"
            "其他城市日值不进入Agent证据包。"
        ),
    }
    for field, label in (("pm25", "pm25"), ("pm10", "pm10")):
        value = result["xuchang"][label]
        peers = [row[field] for row in cities if row.get(field) is not None and value is not None]
        if value is not None and peers:
            result["xuchang"][f"{label}_median"] = round(sorted(peers)[len(peers) // 2], 3)
    return result


def build_report_summary(
    station_rows: list[dict[str, Any]],
    regional_rows: list[dict[str, Any]],
    episode_analyses: list[dict[str, Any]],
    target_date: date,
) -> dict[str, Any]:
    """Precompute compact, deterministic facts used by the report Agent."""
    station_stats: dict[str, dict[str, Any]] = {}
    for station_id in sorted({str(row.get("station_id")) for row in station_rows if row.get("station_id")}):
        rows = [row for row in station_rows if str(row.get("station_id")) == station_id]
        values = [_number(row.get("pm25")) for row in rows]
        values = [value for value in values if value is not None]
        if not values:
            continue
        station_stats[station_id] = {
            "station_name": next((row.get("name") or station_id for row in rows), station_id),
            "hour_count": len(values),
            "pm25_mean": round(sum(values) / len(values), 3),
            "pm25_max": round(max(values), 3),
            "pm25_min": round(min(values), 3),
        }
    city_stats: dict[str, dict[str, Any]] = {}
    for city in sorted({str(row.get("city")) for row in regional_rows if row.get("city")}):
        values = [_number(row.get("pm25")) for row in regional_rows if str(row.get("city")) == city]
        values = [value for value in values if value is not None]
        if values:
            city_stats[city] = {
                "hour_count": len(values),
                "pm25_mean": round(sum(values) / len(values), 3),
                "pm25_max": round(max(values), 3),
                "pm25_min": round(min(values), 3),
            }
    episode_summaries = []
    seen_episode_ids: set[str] = set()
    for analysis in episode_analyses:
        episode_id = str(analysis.get("episode_id") or "")
        if episode_id in seen_episode_ids:
            continue
        seen_episode_ids.add(episode_id)
        anchor = analysis.get("alert_anchor") or {}
        episode_summaries.append({
            "episode_id": analysis.get("episode_id"),
            "station_id": anchor.get("station_id"),
            "station_name": anchor.get("station_name"),
            "target_pollutant": anchor.get("target_pollutant"),
            "episode_start": anchor.get("episode_start"),
            "episode_end": anchor.get("episode_end"),
            "peak_time": anchor.get("peak_time"),
            "regional_classification": (analysis.get("regional_co_rise") or {}).get("classification"),
            "transport_conclusion": (analysis.get("transport_consistency") or {}).get("conclusion"),
            "calculation_status": analysis.get("calculation_status"),
        })
    return {
        "target_date": target_date.isoformat(),
        "episode_count": len(episode_summaries),
        "episodes": episode_summaries,
        "alert_source_status": "found" if episode_summaries else "not_found",
        "station_pm25_statistics": station_stats,
        "regional_city_pm25_statistics": city_stats,
    }


def build_report_brief(result: dict[str, Any]) -> dict[str, Any]:
    """Provide one bounded, typed reading guide for the report Agent."""
    summary = result["report_summary"]

    def weather_interval(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, Any]:
        times = []
        for row in rows:
            try:
                times.append(datetime.fromisoformat(str(row["time"])).astimezone(TZ_SHANGHAI))
            except (KeyError, TypeError, ValueError):
                continue
        interval: dict[str, Any] = {
            "record_count": len(rows),
            "start_time": min(times).isoformat() if times else None,
            "end_time": max(times).isoformat() if times else None,
        }
        for field in fields:
            values = []
            for row in rows:
                try:
                    value = float(row[field])
                except (KeyError, TypeError, ValueError):
                    continue
                if isfinite(value) and (field == "temperature_2m" or value >= 0):
                    values.append(value)
            interval[field] = ({
                "valid_hours": len(values),
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "mean": round(sum(values) / len(values), 3),
                **({"sum": round(sum(values), 3)} if field == "precipitation" else {}),
            } if values else {"valid_hours": 0})
        return interval

    return {
        "schema_version": "xuchang_station_daily_review_brief/v2",
        "target_date": result["target_date"],
        "alert_source_status": summary["alert_source_status"],
        "episode_count": summary["episode_count"],
        "alert_list": summary["episodes"],
        "station_pm25_statistics": summary["station_pm25_statistics"],
        "regional_city_pm25_statistics": summary["regional_city_pm25_statistics"],
        "meteorology_intervals": {
            "nmc": weather_interval(result.get("meteorology") or [], (
                "temperature_2m", "relative_humidity_2m",
                "wind_speed_10m", "precipitation",
            )),
            "era5": weather_interval(result.get("meteorology_era5") or [], (
                "boundary_layer_height", "cloud_cover",
            )),
        },
        "field_guide": {
            "basic_situation": "report_brief.json:alert_list / episode_count",
            "station_and_city_pm25": "report_brief.json:station_pm25_statistics / regional_city_pm25_statistics",
            "weather_overview": "report_brief.json:meteorology_intervals",
            "merged_alert_events": "event_brief.json:events[] (两个章节共用；alert_intervals 为实际告警段，跨短空档事件的 segments[] 保留各段升幅、风向和上风向乡镇站对比)",
            "episode_windows_and_neighbors": "stage_brief.json:episodes[] (原始 episode 级辅助证据；按 episode_id 匹配)",
            "township_and_regional_response": "regional_responses.json:episodes[]",
            "hourly_weather_if_needed": "meteorology.json:meteorology / meteorology_era5",
            "spatial_and_transport_if_needed": "spatial_responses.json / transport_responses.json:episodes[]",
            "map_render_only": "pollutant_maps.json:maps[]; 由 HTML 组装程序读取，不由 Agent 阅读",
        },
        "limits": "站点和城市概览统计仅为 PM2.5；各污染物告警过程值以 event_brief.json 为准。气象区间为描述性统计，不自动形成污染成因判断。",
    }


def build_source_features_summary(episode_analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """Project Scenario-1 source features into a compact daily summary."""
    records = []
    for analysis in episode_analyses:
        features = analysis.get("source_features") or []
        anchor = analysis.get("alert_anchor") or {}
        for feature in features:
            records.append({
                "episode_id": analysis.get("episode_id"),
                "station_id": anchor.get("station_id"),
                "pollutant": anchor.get("target_pollutant"),
                "classification": feature.get("classification"),
                "status": feature.get("status"),
                "sample_count": feature.get("sample_count"),
                "components": feature.get("components"),
                "flags": feature.get("flags"),
            })
    counts: dict[str, int] = {}
    for record in records:
        classification = record.get("classification")
        if classification:
            counts[str(classification)] = counts.get(str(classification), 0) + 1
    return {
        "record_count": len(records),
        "classification_counts": counts,
        "records": records,
        "note": "源特征复用场景一确定性结果，报告 Agent 只作业务归纳，不重新计算",
    }


def build_stage_brief(report_facts: dict[str, Any]) -> dict[str, Any]:
    """Bounded episode facts for prose; keep the full neighbor list in report_facts."""
    episodes = []
    for item in report_facts.get("episodes") or []:
        target = item.get("target_response") or {}
        response = {
            name: {key: (target.get(name) or {}).get(key) for key in ("mean", "valid_hours", "status")}
            for name in ("before", "during", "after")
        }
        response.update({key: target.get(key) for key in ("during_delta", "during_ratio", "after_delta", "during_classification")})
        township = [station for station in item.get("nearby_station_candidates") or [] if station.get("station_type") == "township"][:3]
        neighbors = [{key: station.get(key) for key in (
            "station_name", "district", "distance_km", "bearing_deg_from_target",
            "before_mean", "during_mean", "after_mean", "during_classification",
        )} for station in township]
        episodes.append({
            "episode_id": item.get("episode_id"),
            "alert_anchor": item.get("alert_anchor"),
            "window_hours": item.get("window_hours"),
            "target_response": response,
            "regional_classification": item.get("regional_classification"),
            "regional_reason": item.get("regional_reason"),
            "temporal_counts": item.get("temporal_counts"),
            "spatial_status": item.get("spatial_status"),
            "transport_conclusion": item.get("transport_conclusion"),
            "nearby_township_examples": neighbors,
            "selection_note": "仅列最近3个乡镇站作对比，方位不代表上风向；完整候选站见 report_facts.json",
        })
    return {"episode_count": len(episodes), "episodes": episodes}


def build_report_facts(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose precomputed episode facts without making the Agent rescan station rows."""
    episodes = []
    for analysis in analyses:
        anchor = analysis.get("alert_anchor") or {}
        target = analysis.get("target_response") or {}
        regional = analysis.get("regional_co_rise") or {}
        temporal = analysis.get("temporal_lead_lag") or {}
        spatial = analysis.get("spatial_gradient") or {}
        transport = analysis.get("transport_consistency") or {}
        target_lat, target_lon = target.get("lat"), target.get("lon")
        nearby = []
        for station in analysis.get("station_response_by_window") or []:
            if station.get("is_target"):
                continue
            lat, lon = station.get("lat"), station.get("lon")
            if None in (target_lat, target_lon, lat, lon):
                continue
            distance = round(_haversine_km(target_lat, target_lon, lat, lon), 2)
            bearing = round(_bearing_deg(target_lat, target_lon, lat, lon), 1)
            nearby.append({
                "station_id": station.get("station_id"),
                "station_name": station.get("station_name"),
                "station_type": station.get("station_type"),
                "district": station.get("district"),
                "distance_km": distance,
                "bearing_deg_from_target": bearing,
                "before_mean": (station.get("before") or {}).get("mean"),
                "during_mean": (station.get("during") or {}).get("mean"),
                "after_mean": (station.get("after") or {}).get("mean"),
                "during_delta": station.get("during_delta"),
                "after_delta": station.get("after_delta"),
                "during_classification": station.get("during_classification"),
                "after_classification": station.get("after_classification"),
            })
        nearby.sort(key=lambda station: (station["distance_km"], str(station["station_id"])))
        # Preserve township coverage across all eight directions, then include
        # the closest stations. This is a selection for review, not a source claim.
        selected: dict[str, dict[str, Any]] = {}
        for sector in range(8):
            match = next((item for item in nearby if item["station_type"] == "township" and int((item["bearing_deg_from_target"] + 22.5) // 45) % 8 == sector), None)
            if match is not None:
                selected[str(match["station_id"])] = match
        for item in [x for x in nearby if x["station_type"] == "township"][:4] + [x for x in nearby if x["station_type"] != "township"][:5]:
            selected[str(item["station_id"])] = item
        episodes.append({
            "episode_id": analysis.get("episode_id"),
            "alert_anchor": anchor,
            "window_hours": (analysis.get("window_policy") or {}).get("windows", {}),
            "target_response": {key: target.get(key) for key in ("before", "during", "after", "during_delta", "during_ratio", "after_delta", "after_ratio", "during_classification", "after_classification")},
            "regional_classification": regional.get("classification"),
            "regional_reason": regional.get("reason"),
            "temporal_counts": {key: temporal.get(key) for key in ("lead_count", "synchronous_count", "lag_count", "detected_rise_count", "median_lead_hours_to_target")},
            "spatial_status": spatial.get("spatial_status"),
            "transport_conclusion": transport.get("conclusion"),
            "transport_evidence_limits": transport.get("evidence_limits"),
            "nearby_station_candidates": sorted(selected.values(), key=lambda station: (station["distance_km"], str(station["station_id"]))),
            "neighbor_selection_note": "乡镇站每个方位扇区最近1站、总体最近4站，另取最近5个常规站；仅作阅读索引，不代表上风向或污染来源",
        })
    return {"episode_count": len(episodes), "episodes": episodes}


class XuchangStationDailyPollutionFetcher(DataFetcher):
    """Consume Scenario-1 episodes and build yesterday's review evidence once."""

    def __init__(
        self,
        *,
        now_factory: Callable[[], datetime] = lambda: datetime.now(TZ_SHANGHAI),
        township_loader: Callable[[datetime, datetime], dict[str, Any]] = load_township_hourly_rows,
    ) -> None:
        super().__init__(
            name="xuchang_station_daily_pollution_fetcher",
            description="许昌昨日污染回顾：消费场景一episode并计算乡镇站区域响应与传输线索",
            schedule="5 2 * * *",
            version="4.0.0",
        )
        self.now_factory = now_factory
        self.township_loader = township_loader

    def load_rows(
        self, start: datetime, end: datetime, station_codes: Iterable[str]
    ) -> list[dict[str, Any]]:
        codes = sorted({str(code) for code in station_codes if code})
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            placeholders = ", ".join("?" for _ in codes)
            cursor.execute(
                f"""
                SELECT station_code, station_name, pm25, pm10, o3, no2, so2, co, time_point
                FROM dbo.dat_zhongda_station_hour
                WHERE time_point >= ? AND time_point < ?
                  AND area LIKE N'%许昌%'
                  AND station_code IN ({placeholders})
                ORDER BY station_code, time_point
                """,
                [start, end, *codes],
            )
            return [
                {
                    "station_id": row[0], "name": row[1], "pm25": row[2],
                    "pm10": row[3], "o3": row[4], "no2": row[5], "so2": row[6],
                    "co": row[7], "data_time": row[8],
                    "lat": STATION_COORDINATES.get(str(row[0]), (None, None))[0],
                    "lon": STATION_COORDINATES.get(str(row[0]), (None, None))[1],
                    "station_type": "regular", "data_source": "zhongda_raw_hour",
                }
                for row in cursor.fetchall()
            ]
        finally:
            connection.close()

    def load_regional_hourly_rows(self, target_date: date) -> list[dict[str, Any]]:
        start = datetime.combine(target_date, time.min)
        end = start + timedelta(days=1)
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            city_names = sorted(REGIONAL_COMPARISON_CITIES)
            placeholders = ", ".join("?" for _ in city_names)
            cursor.execute(
                f"""
                SELECT Area, CityCode, TimePoint, PM2_5, PM10, O3, NO2, SO2, CO
                FROM dbo.CityAQIPublishHistory
                WHERE TimePoint >= ? AND TimePoint < ?
                  AND Area IN ({placeholders})
                ORDER BY Area, TimePoint
                """,
                [start, end, *city_names],
            )
            return [
                {
                    "city": row[0], "city_code": row[1], "data_time": row[2],
                    "pm25": _number(row[3]), "pm10": _number(row[4]), "o3": _number(row[5]),
                    "no2": _number(row[6]), "so2": _number(row[7]), "co": _number(row[8]),
                    "data_source": "published_city_hour",
                }
                for row in cursor.fetchall()
            ]
        finally:
            connection.close()

    def load_city_daily_rows(self, target_date: date) -> list[dict[str, Any]]:
        """河南各城市日均统一取城市日发布历史（中大平台日数据已停止采集）。"""
        city_names = sorted(HENAN_CITY_NAMES)
        day_start = datetime.combine(target_date, time.min)
        day_end = day_start + timedelta(days=1)
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            placeholders = ", ".join("?" for _ in city_names)
            cursor.execute(
                f"""
                SELECT Area, CityCode, TimePoint, PM2_5_24h, PM10_24h
                FROM dbo.CityDayAQIPublishHistory
                WHERE TimePoint >= ? AND TimePoint < ?
                  AND Area IN ({placeholders})
                ORDER BY Area, TimePoint
                """,
                [day_start, day_end, *city_names],
            )
            return [
                {
                    "city": str(row[0] or "").strip(),
                    "city_code": row[1],
                    "data_date": row[2],
                    "pm25": _number(row[3]),
                    "pm10": _number(row[4]),
                    "data_source": "city_day_publish_history",
                }
                for row in cursor.fetchall()
            ]
        finally:
            connection.close()

    def _episode_anchors(self, target_date: date) -> dict[str, Any]:
        registry = get_data_registry()
        return load_episode_anchors(
            registry / "xuchang_station_deviation_alerts" / "episode_state.json",
            target_date,
            evidence_root=registry / "xuchang_station_deviation_alerts",
        )

    def _query_window(
        self, anchors: list[dict[str, Any]], target_date: date
    ) -> tuple[datetime, datetime]:
        day_start = datetime.combine(target_date, time.min)
        if not anchors:
            return day_start, day_start + timedelta(days=1)
        starts = [datetime.fromisoformat(anchor["episode_start"]) for anchor in anchors]
        ends = [datetime.fromisoformat(anchor["episode_end"]) for anchor in anchors]
        window_start = min(starts).replace(tzinfo=None) - timedelta(hours=WINDOW_EXTENSION_HOURS)
        window_end = max(ends).replace(tzinfo=None) + timedelta(hours=WINDOW_EXTENSION_HOURS + 1)
        return window_start, window_end

    async def _build_meteorology_block(
        self, result: dict[str, Any], target_date: date
    ) -> None:
        weather_rows = await WeatherRepository().get_observed_data(
            "ZzMTA", datetime.combine(target_date, time.min), datetime.combine(target_date, time.max)
        )
        result["meteorology"] = [
            {
                "time": item.time.isoformat(), "temperature_2m": item.temperature_2m,
                "relative_humidity_2m": item.relative_humidity_2m,
                "wind_speed_10m": item.wind_speed_10m,
                "wind_direction_10m": item.wind_direction_10m,
                "precipitation": item.precipitation, "data_source": "NMC",
            }
            for item in weather_rows
        ]
        era5_rows: list[dict[str, Any]] = []
        try:
            era5_data = await WeatherRepository().get_weather_data(
                XUCHANG_ERA5_GRID_POINT[0],
                XUCHANG_ERA5_GRID_POINT[1],
                datetime.combine(target_date, time.min, tzinfo=TZ_SHANGHAI),
                datetime.combine(target_date, time.max, tzinfo=TZ_SHANGHAI),
            )
            for item in era5_data:
                timestamp = item.time
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=TZ_SHANGHAI)
                timestamp = timestamp.astimezone(TZ_SHANGHAI)
                era5_rows.append({
                    "time": timestamp.isoformat(),
                    "boundary_layer_height": item.boundary_layer_height,
                    "cloud_cover": item.cloud_cover,
                    "data_source": "ERA5",
                })
        except Exception as exc:  # ERA5 is supplemental; NMC remains usable.
            result["meteorology_era5_error"] = str(exc)
        result["meteorology_era5"] = era5_rows
        result["meteorology_coverage"] = {
            "nmc_hours": len(result["meteorology"]),
            "era5_hours": len(era5_rows),
            "era5_grid_point": {
                "lat": XUCHANG_ERA5_GRID_POINT[0],
                "lon": XUCHANG_ERA5_GRID_POINT[1],
            },
            "variables": {
                "nmc": [
                    "temperature_2m", "relative_humidity_2m", "wind_speed_10m",
                    "wind_direction_10m", "precipitation",
                ],
                "era5": ["boundary_layer_height", "cloud_cover"],
            },
            "note": "NMC提供地面常规气象，ERA5补充边界层高度和云量；不在数据脚本中判定气象机制",
        }

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory()
        target_date = now.astimezone(TZ_SHANGHAI).date() - timedelta(days=1)
        anchors_result = self._episode_anchors(target_date)
        anchors = anchors_result["episodes"]
        query_start, query_end = self._query_window(anchors, target_date)
        station_codes: set[str] = set(TARGET_STATION_CODES)
        station_codes.update(str(anchor["station_id"]) for anchor in anchors)
        station_rows = self.load_rows(query_start, query_end, station_codes)
        regional_rows = self.load_regional_hourly_rows(target_date)
        city_daily_rows = self.load_city_daily_rows(target_date)
        city_daily_ranking = build_city_daily_ranking(city_daily_rows, target_date)
        township_result = await asyncio.to_thread(self.township_loader, query_start, query_end)

        registry = get_data_registry()
        analysis_state = DailyReviewAnalysisState(
            registry / "xuchang_station_daily_reviews" / "analysis_state.json"
        )
        episode_analyses = []
        for anchor in anchors:
            analysis_version = f"{anchor['evidence_version']}:{REGIONAL_ANALYSIS_VERSION}"
            base_analysis_id = (
                f"xuchang-daily-review-{target_date:%Y%m%d}-{anchor['episode_id']}"
            )
            resolution = analysis_state.resolve(
                anchor["episode_id"], analysis_version, base_analysis_id
            )
            if resolution["analysis_status"] == "duplicate" and resolution.get("result"):
                reused = dict(resolution.get("result") or {})
                reused["analysis_status"] = "duplicate"
                reused["calculation_status"] = "skipped_duplicate"
                episode_analyses.append(reused)
                continue
            analysis = calculate_regional_response(
                {
                    **anchor,
                    "analysis_id": resolution["analysis_id"],
                    "target_date": target_date.isoformat(),
                },
                regular_rows=station_rows,
                township_rows=township_result.get("rows") or [],
            )
            analysis["analysis_status"] = (
                "retry" if resolution.get("pending") else resolution["analysis_status"]
            )
            analysis["parent_analysis_id"] = resolution["parent_analysis_id"]
            analysis["version_number"] = resolution["version_number"]
            analysis_state.complete(
                anchor["episode_id"], analysis_version,
                resolution["analysis_id"], analysis,
            )
            episode_analyses.append(analysis)

        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "target_date": target_date.isoformat(),
            "review_scope": {
                "mode": "always",
                "description": "无论昨日是否存在城市超标或场景一告警，均执行昨日数据抓取和确定性分析；告警仅作为事件锚点复用",
            },
            "alert_source": {
                "status": anchors_result["status"],
                "episode_source": anchors_result.get("episode_source"),
                "accepted_alert_event_types": anchors_result["accepted_alert_event_types"],
                "episode_state_path": anchors_result["state_path"],
                "note": "昨日回顾只消费场景一告警episode，不重新判定告警",
            },
            "episodes": episode_analyses,
            "township_data": {
                "status": township_result.get("status"),
                "reason": township_result.get("reason"),
                "source": township_result.get("source"),
                "query_window": township_result.get("query_window"),
                "station_count": township_result.get("station_count"),
                "coordinate_count": township_result.get("coordinate_count", 0),
                "coordinate_source": "xuchang_station_catalog:township_coordinates.tsv",
                "note": "乡镇小时视图0时为数据源系统性缺测，窗口样本统计自动跳过缺失小时，不影响样本约束与计算结论",
            },
            # Raw hourly rows are intentionally kept in the fetcher's local
            # calculation scope only. The report Agent receives deterministic
            # summaries, not a large row-level payload.
            "input_data_summary": {
                "regular_station_row_count": len(station_rows),
                "township_station_row_count": len(township_result.get("rows") or []),
                "regional_city_row_count": len(regional_rows),
                "regular_station_count": len({str(row.get("station_id")) for row in station_rows if row.get("station_id")}),
                "township_station_count": township_result.get("station_count") or 0,
                "township_coordinate_count": township_result.get("coordinate_count") or 0,
                "regional_city_count": len({str(row.get("city")) for row in regional_rows if row.get("city")}),
                "note": "原始小时行仅用于数据脚本确定性计算，不写入报告 Agent 证据包",
            },
            "report_summary": build_report_summary(
                station_rows, regional_rows, episode_analyses, target_date
            ),
            "source_features_summary": build_source_features_summary(episode_analyses),
            "city_daily_ranking": city_daily_ranking,
            "source_provenance": {
                "alert_episodes": "场景一站点快速污染抬升告警episode（xuchang_station_deviation）",
                "station_hourly": "中大源原始站点小时数据（dbo.dat_zhongda_station_hour）",
                "township_hourly": "大气环境监测数据接口中台（v_t_h_src 乡镇小时-原始）",
                "regional_city_hourly": "城市发布小时数据（dbo.CityAQIPublishHistory）",
                "city_daily": "城市日发布历史（dbo.CityDayAQIPublishHistory，各城市统一来源；中大平台日数据已停止采集）",
                "meteorology": "NMC许昌观测站（station_id=ZzMTA）",
                "township_coordinates": "backend/app/tools/xuchang/station_catalog/township_coordinates.tsv",
            },
        }
        await self._build_meteorology_block(result, target_date)

        # The same merged event list drives both the basic-situation count and
        # the chapter-two narrative. Scenario-1 episodes remain source records.
        report_events = build_report_events(
            episode_analyses, station_rows, township_result.get("rows") or [],
            result.get("meteorology") or [],
        )
        result["report_events"] = report_events
        result["report_summary"]["raw_episode_count"] = result["report_summary"]["episode_count"]
        result["report_summary"]["episode_count"] = report_events["event_count"]
        result["report_summary"]["episodes"] = [
            {key: event.get(key) for key in (
                "event_id", "station_id", "station_name", "pollutant", "start_time",
                "end_time", "alert_intervals", "gap_hour_count", "peak_rise_absolute",
                "peak_rise_percent", "source_episode_ids",
            )} for event in report_events["events"]
        ]

        agent_episodes = [
            {key: value for key, value in analysis.items() if key != "source_evidence_package_path"}
            for analysis in result["episodes"]
        ]
        review_dir = registry / "xuchang_station_daily_reviews" / f"{target_date:%Y%m%d}"
        review_dir.mkdir(parents=True, exist_ok=True)
        summary_payload = {
            "schema_version": SCHEMA_VERSION,
            "target_date": result["target_date"],
            "review_scope": result["review_scope"],
            "alert_source": result["alert_source"],
            "township_data": result["township_data"],
            "input_data_summary": result["input_data_summary"],
            "report_summary": result["report_summary"],
            "note": (
                "report_summary.episodes 即当日告警结果清单；原始告警证据包与告警图表目录"
                "为内部过程数据，报告生成无需读取。"
            ),
        }
        meteorology_payload = {
            "target_date": result["target_date"],
            "meteorology": result.get("meteorology", []),
            "meteorology_era5": result.get("meteorology_era5", []),
            "meteorology_coverage": result.get("meteorology_coverage", {}),
            "meteorology_era5_error": result.get("meteorology_era5_error"),
        }
        episode_metadata = []
        station_responses = []
        regional_responses = []
        temporal_responses = []
        spatial_responses = []
        transport_responses = []
        episode_source_features = []
        for analysis in agent_episodes:
            episode_id = analysis["episode_id"]
            episode_metadata.append({
                key: value for key, value in analysis.items()
                if key not in {
                    "station_response_by_window", "regional_co_rise",
                    "township_district_summary", "temporal_lead_lag",
                    "spatial_gradient", "transport_consistency",
                    "target_response", "source_features", "spatial_map",
                }
            })
            station_responses.append({
                "episode_id": episode_id,
                "target_response": analysis.get("target_response"),
                "stations": analysis.get("station_response_by_window") or [],
            })
            regional_responses.append({
                "episode_id": episode_id,
                "regional_co_rise": analysis.get("regional_co_rise"),
                "township_district_summary": analysis.get("township_district_summary") or [],
            })
            temporal_responses.append({
                "episode_id": episode_id,
                "temporal_lead_lag": analysis.get("temporal_lead_lag"),
            })
            spatial_responses.append({
                "episode_id": episode_id,
                "spatial_gradient": analysis.get("spatial_gradient"),
                "spatial_map": analysis.get("spatial_map"),
            })
            transport_responses.append({
                "episode_id": episode_id,
                "transport_consistency": analysis.get("transport_consistency"),
            })
            episode_source_features.append({
                "episode_id": episode_id,
                "source_features": analysis.get("source_features") or [],
            })
        report_facts = {"target_date": result["target_date"], **build_report_facts(agent_episodes)}
        component_payloads = {
            "report_brief": build_report_brief(result),
            "event_brief": {"target_date": result["target_date"], **report_events},
            "stage_brief": {"target_date": result["target_date"], **build_stage_brief(report_facts)},
            "summary": summary_payload,
            "episodes": {
                "target_date": result["target_date"],
                "episodes": episode_metadata,
            },
            "station_responses": {"target_date": result["target_date"], "episodes": station_responses},
            "regional_responses": {"target_date": result["target_date"], "episodes": regional_responses},
            "temporal_responses": {"target_date": result["target_date"], "episodes": temporal_responses},
            "spatial_responses": {"target_date": result["target_date"], "episodes": spatial_responses},
            "transport_responses": {"target_date": result["target_date"], "episodes": transport_responses},
            "report_facts": report_facts,
            "pollutant_maps": {"target_date": result["target_date"], **build_pollutant_map_frames(
                report_events["events"], station_rows, township_result.get("rows") or [], result["target_date"]
            )},
            "meteorology": meteorology_payload,
            "source_features": {
                "target_date": result["target_date"],
                "source_features_summary": result["source_features_summary"],
                "episodes": episode_source_features,
            },
            "city_daily_rankings": {
                "target_date": result["target_date"],
                "city_daily_ranking": result["city_daily_ranking"],
            },
            "provenance": {
                "target_date": result["target_date"],
                "source_provenance": result["source_provenance"],
            },
        }
        component_paths: dict[str, str] = {}
        for name, payload in component_payloads.items():
            component_path = review_dir / f"{name}.json"
            component_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=None if name == "stage_brief" else 2, default=str), encoding="utf-8"
            )
            component_paths[name] = format_agent_path(component_path)

        # The Python sandbox has no .env or inherited environment. Stage only
        # the browser-facing map key for the final renderer.
        render_config_path = review_dir / "render_config.json"
        render_config_path.write_text(
            json.dumps({"map_provider": "amap", "public_key": settings.amap_public_key or ""}, ensure_ascii=False),
            encoding="utf-8",
        )

        # Keep a small manifest at the event-facing path. It contains compact
        # summary fields for routing and points the Agent to typed evidence.
        review_path = review_dir / "manifest.json"
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "target_date": result["target_date"],
            "review_scope": result["review_scope"],
            "alert_source": result["alert_source"],
            "episode_count": report_events["event_count"],
            "raw_episode_count": len(agent_episodes),
            "evidence_files": component_paths,
            "render_config_path": format_agent_path(render_config_path),
        }
        review_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        analyzed = episode_analyses
        review_payload = {
            "city": "许昌市",
            "target_date": result["target_date"],
            "alert_source_status": anchors_result["status"],
            "episode_count": report_events["event_count"],
            "raw_episode_count": len(analyzed),
            "alert_event_anchors": [
                f"{event['station_id']}({event['pollutant']},"
                f"{event['start_time'][:16]}~{event['end_time'][:16]})"
                for event in report_events["events"]
            ],
            "evidence_package_path": format_agent_path(review_path),
            "template_path": str(registry / "uploads" / "2d1aabdc-ca0a-4bcd-9166-07d38a5e595b.docx"),
        }
        review_event = TaskEvent(
            event_id=f"xuchang-station-daily-review-{target_date:%Y%m%d}",
            event_type=DAILY_REVIEW_EVENT_TYPE,
            occurred_at=datetime.combine(
                target_date + timedelta(days=1), time.min, tzinfo=TZ_SHANGHAI
            ).isoformat(),
            attributes={"city": "许昌市", "target_date": result["target_date"]},
            payload=review_payload,
        )
        from app.scheduled_tasks import get_scheduled_task_service

        task_service = get_scheduled_task_service()
        await task_service.publish_event(review_event)
        logger.info(
            "xuchang_station_daily_pollution_completed",
            target_date=result["target_date"],
            alert_source_status=anchors_result["status"],
            merged_event_count=report_events["event_count"],
            raw_episode_count=len(analyzed),
        )
        return result

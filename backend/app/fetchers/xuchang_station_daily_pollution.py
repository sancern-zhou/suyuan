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
from typing import Any
from zoneinfo import ZoneInfo

import pyodbc
import structlog

from app.db.repositories.weather_repo import WeatherRepository
from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.xcai_station_sql import xcai_connection_string
from app.scenarios.xuchang_daily_review.episodes import (
    DailyReviewAnalysisState,
    load_episode_anchors,
)
from app.scenarios.xuchang_daily_review.regional_response import calculate_regional_response
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
SCHEMA_VERSION = "xuchang_station_daily_review/v5"
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
            "许昌市:中大源dbo.dat_zhongda_city_day（审核回算，缺失当日回退"
            "dbo.CityDayAQIPublishHistory并在value_source标注）；"
            "其他城市:dbo.CityDayAQIPublishHistory（城市日发布历史）"
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
            "排名按浓度从高到低，1为浓度最高；许昌日均取中大审核值，其他城市取发布历史日数据；"
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
        """许昌日均取中大审核回算值，其他河南城市取城市日发布历史。"""
        peer_cities = sorted(HENAN_CITY_NAMES - {"许昌市"})
        day_start = datetime.combine(target_date, time.min)
        day_end = day_start + timedelta(days=1)
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT area, city_code, data_date, pm25, pm10
                FROM dbo.dat_zhongda_city_day
                WHERE data_date = ? AND area = ?
                ORDER BY data_date
                """,
                [target_date, "许昌市"],
            )
            rows = [
                {
                    "city": str(row[0] or "").strip(),
                    "city_code": row[1],
                    "data_date": row[2],
                    "pm25": _number(row[3]),
                    "pm10": _number(row[4]),
                    "data_source": "zhongda_city_day",
                }
                for row in cursor.fetchall()
            ]
            xuchang_row = next((row for row in rows if row["pm25"] is not None or row["pm10"] is not None), None)
            if xuchang_row is None:
                cursor.execute(
                    """
                    SELECT Area, CityCode, TimePoint, PM2_5_24h, PM10_24h
                    FROM dbo.CityDayAQIPublishHistory
                    WHERE TimePoint >= ? AND TimePoint < ? AND Area = ?
                    ORDER BY Area, TimePoint
                    """,
                    [day_start, day_end, "许昌市"],
                )
                rows = [
                    row for row in rows
                    if not (row["city"] == "许昌市" and row["data_source"] == "zhongda_city_day")
                ] + [
                    {
                        "city": str(row[0] or "").strip(),
                        "city_code": row[1],
                        "data_date": row[2],
                        "pm25": _number(row[3]),
                        "pm10": _number(row[4]),
                        "data_source": "city_day_publish_history_xuchang_fallback",
                    }
                    for row in cursor.fetchall()
                ]
            placeholders = ", ".join("?" for _ in peer_cities)
            cursor.execute(
                f"""
                SELECT Area, CityCode, TimePoint, PM2_5_24h, PM10_24h
                FROM dbo.CityDayAQIPublishHistory
                WHERE TimePoint >= ? AND TimePoint < ?
                  AND Area IN ({placeholders})
                ORDER BY Area, TimePoint
                """,
                [day_start, day_end, *peer_cities],
            )
            rows.extend(
                {
                    "city": str(row[0] or "").strip(),
                    "city_code": row[1],
                    "data_date": row[2],
                    "pm25": _number(row[3]),
                    "pm10": _number(row[4]),
                    "data_source": "city_day_publish_history",
                }
                for row in cursor.fetchall()
            )
            return rows
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
            base_analysis_id = (
                f"xuchang-daily-review-{target_date:%Y%m%d}-{anchor['episode_id']}"
            )
            resolution = analysis_state.resolve(
                anchor["episode_id"], anchor["evidence_version"], base_analysis_id
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
                anchor["episode_id"], anchor["evidence_version"],
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
                "city_daily": "许昌市日均取中大源审核回算（dbo.dat_zhongda_city_day），其他城市取城市日发布历史（dbo.CityDayAQIPublishHistory）",
                "meteorology": "NMC许昌观测站（station_id=ZzMTA）",
            },
        }
        await self._build_meteorology_block(result, target_date)

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
        component_payloads = {
            "summary": summary_payload,
            "episodes": {
                "target_date": result["target_date"],
                "episodes": agent_episodes,
            },
            "meteorology": meteorology_payload,
            "source_features": {
                "target_date": result["target_date"],
                "source_features_summary": result["source_features_summary"],
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
                json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            component_paths[name] = format_agent_path(component_path)

        # Keep a small manifest at the event-facing path. It contains compact
        # summary fields for routing and points the Agent to typed evidence.
        review_path = review_dir / "manifest.json"
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "target_date": result["target_date"],
            "review_scope": result["review_scope"],
            "alert_source": result["alert_source"],
            "report_summary": result["report_summary"],
            "episodes": agent_episodes,
            "city_daily_ranking": result.get("city_daily_ranking", {}),
            "evidence_files": component_paths,
        }
        review_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        analyzed = episode_analyses
        review_payload = {
            "city": "许昌市",
            "target_date": result["target_date"],
            "alert_source_status": anchors_result["status"],
            "episode_count": len(analyzed),
            "alert_episode_anchors": [
                f"{anchor['station_id']}({anchor['target_pollutant']},"
                f"{anchor['episode_start'][:16]}~{anchor['episode_end'][:16]})"
                for anchor in anchors
            ],
            "evidence_package_path": format_agent_path(review_path),
            "template_path": "/home/xckj/suyuan/backend/backend_data_registry/uploads/401ecbb4-c402-4f55-b37c-331e7a88b49d.docx",
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
            episode_count=len(analyzed),
        )
        return result

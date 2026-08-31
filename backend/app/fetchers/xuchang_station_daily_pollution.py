"""Build deterministic yesterday-hour pollution review evidence for Xuchang."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
import json
import base64
import inspect
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import pyodbc
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.xcai_station_sql import xcai_connection_string
from app.scenarios.xuchang_transport_escalation import XuchangTransportEscalationService
from app.scenarios.xuchang_station_deviation.source_features import calculate_pollutant_source_features
from app.db.repositories.weather_repo import WeatherRepository
from app.scheduled_tasks.models import TaskEvent
from app.utils.path_config import format_agent_path, get_data_registry, get_images_dir

logger = structlog.get_logger()
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
CONFIRMED_EVENT_TYPE = "xuchang.station_daily_pollution.confirmed"
DAILY_REVIEW_EVENT_TYPE = "xuchang.station_daily_pollution.review_completed"
REQUESTED_EVENT_TYPE = "xuchang.station_daily_source_analysis.requested"
PM25_DAILY_LIMIT = 75.0
O3_8H_DAILY_LIMIT = 160.0
HOURLY_POLLUTANTS = {
    "PM2.5": ("pm25", 10.0),
    "PM10": ("pm10", 10.0),
    "SO2": ("so2", 5.0),
    "NO2": ("no2", 10.0),
    "CO": ("co", 0.2),
    "O3": ("o3", 30.0),
}
HOURLY_RELATIVE_THRESHOLD = 0.5
ALERT_POLLUTANTS = {"PM2.5"}
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


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _hour(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ_SHANGHAI)
    return value.astimezone(TZ_SHANGHAI).replace(minute=0, second=0, microsecond=0)


def _hourly_evidence(rows: list[dict[str, Any]], station_id: str) -> dict[str, Any]:
    """Apply Scenario 1's deterministic leave-one-out rule to yesterday's hours."""
    grouped: dict[datetime, dict[str, dict[str, Any]]] = {}
    for row in rows:
        timestamp = _hour(row.get("data_time"))
        row_station = str(row.get("station_id") or "")
        if timestamp is None or not row_station:
            continue
        grouped.setdefault(timestamp, {})[row_station] = row

    alerts: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    station_rows = [row for row in rows if str(row.get("station_id") or "") == station_id]
    target_series: dict[str, dict[datetime, float]] = {}
    for pollutant, (column, absolute_limit) in HOURLY_POLLUTANTS.items():
        target_series[pollutant] = {
            timestamp: value
            for row in station_rows
            if (timestamp := _hour(row.get("data_time"))) is not None
            and (value := _number(row.get(column))) is not None
        }
        if pollutant not in ALERT_POLLUTANTS:
            continue
        for timestamp, hour_rows in sorted(grouped.items()):
            values = [
                (sid, _number(row.get(column)))
                for sid, row in hour_rows.items()
                if _number(row.get(column)) is not None
            ]
            target = next((value for sid, value in values if sid == station_id), None)
            peers = [value for sid, value in values if sid != station_id]
            baseline = median(peers) if peers else None
            check = {
                "time": timestamp.isoformat(),
                "pollutant": pollutant,
                "station_count": len(values),
                "status": "checked" if baseline is not None else "insufficient_peer_data",
            }
            checks.append(check)
            if target is None or baseline is None or baseline <= 0:
                continue
            absolute_delta = target - baseline
            relative_delta = absolute_delta / baseline
            if relative_delta <= HOURLY_RELATIVE_THRESHOLD or absolute_delta <= absolute_limit:
                continue
            alerts.append({
                "time": timestamp.isoformat(),
                "station_id": station_id,
                "target_pollutant": pollutant,
                "station_value": round(target, 3),
                "peer_baseline": round(baseline, 3),
                "absolute_delta": round(absolute_delta, 3),
                "deviation_ratio": round(relative_delta, 3),
                "deviation_percent": round(relative_delta * 100, 1),
                "peer_station_count": len(peers),
                "rule": "relative_deviation > 0.5 AND absolute_delta > pollutant_absolute_threshold",
            })

    # At each target-station hour, record whether other pollutants rose too.
    synchronous: list[dict[str, Any]] = []
    for pollutant, series in target_series.items():
        for timestamp, value in sorted(series.items()):
            previous = series.get(timestamp - timedelta(hours=1))
            if previous is None:
                continue
            synchronous.append({
                "time": timestamp.isoformat(),
                "pollutant": pollutant,
                "absolute_change": round(value - previous, 3),
                "increased": value > previous,
            })
    changes_by_time: dict[datetime, dict[str, dict[str, Any]]] = {}
    for change in synchronous:
        changes_by_time.setdefault(datetime.fromisoformat(change["time"]), {})[
            change["pollutant"]
        ] = change
    classifications = []
    for alert in alerts:
        alert_time = datetime.fromisoformat(alert["time"])
        target = alert["target_pollutant"]
        observed: dict[str, str] = {}
        for pollutant in HOURLY_POLLUTANTS:
            if pollutant == target:
                continue
            changes = [
                changes_by_time.get(alert_time + timedelta(hours=offset), {}).get(pollutant)
                for offset in (-1, 0, 1)
            ]
            changes = [item for item in changes if item is not None]
            if changes:
                observed[pollutant] = "increased" if any(item["increased"] for item in changes) else "not_increased"
        if not observed:
            classification = "indeterminate"
        elif any(value == "increased" for value in observed.values()):
            classification = "multi_pollutant_sync"
        else:
            classification = "single_pollutant_change"
        item = {
            "time": alert["time"],
            "target_pollutant": target,
            "classification": classification,
            "comparison_window_hours": 1,
            "synchronized_pollutants": sorted(
                pollutant for pollutant, value in observed.items() if value == "increased"
            ),
            "non_synchronized_pollutants": sorted(
                pollutant for pollutant, value in observed.items() if value == "not_increased"
            ),
            "available_comparison_pollutants": sorted(observed),
            "rule": "any_other_pollutant_increases_within_previous_current_next_hour",
        }
        alert["pollutant_change_classification"] = item
        classifications.append(item)
    return {
        "alerts": alerts,
        "checks": checks,
        "synchronous_changes": synchronous,
        "change_classifications": classifications,
    }


def evaluate_station_daily_pollution(
    rows: Iterable[dict[str, Any]], *, target_date: date
) -> dict[str, Any]:
    """Evaluate yesterday's station-hour anomalies; daily values are context only."""
    rows = list(rows)
    rows_by_station: dict[str, dict[str, Any]] = {}
    for row in rows:
        data_time = row.get("data_time")
        if not isinstance(data_time, datetime) or data_time.date() != target_date:
            continue
        if row.get("data_source", "day") == "day" and row.get("station_id"):
            rows_by_station[str(row["station_id"])] = row

    evaluations = []
    events = []
    hourly_rows_for_date = [
        row for row in rows
        if row.get("data_source") == "hour"
        and _hour(row.get("data_time")) is not None
        and _hour(row.get("data_time")).date() == target_date
    ]
    hourly_evidence_by_station = {
        station_id: _hourly_evidence(hourly_rows_for_date, station_id)
        for station_id in {
            str(row.get("station_id")) for row in hourly_rows_for_date if row.get("station_id")
        }
    }
    for station_id, row in sorted(rows_by_station.items()):
        pm25_daily = _number(row.get("pm25"))
        o3_mda8 = _number(row.get("o3_8h"))
        evaluation = {
            "station_id": station_id,
            "station_name": row.get("name") or station_id,
            "lat": _number(row.get("lat")),
            "lon": _number(row.get("lon")),
            "target_date": target_date.isoformat(),
            "pm25": {
                "status": "confirmed" if pm25_daily is not None else "missing_daily_value",
                "daily_value": pm25_daily,
                "limit": PM25_DAILY_LIMIT,
                "exceeded": pm25_daily is not None and pm25_daily > PM25_DAILY_LIMIT,
            },
            "o3_8h": {
                "status": "confirmed" if o3_mda8 is not None else "missing_daily_value",
                "daily_value": o3_mda8,
                "limit": O3_8H_DAILY_LIMIT,
                "exceeded": o3_mda8 is not None and o3_mda8 > O3_8H_DAILY_LIMIT,
            },
        }
        evaluations.append(evaluation)
    # Hourly station anomalies are the sole trigger. Daily values above are
    # retained as context when available, but never decide whether an event
    # is created.
    daily_by_station = {item["station_id"]: item for item in evaluations}
    for station_id, hourly_evidence in hourly_evidence_by_station.items():
        evaluation = daily_by_station.get(station_id, {})
        lat = _number(next((row.get("lat") for row in hourly_rows_for_date
                            if str(row.get("station_id")) == station_id), None))
        lon = _number(next((row.get("lon") for row in hourly_rows_for_date
                            if str(row.get("station_id")) == station_id), None))
        station_name = (evaluation.get("station_name") or next(
            (row.get("name") for row in hourly_rows_for_date
             if str(row.get("station_id")) == station_id), station_id
        ))
        for alert in hourly_evidence["alerts"]:
            pollutant = alert["target_pollutant"]
            observed_indicator = {
                "PM2.5": "PM2.5",
                "PM10": "PM10",
                "SO2": "SO2",
                "NO2": "NO2",
                "CO": "CO",
                "O3": "O3",
            }[pollutant]
            if lat is None or lon is None:
                continue
            event_id = (
                f"xuchang-station-hourly-pollution-{target_date:%Y%m%d}-"
                f"{station_id}-{pollutant.lower().replace('.', '')}-"
                f"{alert['time'].replace(':', '').replace('+', '')}"
            )
            events.append({
                "event_id": event_id,
                "event_type": CONFIRMED_EVENT_TYPE,
                "occurred_at": alert["time"],
                "status": "confirmed",
                "city": "许昌市",
                "station_id": station_id,
                "station_name": station_name,
                "lat": lat,
                "lon": lon,
                "target_date": target_date.isoformat(),
                "target_pollutant": pollutant,
                "observed_indicator": observed_indicator,
                "daily_value": (evaluation.get("pm25", {}).get("daily_value")
                                if pollutant == "PM2.5" else evaluation.get("o3_8h", {}).get("daily_value")),
                "limit": None,
                "hourly_value": alert["station_value"],
                "peer_baseline": alert["peer_baseline"],
                "absolute_delta": alert["absolute_delta"],
                "deviation_ratio": alert["deviation_ratio"],
                "data_rate": round(min(len([
                    row for row in hourly_rows_for_date
                    if str(row.get("station_id")) == station_id
                ]) / 24, 1.0), 3),
                "source_granularity": "station_hour",
                "source_table": "dbo.dat_zhongda_station_hour",
                "trigger": "confirmed_station_hourly_high_value",
            })
    evaluation_by_station = {item["station_id"]: item for item in evaluations}
    for event in events:
        metric_key = "pm25" if event["target_pollutant"] == "PM2.5" else "o3_8h"
        event["peer_station_daily"] = [
            {
                "station_id": station_id,
                "station_name": evaluation["station_name"],
                "daily_value": evaluation[metric_key]["daily_value"],
                "exceeded": evaluation[metric_key]["exceeded"],
            }
            for station_id, evaluation in sorted(evaluation_by_station.items())
            if station_id != event["station_id"]
            and evaluation[metric_key]["status"] == "confirmed"
        ]
        station_hourly = [
            {
                key: value.isoformat() if isinstance(value, datetime) else value
                for key, value in row.items()
                if key != "data_source"
            }
            for row in rows
            if row.get("data_source") == "hour"
            and str(row.get("station_id")) == event["station_id"]
            and _hour(row.get("data_time")) is not None
            and _hour(row.get("data_time")).date() == target_date
        ]
        hourly = _hourly_evidence(
            [
                row for row in rows
                if row.get("data_source") == "hour"
                and _hour(row.get("data_time")) is not None
                and _hour(row.get("data_time")).date() == target_date
            ],
            event["station_id"],
        )
        event["station_hourly"] = station_hourly
        hourly_column = HOURLY_POLLUTANTS[event["target_pollutant"]][0]
        if station_hourly:
            event["hourly_rows"] = [
                {"time": row["data_time"], "concentration": row.get(hourly_column)}
                for row in station_hourly
                if row.get("data_time") is not None
            ]
        event["hourly_alerts"] = hourly["alerts"]
        event["hourly_checks"] = hourly["checks"]
        event["pollutant_synchronous_changes"] = hourly["synchronous_changes"]
        event["pollutant_change_classifications"] = [
            item for item in hourly["change_classifications"]
            if item["target_pollutant"] == event["target_pollutant"]
        ]
        event["pollutant_source_features"] = calculate_pollutant_source_features(
            [
                row for row in rows
                if row.get("data_source") == "hour"
                and _hour(row.get("data_time")) is not None
                and _hour(row.get("data_time")).date() == target_date
            ],
            event["station_id"],
        )
        event["component_station_evidence"] = {
            "status": "not_available",
            "reason": "xuchang_component_station_data_not_integrated",
        }
        event["township_and_provincial_transport"] = {
            "status": "not_available",
            "reason": "township_and_provincial_station_data_not_integrated",
        }
        event["meteorology_evidence"] = {
            "status": "not_available",
            "reason": "yesterday_hourly_meteorology_not_integrated",
        }
        event["local_source_indicators"] = {
            "status": "not_available",
            "reason": "local_source_activity_data_not_integrated",
        }
        event["data_quality"] = {
            "hourly_station_rows": len(station_hourly),
            "expected_hourly_rows": 24,
            "hourly_completeness_ratio": round(min(len(station_hourly) / 24, 1.0), 3),
            "daily_value_status": "confirmed",
        }
    return {"target_date": target_date.isoformat(), "evaluations": evaluations, "events": events}


def build_report_summary(
    station_rows: list[dict[str, Any]],
    regional_rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    target_date: date,
) -> dict[str, Any]:
    """Precompute compact, deterministic facts used by the report Agent."""
    pollutants = sorted({str(event.get("target_pollutant")) for event in events})
    alerts_by_pollutant = {
        pollutant: sum(1 for event in events if event.get("target_pollutant") == pollutant)
        for pollutant in pollutants
    }
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
    return {
        "target_date": target_date.isoformat(),
        "alert_count": len(events),
        "alerts_by_pollutant": alerts_by_pollutant,
        "alert_stations": sorted({str(event.get("station_id")) for event in events}),
        "station_pm25_statistics": station_stats,
        "regional_city_pm25_statistics": city_stats,
    }


class XuchangStationDailyPollutionFetcher(DataFetcher):
    """Read yesterday's station-day values and hourly review evidence once."""

    def __init__(
        self,
        *,
        analysis_service: XuchangTransportEscalationService | None = None,
        now_factory: Callable[[], datetime] = lambda: datetime.now(TZ_SHANGHAI),
    ) -> None:
        super().__init__(
            name="xuchang_station_daily_pollution_fetcher",
            description="许昌昨日单站点小时高值回顾、确定性计算与溯源任务触发",
            schedule="5 2 * * *",
            version="3.0.0",
        )
        self.analysis_service = analysis_service or XuchangTransportEscalationService()
        self.now_factory = now_factory

    def load_rows(self, target_date: date) -> list[dict[str, Any]]:
        start = datetime.combine(target_date, time.min)
        end = start + timedelta(days=1)
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            rows = []
            cursor.execute(
                """
                SELECT station_code, station_name, pm25, pm10, o3, no2, so2, co, time_point
                FROM dbo.dat_zhongda_station_hour
                WHERE time_point >= ? AND time_point < ?
                  AND area LIKE N'%许昌%'
                  AND station_code IN (?, ?, ?, ?, ?, ?)
                ORDER BY station_code, time_point
                """,
                [start, end, *TARGET_STATION_CODES],
            )
            rows.extend(
                {
                    "station_id": row[0], "name": row[1], "pm25": row[2],
                    "pm10": row[3], "o3": row[4], "no2": row[5], "so2": row[6],
                    "co": row[7], "data_time": row[8],
                    "lat": STATION_COORDINATES.get(str(row[0]), (None, None))[0],
                    "lon": STATION_COORDINATES.get(str(row[0]), (None, None))[1],
                    "data_source": "zhongda_raw_hour",
                }
                for row in cursor.fetchall()
            )
            return rows
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
                """
                SELECT Area, CityCode, TimePoint, PM2_5, PM10, O3, NO2, SO2, CO
                FROM dbo.CityAQIPublishHistory
                WHERE TimePoint >= ? AND TimePoint < ?
                  AND Area IN (PLACEHOLDERS)
                ORDER BY Area, TimePoint
                """.replace("PLACEHOLDERS", placeholders),
                [start, end, *city_names],
            )
            return [
                {
                    "city": row[0], "city_code": row[1], "data_time": row[2],
                    "pm25": _number(row[3]), "pm10": _number(row[4]), "o3": _number(row[5]), "no2": _number(row[6]),
                    "so2": _number(row[7]), "co": _number(row[8]), "data_source": "published_city_hour",
                }
                for row in cursor.fetchall()
            ]
        finally:
            connection.close()

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory()
        target_date = now.astimezone(TZ_SHANGHAI).date() - timedelta(days=1)
        station_rows = self.load_rows(target_date)
        result = evaluate_station_daily_pollution(station_rows, target_date=target_date)
        result["station_hourly"] = station_rows
        result["hourly_alerts"] = result.get("events", [])
        result["hourly_checks"] = result.get("evaluations", [])
        regional_rows = self.load_regional_hourly_rows(target_date)
        result["regional_city_hourly"] = regional_rows
        result["report_summary"] = build_report_summary(
            station_rows, regional_rows, result["events"], target_date
        )
        result["source_provenance"] = {
            "station_hourly": "中大源原始站点小时数据（dbo.dat_zhongda_station_hour）",
            "regional_city_hourly": "城市发布小时数据（dbo.CityAQIPublishHistory）",
            "meteorology": "NMC许昌观测站（station_id=ZzMTA）",
        }
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
        if result["meteorology"]:
            from app.tools.visualization.create_report_chart.domain.wind_timeseries import render_wind_timeseries

            def build_chart_rows(values_lookup: Callable[[datetime], list[float]]) -> list[dict[str, Any]]:
                chart_rows = []
                for met in result["meteorology"]:
                    meteorology_time = datetime.fromisoformat(met["time"])
                    if meteorology_time.tzinfo is not None:
                        meteorology_time = meteorology_time.astimezone(TZ_SHANGHAI).replace(tzinfo=None)
                    values = values_lookup(meteorology_time)
                    chart_rows.append({
                        "time": meteorology_time,
                        "concentration": sum(values) / len(values) if values else float("nan"),
                        "wind_speed_10m": met.get("wind_speed_10m"),
                        "wind_direction_10m": met.get("wind_direction_10m"),
                        "humidity": met.get("relative_humidity_2m"),
                        "precipitation": met.get("precipitation"),
                    })
                return chart_rows

            def chart_options(rows: list[dict[str, Any]]) -> dict[str, Any]:
                return {
                    "wind_direction_convention": "meteorological_from",
                    "include_humidity": True,
                    "include_precipitation": any(
                        row.get("precipitation") is not None and row["precipitation"] > 0 for row in rows
                    ),
                }

            by_time: dict[tuple[str, datetime], list[float]] = {}
            for row in station_rows:
                value = _number(row.get("pm25"))
                if value is not None:
                    by_time.setdefault((str(row.get("station_id")), row["data_time"]), []).append(value)
            chart_paths = {}
            alert_station_ids = sorted({event["station_id"] for event in result["events"]})
            for station_id in alert_station_ids:
                chart_rows = build_chart_rows(
                    lambda timestamp, sid=str(station_id): by_time.get((sid, timestamp), [])
                )
                if len(chart_rows) < 2:
                    continue
                station_name = next((str(row.get("name") or station_id) for row in station_rows
                                     if str(row.get("station_id")) == str(station_id)), station_id)
                image, _, _ = render_wind_timeseries(
                    title=f"{station_name}（{station_id}）{target_date}气象与PM2.5时序变化",
                    data={"records": chart_rows, "pollutant_name": "PM2.5", "unit": "μg/m³"},
                    options=chart_options(chart_rows),
                    output_context="word", style_profile="report",
                )
                safe_station = str(station_id).replace("/", "_")
                chart_path = get_images_dir() / f"许昌市{safe_station}_气象与PM2_5时序变化_{target_date}.png"
                chart_path.write_bytes(base64.b64decode(image))
                chart_paths[str(station_id)] = format_agent_path(chart_path)
            if chart_paths:
                result["meteorology_chart_paths"] = chart_paths
                if len(chart_paths) == 1:
                    result["meteorology_chart_path"] = next(iter(chart_paths.values()))
            else:
                city_by_time: dict[datetime, list[float]] = {}
                for row in station_rows:
                    value = _number(row.get("pm25"))
                    if value is not None:
                        city_by_time.setdefault(row["data_time"], []).append(value)
                chart_rows = build_chart_rows(lambda timestamp: city_by_time.get(timestamp, []))
                has_concentration = any(row["concentration"] == row["concentration"] for row in chart_rows)
                if len(chart_rows) >= 2 and has_concentration:
                    image, _, _ = render_wind_timeseries(
                        title=f"许昌市{target_date}气象与PM2.5时序变化（全市站点均值）",
                        data={"records": chart_rows, "pollutant_name": "PM2.5", "unit": "μg/m³"},
                        options=chart_options(chart_rows),
                        output_context="word", style_profile="report",
                    )
                    city_chart_path = get_images_dir() / f"许昌市全市均值_气象与PM2_5时序变化_{target_date}.png"
                    city_chart_path.write_bytes(base64.b64decode(image))
                    result["city_mean_meteorology_chart_path"] = format_agent_path(city_chart_path)
        for event in result["events"]:
            event["meteorology_evidence"] = {
                "status": "available" if result["meteorology"] else "not_available",
                "source": "NMC observed station ZzMTA",
                "rows": result["meteorology"],
            }
            station_chart_path = (result.get("meteorology_chart_paths") or {}).get(str(event["station_id"]))
            if station_chart_path:
                event["meteorology_chart_path"] = station_chart_path
            event["township_and_provincial_transport"] = {
                "status": "available" if regional_rows else "not_available",
                "source": "中大发布城市小时数据",
                "rows": regional_rows,
            }
        from app.scheduled_tasks import get_scheduled_task_service

        task_service = get_scheduled_task_service()
        review_path = get_data_registry() / "xuchang_station_daily_reviews" / f"{target_date:%Y%m%d}.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        # 事件 payload 只携带摘要与证据包路径；全量数据通过持久化文件传递，
        # 避免执行器把数百 KB 的原始小时数据灌进 Agent 对话上下文。
        review_payload = {
            "city": "许昌市",
            "target_date": result["target_date"],
            "event_count": len(result["events"]),
            "alert_stations": sorted({
                f"{event['station_id']}({event['target_pollutant']})"
                for event in result["events"]
            }),
            "evidence_package_path": format_agent_path(review_path),
            "template_path": "/home/xckj/suyuan/backend/backend_data_registry/uploads/401ecbb4-c402-4f55-b37c-331e7a88b49d.docx",
        }
        review_event = TaskEvent(
            event_id=f"xuchang-station-daily-review-{target_date:%Y%m%d}",
            event_type=DAILY_REVIEW_EVENT_TYPE,
            occurred_at=datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=TZ_SHANGHAI).isoformat(),
            attributes={"city": "许昌市", "target_date": result["target_date"]},
            payload=review_payload,
        )
        publish_kwargs = {}
        if "force_retry" in inspect.signature(task_service.publish_event).parameters:
            publish_kwargs["force_retry"] = True
        await task_service.publish_event(review_event, **publish_kwargs)
        if result["events"]:
            for event in result["events"]:
                ingestion = self.analysis_service.ingest_daily_exceedance(event)
                event["scenario_2"] = {
                    "status": ingestion["status"],
                    "analysis_id": ingestion.get("analysis", {}).get("analysis_id"),
                    "job_id": (ingestion.get("job") or {}).get("job_id"),
                }
                await task_service.publish_event(TaskEvent(
                    event_id=event["event_id"],
                    event_type=CONFIRMED_EVENT_TYPE,
                    occurred_at=event["occurred_at"],
                    attributes={
                        "city": event["city"],
                        "station_id": event["station_id"],
                        "target_date": event["target_date"],
                        "target_pollutant": event["target_pollutant"],
                    },
                    payload=event,
                ))
                if ingestion.get("job"):
                    job = ingestion["job"]
                    await task_service.publish_event(TaskEvent(
                        event_id=job["event_id"],
                        event_type=REQUESTED_EVENT_TYPE,
                        occurred_at=event["occurred_at"],
                        attributes={
                            "city": event["city"],
                            "station_id": event["station_id"],
                            "target_date": event["target_date"],
                            "target_pollutant": event["target_pollutant"],
                        },
                        payload=job,
                    ))
        logger.info(
            "xuchang_station_daily_pollution_completed",
            target_date=result["target_date"],
            event_count=len(result["events"]),
        )
        return result

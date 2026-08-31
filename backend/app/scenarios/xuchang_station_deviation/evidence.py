"""Collect and pre-compute the evidence consumed by the Scenario 1 Agent."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from math import atan2, cos, degrees, radians, sin, sqrt
from statistics import mean, median
from typing import Any
from zoneinfo import ZoneInfo

import pyodbc

from app.db.repositories.weather_repo import WeatherRepository
from app.integrations.xcai_station_sql import xcai_connection_string

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
XUCHANG_CITY = "许昌市"
XUCHANG_CITY_AREA_CODE = "411000"
# 场景一告警只需要许昌本地站点和许昌气象站实况，避免无关区域数据放大证据包。
NMC_STATIONS = {"ZzMTA": "许昌"}
POLLUTANT_COLUMNS = {"PM2.5": "pm25", "O3": "o3", "NOX": "no2"}
AIR_QUALITY_LOOKBACK_HOURS = 12
OBSERVED_WEATHER_LOOKBACK_HOURS = 3
CALM_WIND_THRESHOLD_MS = 1.5
# NMC 城市预报为 3 小时间隔；告警时刻后 3 小时内应能找到最近槽位。
NMC_FORECAST_TABLE = "XuchangNmcHourlyWeatherForecast"
NMC_FORECAST_LOOKAHEAD_HOURS = 3


def _event_hour(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ_SHANGHAI)
    return parsed.astimezone(TZ_SHANGHAI).replace(minute=0, second=0, microsecond=0)


def _event_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ_SHANGHAI)
    return parsed.astimezone(TZ_SHANGHAI)


def _record_hour(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ_SHANGHAI)
    return parsed.astimezone(TZ_SHANGHAI).replace(minute=0, second=0, microsecond=0)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _rounded(value: float | None, digits: int = 3) -> float | None:
    return round(value, digits) if value is not None else None


def _json_value(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _rows(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    return [
        {key: _json_value(value) for key, value in zip(columns, row, strict=True)}
        for row in cursor.fetchall()
    ]


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 4 or len(left) != len(right):
        return None
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    denominator = sqrt(
        sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else None


def _change(series: dict[datetime, float], end: datetime, hours: int) -> dict[str, Any]:
    current, previous = series.get(end), series.get(end - timedelta(hours=hours))
    absolute = current - previous if current is not None and previous is not None else None
    percent = absolute / previous * 100 if absolute is not None and previous else None
    return {
        "hours": hours,
        "current": _rounded(current),
        "previous": _rounded(previous),
        "absolute_change": _rounded(absolute),
        "percent_change": _rounded(percent, 1),
    }


def _series_by_time(rows: Iterable[dict[str, Any]], field: str) -> dict[datetime, float]:
    result = {}
    for row in rows:
        hour, value = _record_hour(row.get("time")), _number(row.get(field))
        if hour is not None and value is not None:
            result[hour] = value
    return result


def _station_indicators(
    alert: dict[str, Any], station_rows: list[dict[str, Any]], event_hour: datetime
) -> dict[str, Any]:
    field = POLLUTANT_COLUMNS.get(str(alert.get("target_pollutant")))
    station_id = str(alert.get("station_id") or "")
    if not field or not station_id:
        return {"status": "unavailable", "reason": "unsupported_pollutant_or_missing_station_id"}

    target_rows = [row for row in station_rows if str(row.get("station_id")) == station_id]
    target = _series_by_time(target_rows, field)
    by_hour: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in station_rows:
        if (hour := _record_hour(row.get("time"))) is not None:
            by_hour[hour].append(row)

    peer_medians: dict[datetime, float] = {}
    comparison = []
    for hour in sorted(by_hour):
        peers = [
            value
            for row in by_hour[hour]
            if str(row.get("station_id")) != station_id
            and (value := _number(row.get(field))) is not None
        ]
        target_value = target.get(hour)
        peer_value = median(peers) if peers else None
        if peer_value is not None:
            peer_medians[hour] = peer_value
        delta = target_value - peer_value if target_value is not None and peer_value is not None else None
        deviation = delta / peer_value * 100 if delta is not None and peer_value else None
        comparison.append({
            "time": hour.isoformat(),
            "target_value": _rounded(target_value),
            "peer_median": _rounded(peer_value),
            "absolute_delta": _rounded(delta),
            "deviation_percent": _rounded(deviation, 1),
            "peer_count": len(peers),
        })

    ordered = sorted(target.items())
    hourly_increases = [
        (hour, value - ordered[index - 1][1])
        for index, (hour, value) in enumerate(ordered)
        if index > 0 and hour - ordered[index - 1][0] == timedelta(hours=1)
    ]
    peak = max(ordered, key=lambda item: item[1]) if ordered else None
    largest_rise = max(hourly_increases, key=lambda item: item[1]) if hourly_increases else None

    direction_matches = 0
    direction_pairs = 0
    common_hours = sorted(set(target) & set(peer_medians))
    for previous, current in zip(common_hours, common_hours[1:], strict=False):
        if current - previous != timedelta(hours=1):
            continue
        target_delta = target[current] - target[previous]
        peer_delta = peer_medians[current] - peer_medians[previous]
        if target_delta == 0 or peer_delta == 0:
            continue
        direction_pairs += 1
        direction_matches += int((target_delta > 0) == (peer_delta > 0))

    latest_target_row = next(
        (row for row in target_rows if _record_hour(row.get("time")) == event_hour), None
    )
    ratios = {}
    if latest_target_row:
        pm25, pm10 = _number(latest_target_row.get("pm25")), _number(latest_target_row.get("pm10"))
        no2, o3 = _number(latest_target_row.get("no2")), _number(latest_target_row.get("o3"))
        so2, co = _number(latest_target_row.get("so2")), _number(latest_target_row.get("co"))
        ratios = {
            "pm25_pm10": _rounded(pm25 / pm10 if pm25 is not None and pm10 else None),
            "no2_o3": _rounded(no2 / o3 if no2 is not None and o3 else None),
            "so2_co": _rounded(so2 / co if so2 is not None and co else None),
        }

    expected_points = AIR_QUALITY_LOOKBACK_HOURS + 1
    return {
        "status": "success" if target else "unavailable",
        "pollutant": alert.get("target_pollutant"),
        "observed_field": field,
        "target_station_id": station_id,
        "changes": [_change(target, event_hour, hours) for hours in (1, 3, 6)],
        "peak": {"time": peak[0].isoformat(), "value": _rounded(peak[1])} if peak else None,
        "largest_hourly_rise": (
            {"time": largest_rise[0].isoformat(), "absolute_change": _rounded(largest_rise[1])}
            if largest_rise else None
        ),
        "target_peer_hourly_comparison": comparison,
        "local_direction_agreement": {
            "comparable_changes": direction_pairs,
            "same_direction_changes": direction_matches,
            "agreement_ratio": _rounded(direction_matches / direction_pairs if direction_pairs else None),
        },
        "current_pollutant_ratios": ratios,
        "data_completeness": {
            "expected_hours": expected_points,
            "available_target_hours": len(target),
            "completeness_ratio": _rounded(min(len(target) / expected_points, 1.0)),
        },
    }


def _station_5min_indicators(alert: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    field = POLLUTANT_COLUMNS.get(str(alert.get("target_pollutant"))) or str(alert.get("target_pollutant", "")).lower()
    station_id = str(alert.get("station_id") or "")
    parsed = []
    for row in rows:
        try:
            timestamp = datetime.fromisoformat(str(row.get("time")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        value = _number(row.get(field))
        if value is not None:
            parsed.append((timestamp, row, value))
    target = sorted((t, v) for t, row, v in parsed if str(row.get("station_id")) == station_id)
    target_changes = [
        {"time": t.isoformat(), "value": _rounded(value), "absolute_change": _rounded(value - target[i - 1][1]),
         "percent_change": _rounded((value - target[i - 1][1]) / target[i - 1][1] * 100, 1) if target[i - 1][1] else None}
        for i, (t, value) in enumerate(target) if i and t - target[i - 1][0] <= timedelta(minutes=10)
    ]
    peer_comparison = []
    for timestamp in sorted({t for t, _, _ in parsed}):
        slot_rows = [(row, value) for t, row, value in parsed if t == timestamp]
        target_value = next((value for row, value in slot_rows if str(row.get("station_id")) == station_id), None)
        peers = [value for row, value in slot_rows if str(row.get("station_id")) != station_id]
        peer_value = median(peers) if peers else None
        peer_comparison.append({
            "time": timestamp.isoformat(),
            "target_value": _rounded(target_value),
            "peer_median": _rounded(peer_value),
            "absolute_delta": _rounded(target_value - peer_value) if target_value is not None and peer_value is not None else None,
            "deviation_percent": _rounded((target_value - peer_value) / peer_value * 100, 1) if target_value is not None and peer_value else None,
            "peer_count": len(peers),
        })
    mark_fields = [f"{field}_mark"]
    marked = [
        {"time": str(row.get("time")), "station_id": row.get("station_id"), "mark": row.get(mark_fields[0])}
        for _, row, _ in parsed if str(row.get("station_id")) == station_id and row.get(mark_fields[0]) not in (None, "")
    ]
    return {
        "status": "success" if target else "unavailable",
        "pollutant": alert.get("target_pollutant"),
        "observed_field": field,
        "window": "previous_1_hour",
        "target_station_values": [{"time": t.isoformat(), "value": _rounded(v)} for t, v in target],
        "target_station_5min_changes": target_changes,
        "target_peer_5min_comparison": peer_comparison,
        "marked_quality_records": marked,
        "peer_comparison_note": "每个5分钟槽位的周边站点中位数用于对比；带mark记录不作为污染异常事实直接解释。",
    }


def _weather_row(record: Any) -> dict[str, Any]:
    fields = (
        "time", "station_id", "station_name", "lat", "lon", "temperature_2m",
        "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m",
        "surface_pressure", "precipitation", "data_source", "data_quality",
    )
    return {field: _json_value(getattr(record, field, None)) for field in fields}


def _weather_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_station: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_station[str(row.get("station_id"))].append(row)
    summaries = []
    for station_id, station_rows in sorted(by_station.items()):
        station_rows.sort(key=lambda row: str(row.get("time")))
        speeds = [value for row in station_rows if (value := _number(row.get("wind_speed_10m"))) is not None]
        humidities = [value for row in station_rows if (value := _number(row.get("relative_humidity_2m"))) is not None]
        rainfall = [value for row in station_rows if (value := _number(row.get("precipitation"))) is not None]
        directions = [
            radians(value)
            for row in station_rows
            if (value := _number(row.get("wind_direction_10m"))) is not None
        ]
        x = mean([cos(value) for value in directions]) if directions else None
        y = mean([sin(value) for value in directions]) if directions else None
        concentration = sqrt(x * x + y * y) if x is not None and y is not None else None
        prevailing = (degrees(atan2(y, x)) + 360) % 360 if x is not None and y is not None else None
        summaries.append({
            "station_id": station_id,
            "station_name": station_rows[-1].get("station_name") or NMC_STATIONS.get(station_id),
            "record_count": len(station_rows),
            "latest_time": station_rows[-1].get("time"),
            "mean_wind_speed_ms": _rounded(mean(speeds) if speeds else None),
            "calm_hours": sum(value <= CALM_WIND_THRESHOLD_MS for value in speeds),
            "prevailing_wind_direction_deg": _rounded(prevailing, 1),
            "wind_direction_concentration": _rounded(concentration),
            "mean_relative_humidity_percent": _rounded(mean(humidities) if humidities else None),
            "high_humidity_hours_ge_80_percent": sum(value >= 80 for value in humidities),
            "accumulated_precipitation_mm": _rounded(sum(rainfall) if rainfall else None),
        })
    return {
        "calm_wind_threshold_ms": CALM_WIND_THRESHOLD_MS,
        "wind_direction_concentration_note": "取值0-1，越接近1表示观测窗口内风向越稳定",
        "stations": summaries,
    }


def _maintenance_qc_review(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return QC evidence only when the target station has an actual mark."""
    mark_names = ("pm25_mark", "pm10_mark", "o3_mark", "no2_mark", "so2_mark", "co_mark", "nox_mark")
    marked = [
        {
            "time": row.get("time"),
            "station_id": row.get("station_id"),
            "marks": {name: row.get(name) for name in mark_names if row.get(name) not in (None, "")},
        }
        for row in rows
        if any(row.get(name) not in (None, "") for name in mark_names)
    ]
    if not marked:
        return None
    return {
        "required": True,
        "records": marked,
        "instruction": "存在质控标记；相关污染物数据可能受运维质控操作影响，不应直接归因于污染变化。",
    }


class XuchangStationDeviationEvidenceCollector:
    """Fetch external context and compute stable metrics before invoking an Agent."""

    def __init__(
        self,
        *,
        connection_string_factory: Callable[[], str] = xcai_connection_string,
        forecast_client: Any | None = None,
        weather_repo: WeatherRepository | None = None,
    ) -> None:
        self.connection_string_factory = connection_string_factory
        self.weather_repo = weather_repo or WeatherRepository()

    async def collect(
        self,
        *,
        alert: dict[str, Any],
        source_screening: dict[str, Any],
    ) -> dict[str, Any]:
        event_time = _event_time(alert["occurred_at"])
        event_hour = _event_hour(alert["occurred_at"])
        air_start = event_hour - timedelta(hours=AIR_QUALITY_LOOKBACK_HOURS)
        weather_start = event_time - timedelta(hours=OBSERVED_WEATHER_LOOKBACK_HOURS)
        air_result, observed_result, forecast_result = await asyncio.gather(
            asyncio.to_thread(self._load_air_quality, air_start, event_time),
            self._load_observed_weather(weather_start, event_time),
            asyncio.to_thread(self._load_forecast_weather, event_time),
            return_exceptions=True,
        )

        errors = []
        if isinstance(air_result, BaseException):
            errors.append({"asset": "air_quality_context", "error": str(air_result)})
            air_quality: dict[str, Any] = {
                "status": "failed", "window": {"start": air_start.isoformat(), "end": event_hour.isoformat()},
                "local_station_hour_records": [], "local_station_5min_records": [],
                "maintenance_qc_review": None,
            }
        else:
            air_quality = air_result

        if isinstance(observed_result, BaseException):
            errors.append({"asset": "observed_meteorology", "error": str(observed_result)})
            observed_meteorology: dict[str, Any] = {
                "status": "failed", "window": {"start": air_start.isoformat(), "end": event_hour.isoformat()},
                "station_hour_records": [], "summary": {"stations": []},
            }
        else:
            observed_meteorology = observed_result

        if isinstance(forecast_result, BaseException):
            errors.append({"asset": "forecast_meteorology", "error": str(forecast_result)})
            forecast_meteorology: dict[str, Any] = {
                "status": "failed", "source": f"XcAiDb.dbo.{NMC_FORECAST_TABLE}",
                "event_time": event_time.isoformat(), "nearest_forecast": None,
            }
        else:
            forecast_meteorology = forecast_result

        computed_indicators = {
            "calculation_status": "success" if air_quality.get("local_station_hour_records") else "unavailable",
            "station_process": _station_indicators(
                alert, air_quality.get("local_station_hour_records", []), event_hour
            ),
            "station_5min_process": _station_5min_indicators(
                alert, air_quality.get("local_station_5min_records", [])
            ),
            "calculation_notes": [
                "NOX事件使用站点NO2小时浓度作为空间异常代理。",
                "相关性和领先滞后是时序关系，不等同于来源因果关系。",
                "所有指标仅基于证据窗口内已落库数据计算。",
            ],
        }

        source_screening_status = source_screening.get("status")
        if source_screening_status not in {"success", "not_run"}:
            errors.append({
                "asset": "source_screening",
                "error": (
                    source_screening.get("error")
                    or source_screening.get("summary")
                    or f"source_screening_{source_screening_status or 'failed'}"
                ),
            })
        asset_statuses = [
            air_quality.get("status"),
            observed_meteorology.get("status"),
            forecast_meteorology.get("status"),
        ]
        if source_screening_status != "not_run":
            asset_statuses.insert(0, source_screening_status)
        if all(status == "success" for status in asset_statuses):
            collection_status = "complete"
        elif any(status in {"success", "partial"} for status in asset_statuses):
            collection_status = "partial"
        else:
            collection_status = "failed"
        return {
            "schema_version": "xuchang_station_deviation_evidence/v3",
            "generated_at": datetime.now(TZ_SHANGHAI).isoformat(),
            "event": dict(alert),
            "source_screening": source_screening,
            "air_quality_context": air_quality,
            "observed_meteorology": observed_meteorology,
            "forecast_meteorology": forecast_meteorology,
            "computed_indicators": computed_indicators,
            "collection": {
                "status": collection_status,
                "errors": errors,
                "interpretation_contract": (
                    "Agent只读取本证据包开展监测告警通报；确定性指标直接引用computed_indicators，"
                    "mark造成的质控影响必须与污染事实区分。"
                ),
            },
        }

    def _load_air_quality(self, start: datetime, end: datetime) -> dict[str, Any]:
        start_value = start.replace(tzinfo=None)
        end_value = end.replace(tzinfo=None)
        connection = pyodbc.connect(self.connection_string_factory(), timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT data_time AS time, station_id, name AS station_name,
                       lon, lat, pm25, pm10, o3, no2, so2, co, aqi
                FROM dbo.dat_station_hour
                WHERE city_area_code = ? AND data_time >= ? AND data_time <= ?
                ORDER BY data_time, station_id
                """,
                [XUCHANG_CITY_AREA_CODE, start_value, end_value],
            )
            station_rows = _rows(cursor)
            minute_start_value = (end - timedelta(hours=1)).replace(tzinfo=None)
            cursor.execute(
                """
                SELECT time_point AS time, station_code AS station_id,
                       station_name, area,
                       pm25, pm25_mark, pm10, pm10_mark,
                       o3, o3_mark, no2, no2_mark,
                       so2, so2_mark, co, co_mark, nox, nox_mark
                FROM dbo.dat_zhongda_station_minute
                WHERE area = ? AND time_point >= ? AND time_point <= ?
                ORDER BY time_point, station_code
                """,
                [XUCHANG_CITY, minute_start_value, end_value],
            )
            station_minute_rows = _rows(cursor)
        finally:
            connection.close()

        air_status = "success" if station_rows or station_minute_rows else "empty"
        return {
            "status": air_status,
            "source": "XcAiDb.dbo.dat_station_hour + XcAiDb.dbo.dat_zhongda_station_minute",
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "local_station_hour_records": station_rows,
            "local_station_5min_records": station_minute_rows,
            "record_counts": {
                "local_station_hours": len(station_rows),
                "local_station_5min": len(station_minute_rows),
            },
            "maintenance_qc_review": _maintenance_qc_review(station_minute_rows),
        }

    async def _load_observed_weather(self, start: datetime, end: datetime) -> dict[str, Any]:
        results = await asyncio.gather(*(
            self.weather_repo.get_observed_data(station_id, start, end)
            for station_id in NMC_STATIONS
        ))
        rows = [_weather_row(record) for station_rows in results for record in station_rows]
        return {
            "status": "success" if rows else "empty",
            "source": "observed_weather_data (NMC)",
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "stations": [{"station_id": station_id, "station_name": name} for station_id, name in NMC_STATIONS.items()],
            "station_hour_records": rows,
            "record_count": len(rows),
            "summary": _weather_summary(rows),
            "units": {
                "temperature_2m": "degC", "relative_humidity_2m": "%", "wind_speed_10m": "m/s",
                "wind_direction_10m": "degree", "surface_pressure": "hPa", "precipitation": "mm",
            },
        }

    def _load_forecast_weather(self, event_time: datetime) -> dict[str, Any]:
        """Load the NMC hourly forecast row nearest to the alert time."""
        event_value = event_time.replace(tzinfo=None)
        window_start = event_value
        window_end = event_value + timedelta(hours=NMC_FORECAST_LOOKAHEAD_HOURS)
        connection = pyodbc.connect(self.connection_string_factory(), timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP (1) station_id, city_code, city_name, forecast_time, publish_time,
                       temperature, humidity, pressure, wind_speed, wind_direction,
                       wind_direction_degrees, precipitation_probability, precipitation_text,
                       weather_code, weather_text,
                       DATEDIFF(MINUTE, ?, forecast_time) AS offset_minutes
                FROM dbo.{NMC_FORECAST_TABLE}
                WHERE forecast_time >= ? AND forecast_time <= ?
                ORDER BY forecast_time ASC
                """,
                [event_value, window_start, window_end, event_value],
            )
            rows = _rows(cursor)
        finally:
            connection.close()

        nearest = rows[0] if rows else None
        return {
            "status": "success" if nearest else "empty",
            "source": f"XcAiDb.dbo.{NMC_FORECAST_TABLE} (NMC 3小时间隔城市预报)",
            "event_time": event_time.isoformat(),
            "selection": f"告警时间至未来{NMC_FORECAST_LOOKAHEAD_HOURS}h窗口内forecast_time最近的一条预报",
            "nearest_forecast": nearest,
            "offset_note": "仅选择offset_minutes>=0且不超过未来3小时的预报",
            "units": {
                "temperature": "degC", "humidity": "%", "pressure": "hPa",
                "wind_speed": "m/s", "wind_direction_degrees": "degree",
                "precipitation_probability": "%",
            },
        }

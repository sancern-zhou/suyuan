"""Collect and pre-compute the evidence consumed by the Scenario 1 Agent."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from math import atan2, cos, degrees, radians, sin, sqrt
from statistics import mean, median
from typing import Any
from zoneinfo import ZoneInfo

import pyodbc

from app.db.repositories.weather_repo import WeatherRepository
from app.external_apis.openmeteo_client import OpenMeteoClient
from app.integrations.xcai_station_sql import xcai_connection_string

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
XUCHANG_CITY = "许昌市"
XUCHANG_CITY_AREA_CODE = "411000"
XUCHANG_NEARBY_CITIES = ("郑州市", "开封市", "周口市", "漯河市", "平顶山市")
NMC_STATIONS = {"ZzMTA": "许昌", "HFqwM": "禹州", "sHlBF": "长葛"}
POLLUTANT_COLUMNS = {"PM2.5": "pm25", "O3": "o3", "NOX": "no2"}
AIR_QUALITY_LOOKBACK_HOURS = 12
METEOROLOGY_FORECAST_HOURS = 24
CALM_WIND_THRESHOLD_MS = 1.5


def _event_hour(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ_SHANGHAI)
    return parsed.astimezone(TZ_SHANGHAI).replace(minute=0, second=0, microsecond=0)


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


def _regional_indicators(
    city_rows: list[dict[str, Any]], pollutant: str, event_hour: datetime
) -> dict[str, Any]:
    field = POLLUTANT_COLUMNS.get(pollutant)
    if not field:
        return {"status": "unavailable", "reason": "unsupported_pollutant"}
    by_city = {
        city: _series_by_time((row for row in city_rows if row.get("city") == city), field)
        for city in (XUCHANG_CITY, *XUCHANG_NEARBY_CITIES)
    }
    target = by_city[XUCHANG_CITY]
    comparisons = []
    for city in XUCHANG_NEARBY_CITIES:
        nearby = by_city[city]
        lag_results = []
        for nearby_lead_hours in range(-3, 4):
            pairs = [
                (target_value, nearby.get(hour - timedelta(hours=nearby_lead_hours)))
                for hour, target_value in target.items()
            ]
            valid = [(left, right) for left, right in pairs if right is not None]
            correlation = _pearson(
                [left for left, _ in valid], [right for _, right in valid]
            )
            if correlation is not None:
                lag_results.append({
                    "nearby_lead_hours": nearby_lead_hours,
                    "correlation": _rounded(correlation),
                    "paired_hours": len(valid),
                })
        best = max(lag_results, key=lambda item: item["correlation"]) if lag_results else None
        comparisons.append({
            "city": city,
            "current_value": _rounded(nearby.get(event_hour)),
            "changes": [_change(nearby, event_hour, hours) for hours in (1, 3, 6)],
            "same_hour_correlation": next(
                (item["correlation"] for item in lag_results if item["nearby_lead_hours"] == 0), None
            ),
            "best_lag_correlation": best,
        })
    return {
        "status": "success" if target else "unavailable",
        "lag_semantics": "nearby_lead_hours > 0 表示周边城市变化早于许昌",
        "xuchang_changes": [_change(target, event_hour, hours) for hours in (1, 3, 6)],
        "nearby_city_comparisons": comparisons,
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


class XuchangStationDeviationEvidenceCollector:
    """Fetch external context and compute stable metrics before invoking an Agent."""

    def __init__(
        self,
        *,
        connection_string_factory: Callable[[], str] = xcai_connection_string,
        forecast_client: OpenMeteoClient | None = None,
        weather_repo: WeatherRepository | None = None,
    ) -> None:
        self.connection_string_factory = connection_string_factory
        self.forecast_client = forecast_client or OpenMeteoClient()
        self.weather_repo = weather_repo or WeatherRepository()

    async def collect(
        self,
        *,
        alert: dict[str, Any],
        source_screening: dict[str, Any],
    ) -> dict[str, Any]:
        event_hour = _event_hour(alert["occurred_at"])
        air_start = event_hour - timedelta(hours=AIR_QUALITY_LOOKBACK_HOURS)
        forecast_end = event_hour + timedelta(hours=METEOROLOGY_FORECAST_HOURS)

        air_result, observed_result, forecast_result = await asyncio.gather(
            asyncio.to_thread(self._load_air_quality, air_start, event_hour),
            self._load_observed_weather(air_start, event_hour),
            self._load_forecast(
                lat=float(alert["lat"]), lon=float(alert["lon"]),
                start=event_hour, end=forecast_end,
            ),
            return_exceptions=True,
        )

        errors = []
        if isinstance(air_result, BaseException):
            errors.append({"asset": "air_quality_context", "error": str(air_result)})
            air_quality: dict[str, Any] = {
                "status": "failed", "window": {"start": air_start.isoformat(), "end": event_hour.isoformat()},
                "target_city": XUCHANG_CITY, "nearby_cities": list(XUCHANG_NEARBY_CITIES),
                "target_city_hour_records": [], "nearby_city_hour_records": [], "local_station_hour_records": [],
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
                "status": "failed", "window": {"start": event_hour.isoformat(), "end": forecast_end.isoformat()},
                "receptor": {"lat": alert["lat"], "lon": alert["lon"]}, "hourly": [],
            }
        else:
            forecast_meteorology = forecast_result

        computed_indicators = {
            "calculation_status": "success" if air_quality.get("local_station_hour_records") else "unavailable",
            "station_process": _station_indicators(
                alert, air_quality.get("local_station_hour_records", []), event_hour
            ),
            "regional_comparison": _regional_indicators(
                [*air_quality.get("target_city_hour_records", []), *air_quality.get("nearby_city_hour_records", [])],
                str(alert.get("target_pollutant")), event_hour,
            ),
            "calculation_notes": [
                "NOX事件使用站点NO2小时浓度作为空间异常代理。",
                "相关性和领先滞后是时序关系，不等同于来源因果关系。",
                "所有指标仅基于证据窗口内已落库数据计算。",
            ],
        }

        asset_statuses = [air_quality.get("status"), observed_meteorology.get("status"), forecast_meteorology.get("status")]
        if all(status == "success" for status in asset_statuses):
            collection_status = "complete"
        elif any(status in {"success", "partial"} for status in asset_statuses):
            collection_status = "partial"
        else:
            collection_status = "failed"
        return {
            "schema_version": "xuchang_station_deviation_evidence/v2",
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
                "excluded_data": {
                    "city_air_quality_forecast": "not_collected: event scope is station-level source tracing",
                },
                "interpretation_contract": (
                    "Agent只读取本证据包开展逻辑分析，不重新调用上风向筛查、空气质量或气象查询工具；"
                    "确定性指标直接引用computed_indicators，相关性不得表述为因果归因。"
                ),
            },
        }

    def _load_air_quality(self, start: datetime, end: datetime) -> dict[str, Any]:
        start_value = start.replace(tzinfo=None)
        end_value = end.replace(tzinfo=None)
        cities = [XUCHANG_CITY, *XUCHANG_NEARBY_CITIES]
        placeholders = ",".join("?" for _ in cities)
        connection = pyodbc.connect(self.connection_string_factory(), timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TimePoint AS time, Area AS city, CityCode AS city_code,
                       PM2_5 AS pm25, PM10 AS pm10, O3 AS o3, NO2 AS no2,
                       SO2 AS so2, CO AS co, AQI AS aqi,
                       PrimaryPollutant AS primary_pollutant, Quality AS quality
                FROM dbo.CityAQIPublishHistory
                WHERE Area IN ({placeholders}) AND TimePoint >= ? AND TimePoint <= ?
                ORDER BY TimePoint, Area
                """,
                [*cities, start_value, end_value],
            )
            city_rows = _rows(cursor)
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
        finally:
            connection.close()

        air_status = "success" if city_rows and station_rows else "partial" if city_rows or station_rows else "empty"
        return {
            "status": air_status,
            "source": "XcAiDb.CityAQIPublishHistory + dbo.dat_station_hour",
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "target_city": XUCHANG_CITY,
            "nearby_cities": list(XUCHANG_NEARBY_CITIES),
            "target_city_hour_records": [row for row in city_rows if row.get("city") == XUCHANG_CITY],
            "nearby_city_hour_records": [row for row in city_rows if row.get("city") != XUCHANG_CITY],
            "local_station_hour_records": station_rows,
            "record_counts": {"city_hours": len(city_rows), "local_station_hours": len(station_rows)},
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

    async def _load_forecast(
        self, *, lat: float, lon: float, start: datetime, end: datetime,
    ) -> dict[str, Any]:
        raw = await self.forecast_client.fetch_forecast(
            lat=lat, lon=lon, forecast_days=2, past_days=0, hourly=True, daily=True,
        )
        hourly_source = raw.get("hourly") if isinstance(raw.get("hourly"), dict) else {}
        times = hourly_source.get("time") or []
        hourly = []
        for index, time_value in enumerate(times):
            parsed = datetime.fromisoformat(str(time_value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            local_time = parsed.astimezone(TZ_SHANGHAI)
            if not start <= local_time <= end:
                continue
            record = {"time": local_time.isoformat()}
            for field, values in hourly_source.items():
                if field == "time" or not isinstance(values, list):
                    continue
                record[field] = values[index] if index < len(values) else None
            hourly.append(record)

        return {
            "status": "success" if hourly else "empty",
            "source": "Open-Meteo Forecast API (meteorology only)",
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "receptor": {"lat": lat, "lon": lon},
            "hourly": hourly,
            "record_count": len(hourly),
            "daily": raw.get("daily") or {},
            "units": {"hourly": raw.get("hourly_units") or {}, "daily": raw.get("daily_units") or {}},
        }

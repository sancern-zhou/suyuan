"""Open-Meteo air quality forecast fetcher for Yuncheng and Xuchang."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

import pyodbc
import requests
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client

logger = structlog.get_logger()

OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
AIR_QUALITY_HOURLY_FIELDS = (
    "pm10",
    "pm2_5",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
)


@dataclass(frozen=True)
class AirQualityForecastCity:
    key: str
    name: str
    city_code: str
    lat: float
    lon: float


@dataclass(frozen=True)
class DailyForecastTarget:
    city: str
    forecast_date: str
    min_aqi: int
    max_aqi: int
    primary_pollutant: str | None = None
    update_time: str | None = None


@dataclass(frozen=True)
class HourlyObservation:
    city: str
    time: datetime
    aqi: int
    pollutants: dict[str, float | None]


AIR_QUALITY_FORECAST_CITIES: dict[str, AirQualityForecastCity] = {
    "yuncheng": AirQualityForecastCity(
        key="yuncheng",
        name="运城市",
        city_code="140800",
        lat=35.11,
        lon=111.06,
    ),
    "xuchang": AirQualityForecastCity(
        key="xuchang",
        name="许昌市",
        city_code="411000",
        lat=34.07,
        lon=113.92,
    ),
}

AQI_LEVELS = (
    (0, 50, "优"),
    (51, 100, "良"),
    (101, 150, "轻度污染"),
    (151, 200, "中度污染"),
    (201, 300, "重度污染"),
    (301, 500, "严重污染"),
)


def _linear_iaqi(value: float, breakpoints: tuple[tuple[float, int], ...]) -> int | None:
    if value is None or value < 0:
        return None
    if value == 0:
        return 0

    previous_concentration = 0.0
    previous_iaqi = 0
    for concentration, iaqi in breakpoints:
        if value <= concentration:
            if concentration == previous_concentration:
                return iaqi
            return round(
                (iaqi - previous_iaqi)
                / (concentration - previous_concentration)
                * (value - previous_concentration)
                + previous_iaqi
            )
        previous_concentration = concentration
        previous_iaqi = iaqi

    return 500


def pm25_to_iaqi(value: float | None) -> int | None:
    return _linear_iaqi(
        value,
        ((35, 50), (75, 100), (115, 150), (150, 200), (250, 300), (350, 400), (500, 500)),
    )


def pm10_to_iaqi(value: float | None) -> int | None:
    return _linear_iaqi(
        value,
        ((50, 50), (150, 100), (250, 150), (350, 200), (420, 300), (500, 400), (600, 500)),
    )


def o3_hourly_to_iaqi(value: float | None) -> int | None:
    return _linear_iaqi(value, ((200, 50), (300, 100), (400, 150), (800, 200), (1000, 300)))


def so2_to_iaqi(value: float | None) -> int | None:
    return _linear_iaqi(value, ((50, 50), (150, 100), (475, 150), (800, 200), (1600, 300)))


def no2_to_iaqi(value: float | None) -> int | None:
    return _linear_iaqi(value, ((40, 50), (80, 100), (180, 150), (280, 200), (565, 300)))


def co_to_iaqi(value: float | None) -> int | None:
    if value is None:
        return None
    return _linear_iaqi(value / 1000, ((2, 50), (4, 100), (14, 150), (24, 200), (36, 300)))


POLLUTANT_THRESHOLDS = {
    "pm25": ((0, 0), (35, 50), (75, 100), (115, 150), (150, 200), (250, 300), (350, 400), (500, 500)),
    "pm10": ((0, 0), (50, 50), (150, 100), (250, 150), (350, 200), (420, 300), (500, 400), (600, 500)),
    "o3": ((0, 0), (100, 50), (160, 100), (215, 150), (265, 200), (800, 300), (800, 400), (800, 500)),
    "so2": ((0, 0), (50, 50), (150, 100), (475, 150), (800, 200), (1600, 300), (2340, 400), (2340, 500)),
    "no2": ((0, 0), (40, 50), (80, 100), (180, 150), (280, 200), (565, 300), (750, 400), (750, 500)),
    "co": ((0, 0), (2, 50), (4, 100), (14, 150), (24, 200), (36, 300), (48, 400), (48, 500)),
}


POLLUTANT_IAQI_CALCULATORS = {
    "PM2.5": ("pm25", pm25_to_iaqi),
    "PM10": ("pm10", pm10_to_iaqi),
    "O3": ("o3", o3_hourly_to_iaqi),
    "SO2": ("so2", so2_to_iaqi),
    "NO2": ("no2", no2_to_iaqi),
    "CO": ("co", co_to_iaqi),
}


def calculate_hourly_aqi(pollutants: dict[str, float | None]) -> int | None:
    iaqi_values = [
        calculator(pollutants.get(key))
        for key, calculator in (item for _, item in POLLUTANT_IAQI_CALCULATORS.items())
    ]
    valid_values = [value for value in iaqi_values if value is not None]
    return max(valid_values) if valid_values else None


def calculate_daily_aqi(pollutants: dict[str, float | None]) -> int | None:
    iaqi_values = [
        pm25_to_iaqi(pollutants.get("pm25")),
        pm10_to_iaqi(pollutants.get("pm10")),
        _linear_iaqi(pollutants.get("o3"), ((100, 50), (160, 100), (215, 150), (265, 200), (800, 300))),
        so2_to_iaqi(pollutants.get("so2")),
        no2_to_iaqi(pollutants.get("no2")),
        co_to_iaqi(pollutants.get("co")),
    ]
    valid_values = [value for value in iaqi_values if value is not None]
    return max(valid_values) if valid_values else None


def calculate_primary_pollutant(pollutants: dict[str, float | None], aqi: int | None) -> str | None:
    if aqi is None or aqi < 50:
        return None

    candidates: list[tuple[str, int]] = []
    for name, (key, calculator) in POLLUTANT_IAQI_CALCULATORS.items():
        value = calculator(pollutants.get(key))
        if value is not None:
            candidates.append((name, value))

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[1])[0]


def get_aqi_level(aqi: int | None) -> dict[str, Any]:
    if aqi is None:
        return {"value": 0, "name": "未知"}
    for index, (minimum, maximum, name) in enumerate(AQI_LEVELS, start=1):
        if minimum <= aqi <= maximum:
            return {"value": index, "name": name}
    return {"value": 6, "name": "严重污染"}


def iaqi_to_concentration(target_iaqi: float, pollutant_key: str) -> float | None:
    points = POLLUTANT_THRESHOLDS.get(pollutant_key)
    if not points:
        return None

    target_iaqi = max(0, min(500, target_iaqi))
    previous_concentration, previous_iaqi = points[0]
    for concentration, iaqi in points[1:]:
        if target_iaqi <= iaqi:
            if iaqi == previous_iaqi:
                value = concentration
            else:
                value = previous_concentration + (
                    (target_iaqi - previous_iaqi)
                    / (iaqi - previous_iaqi)
                    * (concentration - previous_concentration)
                )
            if pollutant_key == "co":
                value *= 1000
            return round(value, 3)
        previous_concentration = concentration
        previous_iaqi = iaqi

    concentration = points[-1][0]
    if pollutant_key == "co":
        concentration *= 1000
    return float(concentration)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def aggregate_daily_pollutants_from_hourly(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    pollutants_by_key: dict[str, list[float]] = {
        "pm25": [],
        "pm10": [],
        "o3": [],
        "so2": [],
        "no2": [],
        "co": [],
    }
    for row in rows:
        pollutants = row.get("pollutants") or {}
        for key in pollutants_by_key:
            value = pollutants.get(key)
            if value is not None:
                pollutants_by_key[key].append(float(value))

    o3_daily = None
    o3_values = pollutants_by_key["o3"]
    if len(o3_values) >= 8:
        o3_daily = round(max(sum(o3_values[index : index + 8]) / 8 for index in range(len(o3_values) - 7)), 1)

    return {
        "pm25": _average(pollutants_by_key["pm25"]),
        "pm10": _average(pollutants_by_key["pm10"]),
        "o3": o3_daily,
        "so2": _average(pollutants_by_key["so2"]),
        "no2": _average(pollutants_by_key["no2"]),
        "co": _average(pollutants_by_key["co"]),
    }


def calculate_pollutant_shifts_for_target_aqi(
    daily_pollutants: dict[str, float | None],
    target_aqi: int,
    original_aqi: int,
) -> dict[str, float]:
    aqi_shift = target_aqi - original_aqi
    daily_calculators = {
        "pm25": pm25_to_iaqi,
        "pm10": pm10_to_iaqi,
        "o3": lambda value: _linear_iaqi(value, ((100, 50), (160, 100), (215, 150), (265, 200), (800, 300))),
        "so2": so2_to_iaqi,
        "no2": no2_to_iaqi,
        "co": co_to_iaqi,
    }
    shifts: dict[str, float] = {}
    for key, calculator in daily_calculators.items():
        concentration = daily_pollutants.get(key)
        if concentration is None:
            shifts[key] = 0
            continue
        current_iaqi = calculator(concentration) or 0
        target_iaqi = max(0, min(500, current_iaqi + aqi_shift))
        new_concentration = iaqi_to_concentration(target_iaqi, key)
        shifts[key] = round(((new_concentration or concentration) - concentration), 3)
    return shifts


def _forecast_date(row: dict[str, Any]) -> str:
    return datetime.fromisoformat(row["forecast_time"]).date().isoformat()


def apply_daily_calibration(
    rows: list[dict[str, Any]],
    city_name: str,
    targets_by_city: dict[str, list[DailyForecastTarget]],
) -> list[dict[str, Any]]:
    targets = {target.forecast_date: target for target in targets_by_city.get(city_name, [])}
    rows_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_date.setdefault(_forecast_date(row), []).append(row)

    calibrated_rows: list[dict[str, Any]] = []
    for date_key, date_rows in rows_by_date.items():
        target = targets.get(date_key)
        daily_pollutants = aggregate_daily_pollutants_from_hourly(date_rows)
        original_daily_aqi = calculate_daily_aqi(daily_pollutants)
        need_shift = False
        target_daily_aqi = original_daily_aqi
        shift_reason = "无日预报目标范围"
        pollutant_shifts = {key: 0.0 for key in ("pm25", "pm10", "o3", "so2", "no2", "co")}

        if target and original_daily_aqi is not None:
            if original_daily_aqi < target.min_aqi:
                target_daily_aqi = round(original_daily_aqi + 0.9 * (target.min_aqi - original_daily_aqi))
                need_shift = True
                shift_reason = f"日AQI偏低（{original_daily_aqi} < {target.min_aqi}），向minAqi靠拢90%"
            elif original_daily_aqi > target.max_aqi:
                target_daily_aqi = round(original_daily_aqi - 0.9 * (original_daily_aqi - target.max_aqi))
                need_shift = True
                shift_reason = f"日AQI偏高（{original_daily_aqi} > {target.max_aqi}），向maxAqi靠拢90%"
            else:
                shift_reason = "日AQI在目标范围内，无需校准"

            if need_shift and target_daily_aqi is not None:
                pollutant_shifts = calculate_pollutant_shifts_for_target_aqi(
                    daily_pollutants,
                    target_daily_aqi,
                    original_daily_aqi,
                )

        for row in date_rows:
            raw_pollutants = dict(row.get("pollutants") or {})
            adjusted_pollutants = {
                key: (max(0, value + pollutant_shifts.get(key, 0)) if value is not None else None)
                for key, value in raw_pollutants.items()
            }
            calibrated_aqi = calculate_hourly_aqi(adjusted_pollutants)
            calibrated_rows.append(
                {
                    **row,
                    "aqi": calibrated_aqi,
                    "raw_aqi": row.get("aqi"),
                    "aqi_level": get_aqi_level(calibrated_aqi),
                    "primary_pollutant": calculate_primary_pollutant(adjusted_pollutants, calibrated_aqi),
                    "pollutants": adjusted_pollutants,
                    "raw_pollutants": raw_pollutants,
                    "daily_shift_value": (target_daily_aqi - original_daily_aqi) if need_shift and target_daily_aqi is not None and original_daily_aqi is not None else 0,
                    "shift_info": {
                        "date": date_key,
                        "target_min_aqi": target.min_aqi if target else None,
                        "target_max_aqi": target.max_aqi if target else None,
                        "original_daily_aqi": original_daily_aqi,
                        "target_daily_aqi": target_daily_aqi,
                        "need_shift": need_shift,
                        "reason": shift_reason,
                        "pollutant_shifts": pollutant_shifts,
                    },
                    "process_type": "calibrated",
                    "is_first_forecast": True,
                }
            )

    return sorted(calibrated_rows, key=lambda item: item["forecast_time"])


def apply_weighted_fusion_with_observation(
    rows: list[dict[str, Any]],
    observation: HourlyObservation | None,
    generated_at: datetime,
) -> list[dict[str, Any]]:
    if not rows or observation is None or observation.aqi is None:
        return rows

    fused_rows: list[dict[str, Any]] = []
    for row in rows:
        forecast_time = datetime.fromisoformat(row["forecast_time"])
        diff_hours = (forecast_time - generated_at).total_seconds() / 3600
        if diff_hours > 12:
            obs_weight = 0.0
        elif diff_hours <= 0:
            obs_weight = 0.7
        else:
            obs_weight = 0.7 * (0.5 ** (diff_hours / 3))
        obs_weight = max(0.0, min(1.0, obs_weight))
        forecast_weight = 1 - obs_weight

        forecast_pollutants = row.get("pollutants") or {}
        fused_pollutants: dict[str, float | None] = {}
        for key in ("pm25", "pm10", "o3", "so2", "no2", "co"):
            forecast_value = forecast_pollutants.get(key)
            obs_value = observation.pollutants.get(key)
            if forecast_value is not None and obs_value is not None:
                fused_value = forecast_value * forecast_weight + obs_value * obs_weight
            elif forecast_value is not None:
                fused_value = forecast_value
            elif obs_value is not None:
                fused_value = obs_value
            else:
                fused_value = None

            if fused_value is None:
                fused_pollutants[key] = None
            elif key == "co":
                fused_pollutants[key] = round(fused_value, 3)
            else:
                fused_pollutants[key] = round(fused_value, 1)

        fused_aqi = calculate_hourly_aqi(fused_pollutants)
        fused_rows.append(
            {
                **row,
                "aqi": fused_aqi if fused_aqi is not None else row.get("aqi"),
                "aqi_level": get_aqi_level(fused_aqi if fused_aqi is not None else row.get("aqi")),
                "primary_pollutant": calculate_primary_pollutant(fused_pollutants, fused_aqi),
                "pollutants": fused_pollutants,
                "fusion": {
                    "forecast_weight": round(forecast_weight, 2),
                    "observation_weight": round(obs_weight, 2),
                    "original_forecast_aqi": row.get("aqi"),
                    "observation_aqi": observation.aqi,
                    "observation_time": observation.time.isoformat(),
                    "diff_hours": round(diff_hours, 2),
                },
            }
        )

    return fused_rows


def _get_hourly_value(hourly: dict[str, list[Any]], key: str, index: int) -> float | None:
    values = hourly.get(key) or []
    if index >= len(values):
        return None
    value = values[index]
    if value is None:
        return None
    return float(value)


def parse_open_meteo_hourly_forecast(
    payload: dict[str, Any],
    city_key: str,
    city_name: str,
    generated_at: datetime,
    max_hours: int = 72,
) -> list[dict[str, Any]]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    rows: list[dict[str, Any]] = []

    for index, time_value in enumerate(times):
        forecast_time = datetime.fromisoformat(str(time_value))
        if forecast_time < generated_at:
            continue
        if len(rows) >= max_hours:
            break
        pollutants = {
            "pm25": _get_hourly_value(hourly, "pm2_5", index),
            "pm10": _get_hourly_value(hourly, "pm10", index),
            "o3": _get_hourly_value(hourly, "ozone", index),
            "so2": _get_hourly_value(hourly, "sulphur_dioxide", index),
            "no2": _get_hourly_value(hourly, "nitrogen_dioxide", index),
            "co": _get_hourly_value(hourly, "carbon_monoxide", index),
        }
        aqi = calculate_hourly_aqi(pollutants)
        rows.append(
            {
                "city_key": city_key,
                "city": city_name,
                "forecast_time": forecast_time.isoformat(),
                "generated_at": generated_at.isoformat(),
                "source": "open-meteo",
                "aqi": aqi,
                "aqi_level": get_aqi_level(aqi),
                "primary_pollutant": calculate_primary_pollutant(pollutants, aqi),
                "pollutants": pollutants,
            }
        )

    return rows


class OpenMeteoAirQualityForecastClient:
    def __init__(
        self,
        base_url: str = OPEN_METEO_AIR_QUALITY_URL,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
            }
        )

    def fetch_city(self, city: AirQualityForecastCity) -> dict[str, Any]:
        response = self.session.get(
            self.base_url,
            params={
                "latitude": city.lat,
                "longitude": city.lon,
                "hourly": ",".join(AIR_QUALITY_HOURLY_FIELDS),
                "timezone": "Asia/Shanghai",
                "forecast_days": 4,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


class SQLForecastSupplementalDataProvider:
    """Fetch daily forecast targets and latest city hourly observations from XcAiDb."""

    def __init__(self):
        self.sql_client = get_sql_server_client()

    def fetch_daily_targets(
        self,
        cities: dict[str, AirQualityForecastCity],
        generated_at: datetime,
    ) -> dict[str, list[DailyForecastTarget]]:
        city_codes = [city.city_code for city in cities.values()]
        placeholders = ",".join("?" for _ in city_codes)
        sql = f"""
        SELECT CityCode, cityname, DayTitle, MinAqi, MaxAqi, MaxPollution, TimePoint, UpdateDate, UpdateTime
        FROM WeatherForecast7Day
        WHERE CityCode IN ({placeholders})
          AND CAST(TimePoint AS DATE) >= CAST(? AS DATE)
          AND UpdateDate = (
              SELECT MAX(UpdateDate)
              FROM WeatherForecast7Day AS latest
              WHERE latest.CityCode = WeatherForecast7Day.CityCode
                AND CAST(latest.UpdateDate AS DATE) >= CAST(DATEADD(DAY, -1, ?) AS DATE)
          )
        ORDER BY CityCode, TimePoint ASC
        """
        params = city_codes + [generated_at.strftime("%Y-%m-%d"), generated_at.strftime("%Y-%m-%d %H:%M:%S")]

        conn = pyodbc.connect(self.sql_client.connection_string, timeout=30)
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)
            columns = [column[0] for column in cursor.description]
            targets: dict[str, list[DailyForecastTarget]] = {}
            for row in cursor.fetchall():
                record = dict(zip(columns, row))
                city_name = record.get("cityname") or next(
                    (city.name for city in cities.values() if city.city_code == str(record.get("CityCode"))),
                    str(record.get("CityCode")),
                )
                time_point = record.get("TimePoint")
                if hasattr(time_point, "date"):
                    forecast_date = time_point.date().isoformat()
                else:
                    forecast_date = str(time_point).split(" ")[0]
                targets.setdefault(city_name, []).append(
                    DailyForecastTarget(
                        city=city_name,
                        forecast_date=forecast_date,
                        min_aqi=int(record.get("MinAqi") or 0),
                        max_aqi=int(record.get("MaxAqi") or 0),
                        primary_pollutant=record.get("MaxPollution"),
                        update_time=str(record.get("UpdateTime") or record.get("UpdateDate") or ""),
                    )
                )
            return targets
        finally:
            cursor.close()
            conn.close()

    def fetch_latest_observations(
        self,
        cities: dict[str, AirQualityForecastCity],
        generated_at: datetime,
    ) -> dict[str, HourlyObservation]:
        start_time = (generated_at - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
        end_time = generated_at.strftime("%Y-%m-%d %H:%M:%S")
        observations: dict[str, HourlyObservation] = {}
        rows = self.sql_client.query(
            cities=[city.name for city in cities.values()],
            start_time=start_time,
            end_time=end_time,
            table="CityAQIPublishHistory",
        )
        rows.sort(key=lambda item: item.get("TimePoint") or datetime.min)

        for row in rows:
            aqi = row.get("AQI")
            if aqi is None or not (0 <= int(aqi) <= 500):
                continue
            city = row.get("Area")
            time_point = row.get("TimePoint")
            if isinstance(time_point, datetime):
                observation_time = time_point
            else:
                observation_time = datetime.fromisoformat(str(time_point))
            age_hours = (generated_at - observation_time).total_seconds() / 3600
            if age_hours < 0 or age_hours > 2:
                continue
            observations[city] = HourlyObservation(
                city=city,
                time=observation_time,
                aqi=int(aqi),
                pollutants={
                    "pm25": _optional_float(row.get("PM2_5")),
                    "pm10": _optional_float(row.get("PM10")),
                    "o3": _optional_float(row.get("O3")),
                    "so2": _optional_float(row.get("SO2")),
                    "no2": _optional_float(row.get("NO2")),
                    "co": _optional_float(row.get("CO")),
                },
            )
        return observations


class SQLForecastStorage:
    """Store calibrated/fused forecast rows in SQL Server."""

    table_name = "OpenMeteoAirQualityForecast72h"

    def __init__(self):
        self.sql_client = get_sql_server_client()

    def ensure_table(self, cursor: pyodbc.Cursor) -> None:
        cursor.execute(
            f"""
            IF OBJECT_ID(N'dbo.{self.table_name}', N'U') IS NULL
            BEGIN
                CREATE TABLE dbo.{self.table_name} (
                    id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    run_id NVARCHAR(32) NOT NULL,
                    generated_at DATETIME2 NOT NULL,
                    source NVARCHAR(64) NOT NULL,
                    process_type NVARCHAR(32) NOT NULL,
                    calibration_applied BIT NOT NULL,
                    city_key NVARCHAR(64) NOT NULL,
                    city_name NVARCHAR(64) NOT NULL,
                    city_code NVARCHAR(20) NOT NULL,
                    lat FLOAT NULL,
                    lon FLOAT NULL,
                    forecast_time DATETIME2 NOT NULL,
                    forecast_date DATE NOT NULL,
                    aqi INT NULL,
                    raw_aqi INT NULL,
                    aqi_level_value INT NULL,
                    aqi_level_name NVARCHAR(32) NULL,
                    primary_pollutant NVARCHAR(64) NULL,
                    pm25 FLOAT NULL,
                    pm10 FLOAT NULL,
                    o3 FLOAT NULL,
                    so2 FLOAT NULL,
                    no2 FLOAT NULL,
                    co FLOAT NULL,
                    raw_pm25 FLOAT NULL,
                    raw_pm10 FLOAT NULL,
                    raw_o3 FLOAT NULL,
                    raw_so2 FLOAT NULL,
                    raw_no2 FLOAT NULL,
                    raw_co FLOAT NULL,
                    daily_shift_value FLOAT NULL,
                    is_first_forecast BIT NOT NULL,
                    target_min_aqi INT NULL,
                    target_max_aqi INT NULL,
                    original_daily_aqi INT NULL,
                    target_daily_aqi INT NULL,
                    shift_reason NVARCHAR(500) NULL,
                    shift_info_json NVARCHAR(MAX) NULL,
                    fusion_json NVARCHAR(MAX) NULL,
                    row_json NVARCHAR(MAX) NULL,
                    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                    updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
                );
            END
            """
        )
        cursor.execute(
            f"""
            IF NOT EXISTS (
                SELECT 1
                FROM sys.indexes
                WHERE name = N'UX_{self.table_name}_CityTime'
                  AND object_id = OBJECT_ID(N'dbo.{self.table_name}')
            )
            BEGIN
                WITH ranked AS (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY city_code, forecast_time
                               ORDER BY generated_at DESC, id DESC
                           ) AS row_number
                    FROM dbo.{self.table_name}
                )
                DELETE FROM ranked WHERE row_number > 1;

                CREATE UNIQUE INDEX UX_{self.table_name}_CityTime
                ON dbo.{self.table_name} (city_code, forecast_time);
            END
            """
        )

    def save_forecast(
        self,
        *,
        run_id: str,
        generated_at: datetime,
        source: str,
        process_type: str,
        calibration_applied: bool,
        cities: dict[str, AirQualityForecastCity],
        city_results: dict[str, list[dict[str, Any]]],
    ) -> int:
        rows = []
        for city in cities.values():
            for row in city_results.get(city.key, []):
                pollutants = row.get("pollutants") or {}
                raw_pollutants = row.get("raw_pollutants") or {}
                aqi_level = row.get("aqi_level") or {}
                shift_info = row.get("shift_info") or {}
                forecast_time = datetime.fromisoformat(row["forecast_time"])
                rows.append(
                    (
                        run_id,
                        generated_at,
                        source,
                        process_type,
                        bool(calibration_applied),
                        city.key,
                        city.name,
                        city.city_code,
                        city.lat,
                        city.lon,
                        forecast_time,
                        forecast_time.date(),
                        row.get("aqi"),
                        row.get("raw_aqi"),
                        aqi_level.get("value"),
                        aqi_level.get("name"),
                        row.get("primary_pollutant"),
                        pollutants.get("pm25"),
                        pollutants.get("pm10"),
                        pollutants.get("o3"),
                        pollutants.get("so2"),
                        pollutants.get("no2"),
                        pollutants.get("co"),
                        raw_pollutants.get("pm25"),
                        raw_pollutants.get("pm10"),
                        raw_pollutants.get("o3"),
                        raw_pollutants.get("so2"),
                        raw_pollutants.get("no2"),
                        raw_pollutants.get("co"),
                        row.get("daily_shift_value"),
                        bool(row.get("is_first_forecast")),
                        shift_info.get("target_min_aqi"),
                        shift_info.get("target_max_aqi"),
                        shift_info.get("original_daily_aqi"),
                        shift_info.get("target_daily_aqi"),
                        shift_info.get("reason"),
                        _json_dumps(shift_info) if shift_info else None,
                        _json_dumps(row.get("fusion")) if row.get("fusion") else None,
                        _json_dumps(row),
                    )
                )

        if not rows:
            return 0

        columns = (
            "run_id",
            "generated_at",
            "source",
            "process_type",
            "calibration_applied",
            "city_key",
            "city_name",
            "city_code",
            "lat",
            "lon",
            "forecast_time",
            "forecast_date",
            "aqi",
            "raw_aqi",
            "aqi_level_value",
            "aqi_level_name",
            "primary_pollutant",
            "pm25",
            "pm10",
            "o3",
            "so2",
            "no2",
            "co",
            "raw_pm25",
            "raw_pm10",
            "raw_o3",
            "raw_so2",
            "raw_no2",
            "raw_co",
            "daily_shift_value",
            "is_first_forecast",
            "target_min_aqi",
            "target_max_aqi",
            "original_daily_aqi",
            "target_daily_aqi",
            "shift_reason",
            "shift_info_json",
            "fusion_json",
            "row_json",
        )
        source_select = ", ".join(f"? AS {column}" for column in columns)
        update_set = ",\n                ".join(
            f"target.{column} = src.{column}"
            for column in columns
            if column not in {"city_code", "forecast_time"}
        )
        insert_columns = ", ".join(columns)
        insert_values = ", ".join(f"src.{column}" for column in columns)
        merge_sql = f"""
        MERGE dbo.{self.table_name} AS target
        USING (SELECT {source_select}) AS src
        ON target.city_code = src.city_code
           AND target.forecast_time = src.forecast_time
        WHEN MATCHED THEN
            UPDATE SET
                {update_set},
                target.updated_at = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN
            INSERT (
                {insert_columns}
            )
            VALUES (
                {insert_values}
            );
        """

        conn = pyodbc.connect(self.sql_client.connection_string, timeout=30)
        cursor = conn.cursor()
        try:
            self.ensure_table(cursor)
            cursor.fast_executemany = True
            cursor.executemany(merge_sql, rows)
            conn.commit()
            return len(rows)
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def is_first_forecast_time(generated_at: datetime) -> bool:
    return generated_at.hour == 8


class OpenMeteoAirQualityForecastFetcher(DataFetcher):
    """Fetch future 72-hour air quality forecasts for Yuncheng and Xuchang."""

    def __init__(
        self,
        client: OpenMeteoAirQualityForecastClient | None = None,
        data_provider: SQLForecastSupplementalDataProvider | None = None,
        storage: SQLForecastStorage | None = None,
        cities: dict[str, AirQualityForecastCity] | None = None,
        generated_at_factory: Callable[[], datetime] = datetime.now,
    ):
        super().__init__(
            name="open_meteo_air_quality_forecast_fetcher",
            description="运城市和许昌市未来72小时空气质量预报抓取",
            schedule="18 * * * *",
            version="1.0.0",
        )
        self.client = client or OpenMeteoAirQualityForecastClient()
        self.data_provider = data_provider or SQLForecastSupplementalDataProvider()
        self.storage = storage or SQLForecastStorage()
        self.cities = cities or AIR_QUALITY_FORECAST_CITIES
        self.generated_at_factory = generated_at_factory

    async def fetch_and_store(self) -> dict[str, Any]:
        generated_at = self.generated_at_factory().replace(microsecond=0)
        run_id = generated_at.strftime("%Y%m%d%H%M%S")
        city_results: dict[str, list[dict[str, Any]]] = {}
        failed_cities: dict[str, str] = {}
        daily_targets: dict[str, list[DailyForecastTarget]] = {}
        observations: dict[str, HourlyObservation] = {}
        process_type = "calibrated" if is_first_forecast_time(generated_at) else "update"

        try:
            daily_targets = self.data_provider.fetch_daily_targets(self.cities, generated_at)
        except Exception as exc:
            logger.warning("open_meteo_air_quality_daily_targets_fetch_failed", error=str(exc))

        try:
            observations = self.data_provider.fetch_latest_observations(self.cities, generated_at)
        except Exception as exc:
            logger.warning("open_meteo_air_quality_observations_fetch_failed", error=str(exc))

        for city in self.cities.values():
            try:
                payload = self.client.fetch_city(city)
                rows = parse_open_meteo_hourly_forecast(
                    payload=payload,
                    city_key=city.key,
                    city_name=city.name,
                    generated_at=generated_at,
                    max_hours=72,
                )
                rows = [
                    {
                        **row,
                        "raw_aqi": row.get("aqi"),
                        "raw_pollutants": dict(row.get("pollutants") or {}),
                        "daily_shift_value": 0,
                        "process_type": process_type,
                        "is_first_forecast": is_first_forecast_time(generated_at),
                    }
                    for row in rows
                ]
                if is_first_forecast_time(generated_at):
                    rows = apply_daily_calibration(rows, city.name, daily_targets)
                rows = apply_weighted_fusion_with_observation(
                    rows,
                    observations.get(city.name),
                    generated_at=generated_at,
                )
                city_results[city.key] = rows
            except Exception as exc:
                failed_cities[city.key] = str(exc)
                logger.warning(
                    "open_meteo_air_quality_city_fetch_failed",
                    city=city.name,
                    error=str(exc),
                )

        if not city_results:
            raise RuntimeError("All Open-Meteo air quality forecast city fetches failed")

        forecast_hours = sum(len(records) for records in city_results.values())
        saved_rows = self.storage.save_forecast(
            run_id=run_id,
            generated_at=generated_at,
            source="open-meteo",
            process_type=process_type,
            calibration_applied=is_first_forecast_time(generated_at),
            cities=self.cities,
            city_results=city_results,
        )
        logger.info(
            "open_meteo_air_quality_forecast_fetch_complete",
            cities=len(city_results),
            failed_cities=len(failed_cities),
            forecast_hours=forecast_hours,
            saved_rows=saved_rows,
            process_type=process_type,
            table=self.storage.table_name,
            run_id=run_id,
        )

        return {
            "run_id": run_id,
            "cities": len(city_results),
            "failed_cities": len(failed_cities),
            "forecast_hours": forecast_hours,
            "saved_rows": saved_rows,
            "table": self.storage.table_name,
        }

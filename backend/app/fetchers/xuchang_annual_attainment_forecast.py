"""Annual Xuchang attainment prediction from year-to-date and historical seasons."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

import pyodbc
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.xuchang_daily_attainment_forecast import XUCHANG_CITY, XUCHANG_CITY_CODE
from app.fetchers.xuchang_attainment_outputs import prediction_output_path, write_json
from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client
from app.utils.percentile_calculator import calculate_percentile

logger = structlog.get_logger()

PM25_ANNUAL_LIMIT = 30.0
O3_8H_P90_LIMIT = 160.0
AQI_ATTAINMENT_LIMIT = 100
STANDARD_VERSION = "GB 3095-2026 transition limits (2026-2030)"
HISTORICAL_SCENARIO_COUNT = 5
MINIMUM_SCENARIO_COUNT = 3


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _range(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {"lower": round(min(values), 1), "upper": round(max(values), 1)}


def _remaining_start(year: int, cutoff_date: date) -> date:
    try:
        matching_date = date(year, cutoff_date.month, cutoff_date.day)
    except ValueError:  # February 29 in a non-leap historical year.
        matching_date = date(year, 2, 28)
    return matching_date + timedelta(days=1)


def _daily_values(rows: list[dict[str, Any]]) -> dict[date, dict[str, float | None]]:
    values: dict[date, dict[str, float | None]] = {}
    for row in rows:
        record_date = _as_date(row.get("TimePoint") or row.get("date"))
        if record_date is None:
            continue
        values[record_date] = {
            "pm25": _as_float(row.get("PM2_5_24h") if "PM2_5_24h" in row else row.get("pm25")),
            "o3_8h": _as_float(row.get("O3_8h_24h") if "O3_8h_24h" in row else row.get("o3_8h")),
            "aqi": _as_float(row.get("AQI") if "AQI" in row else row.get("aqi")),
        }
    return values


def _series(records: dict[date, dict[str, float | None]], key: str) -> list[float]:
    return [record[key] for _, record in sorted(records.items()) if record[key] is not None]


@dataclass(frozen=True)
class AnnualAttainmentPrediction:
    calculated_at: datetime
    cutoff_date: date
    current_valid_days: int
    scenarios: list[dict[str, Any]]

    def _range_for(self, key: str) -> dict[str, float] | None:
        return _range([scenario[key] for scenario in self.scenarios])

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": XUCHANG_CITY,
            "city_code": XUCHANG_CITY_CODE,
            "calculated_at": self.calculated_at.isoformat(),
            "forecast_year": self.cutoff_date.year,
            "cutoff_date": self.cutoff_date.isoformat(),
            "current_valid_days": self.current_valid_days,
            "historical_years": [scenario["historical_year"] for scenario in self.scenarios],
            "standard_version": STANDARD_VERSION,
            "targets": {
                "pm25_annual_average": PM25_ANNUAL_LIMIT,
                "o3_8h_p90": O3_8H_P90_LIMIT,
                "aqi_daily_attainment": f"AQI <= {AQI_ATTAINMENT_LIMIT}",
            },
            "prediction_ranges": {
                "pm25_annual_average": self._range_for("pm25_annual_average"),
                "o3_8h_p90": self._range_for("o3_8h_p90"),
                "aqi_attainment_days": self._range_for("aqi_attainment_days"),
                "aqi_attainment_rate": self._range_for("aqi_attainment_rate"),
            },
            "scenarios": self.scenarios,
        }


def calculate_annual_attainment_prediction(
    *,
    calculated_at: datetime,
    cutoff_date: date,
    current_rows: list[dict[str, Any]],
    historical_rows_by_year: dict[int, list[dict[str, Any]]],
) -> AnnualAttainmentPrediction:
    """Build one annual scenario per historical remaining-season data set."""
    current = {day: values for day, values in _daily_values(current_rows).items() if day <= cutoff_date}
    current_pm25 = _series(current, "pm25")
    current_o3 = _series(current, "o3_8h")
    current_aqi = _series(current, "aqi")
    if not current_pm25 or not current_o3 or not current_aqi:
        raise ValueError("许昌年度达标预测缺少当前年度完整日数据")

    scenarios: list[dict[str, Any]] = []
    for historical_year in sorted(historical_rows_by_year):
        historical = _daily_values(historical_rows_by_year[historical_year])
        historical_pm25 = _series(historical, "pm25")
        historical_o3 = _series(historical, "o3_8h")
        historical_aqi = _series(historical, "aqi")
        if not historical_pm25 or not historical_o3 or not historical_aqi:
            logger.warning(
                "xuchang_annual_attainment_scenario_skipped",
                historical_year=historical_year,
                reason="missing_remaining_season_data",
            )
            continue

        pm25_value = _mean(current_pm25 + historical_pm25)
        o3_value = calculate_percentile(current_o3 + historical_o3, 90)
        aqi_attainment_days = sum(value <= AQI_ATTAINMENT_LIMIT for value in current_aqi + historical_aqi)
        aqi_valid_days = len(current_aqi) + len(historical_aqi)
        scenarios.append({
            "historical_year": historical_year,
            "current_days": len(current_aqi),
            "historical_remaining_days": len(historical_aqi),
            "pm25_annual_average": pm25_value,
            "pm25_attainment": pm25_value is not None and pm25_value <= PM25_ANNUAL_LIMIT,
            "o3_8h_p90": round(float(o3_value), 1) if o3_value is not None else None,
            "o3_8h_attainment": o3_value is not None and o3_value <= O3_8H_P90_LIMIT,
            "aqi_attainment_days": aqi_attainment_days,
            "aqi_valid_days": aqi_valid_days,
            "aqi_attainment_rate": round(aqi_attainment_days / aqi_valid_days * 100, 1),
        })

    if len(scenarios) < MINIMUM_SCENARIO_COUNT:
        raise ValueError(f"历史同季节有效情景不足{MINIMUM_SCENARIO_COUNT}个")
    return AnnualAttainmentPrediction(calculated_at, cutoff_date, len(current_aqi), scenarios)


class XuchangAnnualAttainmentStorage:
    table_name = "XuchangAnnualAttainmentPrediction"

    def __init__(self) -> None:
        self.sql_client = get_sql_server_client()

    def save(self, prediction: AnnualAttainmentPrediction) -> None:
        payload = prediction.to_dict()
        ranges = payload["prediction_ranges"]
        values = [
            *ranges["pm25_annual_average"].values(),
            *ranges["o3_8h_p90"].values(),
            *ranges["aqi_attainment_days"].values(),
            *ranges["aqi_attainment_rate"].values(),
        ]
        result_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        conn = pyodbc.connect(self.sql_client.connection_string, timeout=30)
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                IF OBJECT_ID(N'dbo.{self.table_name}', N'U') IS NULL
                CREATE TABLE dbo.{self.table_name} (
                    id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    city_code NVARCHAR(20) NOT NULL, forecast_year INT NOT NULL,
                    cutoff_date DATE NOT NULL, calculated_at DATETIME2 NOT NULL,
                    pm25_lower FLOAT NULL, pm25_upper FLOAT NULL,
                    o3_8h_lower FLOAT NULL, o3_8h_upper FLOAT NULL,
                    aqi_attainment_days_lower FLOAT NULL, aqi_attainment_days_upper FLOAT NULL,
                    aqi_attainment_rate_lower FLOAT NULL, aqi_attainment_rate_upper FLOAT NULL,
                    result_json NVARCHAR(MAX) NOT NULL,
                    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
                );
                IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_{self.table_name}_CityCutoff'
                    AND object_id = OBJECT_ID(N'dbo.{self.table_name}'))
                CREATE UNIQUE INDEX UX_{self.table_name}_CityCutoff ON dbo.{self.table_name} (city_code, cutoff_date);
            """)
            cursor.execute(f"""
                MERGE dbo.{self.table_name} AS target
                USING (SELECT ? AS city_code, ? AS cutoff_date) AS source
                ON target.city_code = source.city_code AND target.cutoff_date = source.cutoff_date
                WHEN MATCHED THEN UPDATE SET forecast_year=?, calculated_at=?,
                    pm25_lower=?, pm25_upper=?, o3_8h_lower=?, o3_8h_upper=?,
                    aqi_attainment_days_lower=?, aqi_attainment_days_upper=?,
                    aqi_attainment_rate_lower=?, aqi_attainment_rate_upper=?, result_json=?
                WHEN NOT MATCHED THEN INSERT (
                    city_code, forecast_year, cutoff_date, calculated_at, pm25_lower, pm25_upper,
                    o3_8h_lower, o3_8h_upper, aqi_attainment_days_lower, aqi_attainment_days_upper,
                    aqi_attainment_rate_lower, aqi_attainment_rate_upper, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
                XUCHANG_CITY_CODE, prediction.cutoff_date, prediction.cutoff_date.year, prediction.calculated_at,
                *values, result_json,
                XUCHANG_CITY_CODE, prediction.cutoff_date.year, prediction.cutoff_date, prediction.calculated_at,
                *values, result_json,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()


class XuchangAnnualAttainmentForecastFetcher(DataFetcher):
    """Generate monthly annual-attainment prediction intervals for Xuchang."""

    def __init__(
        self,
        storage: XuchangAnnualAttainmentStorage | None = None,
        now_factory: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__(
            name="xuchang_annual_attainment_forecast_fetcher",
            description="许昌市年度达标预测（PM2.5、O3_8H、AQI达标天数）",
            schedule="35 6 1 * *",
            version="1.0.0",
        )
        self.sql_client = get_sql_server_client()
        self.storage = storage or XuchangAnnualAttainmentStorage()
        self.now_factory = now_factory

    def _fetch_rows(self, start: date, end: date) -> list[dict[str, Any]]:
        return self.sql_client.query(
            cities=[XUCHANG_CITY],
            start_time=f"{start.isoformat()} 00:00:00",
            end_time=f"{end.isoformat()} 23:59:59",
            table="CityDayAQIPublishHistory",
        )

    async def fetch_and_store(self) -> dict[str, Any]:
        calculated_at = self.now_factory().replace(microsecond=0)
        latest_complete_date = calculated_at.date() - timedelta(days=1)
        current_rows = self._fetch_rows(date(latest_complete_date.year, 1, 1), latest_complete_date)
        complete_dates = [
            day for day, values in _daily_values(current_rows).items()
            if day <= latest_complete_date and all(values[key] is not None for key in ("pm25", "o3_8h", "aqi"))
        ]
        if not complete_dates:
            raise ValueError("未找到许昌市可用于年度预测的完整日数据")
        cutoff_date = max(complete_dates)
        historical_rows_by_year = {
            year: self._fetch_rows(_remaining_start(year, cutoff_date), date(year, 12, 31))
            for year in range(cutoff_date.year - HISTORICAL_SCENARIO_COUNT, cutoff_date.year)
        }
        prediction = calculate_annual_attainment_prediction(
            calculated_at=calculated_at,
            cutoff_date=cutoff_date,
            current_rows=current_rows,
            historical_rows_by_year=historical_rows_by_year,
        )
        self.storage.save(prediction)
        payload = prediction.to_dict()
        write_json(prediction_output_path("annual"), payload)
        logger.info("xuchang_annual_attainment_prediction_completed", **payload)
        return payload

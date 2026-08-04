"""Hourly Xuchang daily-attainment prediction based on observations and forecasts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Callable

import pyodbc
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.xuchang_attainment_outputs import (
    daily_notification_state_path,
    prediction_output_path,
    read_json,
    write_json,
)
from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client

logger = structlog.get_logger()

XUCHANG_CITY = "许昌市"
XUCHANG_CITY_CODE = "411000"
PM25_DAILY_LIMIT = 75.0
O3_8H_DAILY_LIMIT = 160.0
TURNAROUND_OPPORTUNITY_DELTA = 5.0


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_hour(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(minute=0, second=0, microsecond=0)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value)).replace(minute=0, second=0, microsecond=0)
    except ValueError:
        return None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _max_o3_8h(values: list[float | None]) -> float | None:
    windows = [
        values[index : index + 8]
        for index in range(len(values) - 7)
        if all(value is not None for value in values[index : index + 8])
    ]
    if not windows:
        return None
    return round(max(sum(window) / 8 for window in windows), 1)


@dataclass(frozen=True)
class DailyAttainmentResult:
    analysis_time: datetime
    target_date: date
    observed_hours: int
    forecast_hours: int
    missing_hours: int
    pm25_daily_average: float | None
    o3_8h_maximum: float | None
    pm25_exceeded: bool
    o3_8h_exceeded: bool
    hourly_rows: list[dict[str, Any]]

    @property
    def exceeded_pollutants(self) -> list[str]:
        return [
            pollutant
            for pollutant, exceeded in (("PM2.5", self.pm25_exceeded), ("O3_8H", self.o3_8h_exceeded))
            if exceeded
        ]

    @property
    def is_attainment_predicted(self) -> bool:
        return not self.exceeded_pollutants

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_time": self.analysis_time.isoformat(),
            "target_date": self.target_date.isoformat(),
            "city": XUCHANG_CITY,
            "city_code": XUCHANG_CITY_CODE,
            "observed_hours": self.observed_hours,
            "forecast_hours": self.forecast_hours,
            "missing_hours": self.missing_hours,
            "pm25_daily_average": self.pm25_daily_average,
            "pm25_limit": PM25_DAILY_LIMIT,
            "pm25_exceeded": self.pm25_exceeded,
            "o3_8h_maximum": self.o3_8h_maximum,
            "o3_8h_limit": O3_8H_DAILY_LIMIT,
            "o3_8h_exceeded": self.o3_8h_exceeded,
            "exceeded_pollutants": self.exceeded_pollutants,
            "is_attainment_predicted": self.is_attainment_predicted,
            "hourly_rows": self.hourly_rows,
        }


@dataclass(frozen=True)
class ExceedanceNotification:
    pollutant: str
    reason: str
    predicted_value: float
    limit: float
    previous_predicted_value: float | None


def decide_exceedance_notifications(
    result: DailyAttainmentResult,
    state: dict[str, Any],
) -> tuple[list[ExceedanceNotification], dict[str, Any]]:
    """Alert on a day's first exceedance, then only after a material improvement."""
    previous = state.get("pollutants", {})
    next_pollutants: dict[str, dict[str, Any]] = {}
    notifications: list[ExceedanceNotification] = []
    values = {
        "PM2.5": (result.pm25_daily_average, PM25_DAILY_LIMIT, result.pm25_exceeded),
        "O3_8H": (result.o3_8h_maximum, O3_8H_DAILY_LIMIT, result.o3_8h_exceeded),
    }
    for pollutant, (value, limit, exceeded) in values.items():
        if value is None or not exceeded:
            continue
        old = previous.get(pollutant, {})
        old_value = _as_float(old.get("predicted_value"))
        same_day = old.get("target_date") == result.target_date.isoformat()
        reason = None
        if not same_day:
            reason = "first_exceedance"
        elif old_value is not None and old_value - value >= TURNAROUND_OPPORTUNITY_DELTA:
            reason = "turnaround_opportunity"
        if reason:
            notifications.append(ExceedanceNotification(
                pollutant=pollutant,
                reason=reason,
                predicted_value=value,
                limit=limit,
                previous_predicted_value=old_value if same_day else None,
            ))
        next_pollutants[pollutant] = {
            "target_date": result.target_date.isoformat(),
            "predicted_value": value,
            "limit": limit,
        }
    return notifications, {"pollutants": next_pollutants}


def calculate_daily_attainment_prediction(
    *,
    analysis_time: datetime,
    observations: list[dict[str, Any]],
    forecasts: list[dict[str, Any]],
) -> DailyAttainmentResult:
    """Fuse same-day hourly observations and forecasts into one daily prediction."""
    analysis_time = analysis_time.replace(minute=0, second=0, microsecond=0)
    target_date = analysis_time.date()
    by_hour: dict[datetime, dict[str, Any]] = {}

    for row in forecasts:
        hour = _as_hour(row.get("forecast_time") or row.get("time"))
        if hour and hour.date() == target_date:
            by_hour[hour] = {
                "pm25": _as_float(row.get("pm25") if "pm25" in row else row.get("PM2_5")),
                "o3": _as_float(row.get("o3") if "o3" in row else row.get("O3")),
                "source": "forecast",
            }

    # Observations are authoritative only through the last completed hour.
    for row in observations:
        hour = _as_hour(row.get("TimePoint") or row.get("time"))
        if hour and hour.date() == target_date and hour <= analysis_time:
            by_hour[hour] = {
                "pm25": _as_float(row.get("PM2_5") if "PM2_5" in row else row.get("pm25")),
                "o3": _as_float(row.get("O3") if "O3" in row else row.get("o3")),
                "source": "observation",
            }

    hourly_rows: list[dict[str, Any]] = []
    for hour_index in range(24):
        hour = datetime.combine(target_date, time(hour_index))
        value = by_hour.get(hour, {})
        hourly_rows.append(
            {
                "time": hour.isoformat(),
                "pm25": value.get("pm25"),
                "o3": value.get("o3"),
                "source": value.get("source", "missing"),
            }
        )

    observed_hours = sum(row["source"] == "observation" for row in hourly_rows)
    forecast_hours = sum(row["source"] == "forecast" for row in hourly_rows)
    missing_hours = 24 - observed_hours - forecast_hours
    pm25_daily_average = _mean([row["pm25"] for row in hourly_rows if row["pm25"] is not None])
    o3_8h_maximum = _max_o3_8h([row["o3"] for row in hourly_rows])
    return DailyAttainmentResult(
        analysis_time=analysis_time,
        target_date=target_date,
        observed_hours=observed_hours,
        forecast_hours=forecast_hours,
        missing_hours=missing_hours,
        pm25_daily_average=pm25_daily_average,
        o3_8h_maximum=o3_8h_maximum,
        pm25_exceeded=pm25_daily_average is not None and pm25_daily_average > PM25_DAILY_LIMIT,
        o3_8h_exceeded=o3_8h_maximum is not None and o3_8h_maximum > O3_8H_DAILY_LIMIT,
        hourly_rows=hourly_rows,
    )


class XuchangDailyAttainmentStorage:
    table_name = "XuchangDailyAttainmentPrediction"

    def __init__(self) -> None:
        self.sql_client = get_sql_server_client()

    def ensure_table(self, cursor: pyodbc.Cursor) -> None:
        cursor.execute(
            f"""
            IF OBJECT_ID(N'dbo.{self.table_name}', N'U') IS NULL
            CREATE TABLE dbo.{self.table_name} (
                id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                analysis_time DATETIME2 NOT NULL,
                target_date DATE NOT NULL,
                city_code NVARCHAR(20) NOT NULL,
                observed_hours INT NOT NULL,
                forecast_hours INT NOT NULL,
                missing_hours INT NOT NULL,
                pm25_daily_average FLOAT NULL,
                pm25_limit FLOAT NOT NULL,
                pm25_exceeded BIT NOT NULL,
                o3_8h_maximum FLOAT NULL,
                o3_8h_limit FLOAT NOT NULL,
                o3_8h_exceeded BIT NOT NULL,
                is_attainment_predicted BIT NOT NULL,
                result_json NVARCHAR(MAX) NOT NULL,
                created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
            );
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_{self.table_name}_CityAnalysisTime'
                AND object_id = OBJECT_ID(N'dbo.{self.table_name}'))
            CREATE UNIQUE INDEX UX_{self.table_name}_CityAnalysisTime
                ON dbo.{self.table_name} (city_code, analysis_time);
            """
        )

    def save(self, result: DailyAttainmentResult) -> None:
        payload = result.to_dict()
        conn = pyodbc.connect(self.sql_client.connection_string, timeout=30)
        cursor = conn.cursor()
        try:
            self.ensure_table(cursor)
            cursor.execute(
                f"""
                MERGE dbo.{self.table_name} AS target
                USING (SELECT ? AS city_code, ? AS analysis_time) AS source
                ON target.city_code = source.city_code AND target.analysis_time = source.analysis_time
                WHEN MATCHED THEN UPDATE SET
                    target_date=?, observed_hours=?, forecast_hours=?, missing_hours=?,
                    pm25_daily_average=?, pm25_limit=?, pm25_exceeded=?,
                    o3_8h_maximum=?, o3_8h_limit=?, o3_8h_exceeded=?,
                    is_attainment_predicted=?, result_json=?
                WHEN NOT MATCHED THEN INSERT (
                    analysis_time, target_date, city_code, observed_hours, forecast_hours, missing_hours,
                    pm25_daily_average, pm25_limit, pm25_exceeded, o3_8h_maximum, o3_8h_limit,
                    o3_8h_exceeded, is_attainment_predicted, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                XUCHANG_CITY_CODE, result.analysis_time,
                result.target_date, result.observed_hours, result.forecast_hours, result.missing_hours,
                result.pm25_daily_average, PM25_DAILY_LIMIT, result.pm25_exceeded,
                result.o3_8h_maximum, O3_8H_DAILY_LIMIT, result.o3_8h_exceeded,
                result.is_attainment_predicted, json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                result.analysis_time, result.target_date, XUCHANG_CITY_CODE,
                result.observed_hours, result.forecast_hours, result.missing_hours,
                result.pm25_daily_average, PM25_DAILY_LIMIT, result.pm25_exceeded,
                result.o3_8h_maximum, O3_8H_DAILY_LIMIT, result.o3_8h_exceeded,
                result.is_attainment_predicted, json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()


class XuchangDailyAttainmentForecastFetcher(DataFetcher):
    """Calculate and store Xuchang's daily PM2.5/O3 attainment prediction hourly."""

    def __init__(
        self,
        storage: XuchangDailyAttainmentStorage | None = None,
        now_factory: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__(
            name="xuchang_daily_attainment_forecast_fetcher",
            description="许昌市日达标预测分析（PM2.5、臭氧8小时平均）",
            schedule="25 * * * *",
            version="1.0.0",
        )
        self.sql_client = get_sql_server_client()
        self.storage = storage or XuchangDailyAttainmentStorage()
        self.now_factory = now_factory

    def _fetch_inputs(self, analysis_time: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        day_start = datetime.combine(analysis_time.date(), time.min)
        day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
        observations = self.sql_client.query(
            cities=[XUCHANG_CITY],
            start_time=day_start.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=min(analysis_time, day_end).strftime("%Y-%m-%d %H:%M:%S"),
            table="CityAQIPublishHistory",
        )
        conn = pyodbc.connect(self.sql_client.connection_string, timeout=30)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT forecast_time, pm25, o3
                FROM dbo.OpenMeteoAirQualityForecast72h
                WHERE city_key = ? AND forecast_time >= ? AND forecast_time <= ?
                ORDER BY forecast_time ASC
                """,
                "xuchang", day_start, day_end,
            )
            columns = [column[0] for column in cursor.description]
            forecasts = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return observations, forecasts
        finally:
            cursor.close()
            conn.close()

    async def fetch_and_store(self) -> dict[str, Any]:
        analysis_time = self.now_factory().replace(minute=0, second=0, microsecond=0)
        observations, forecasts = self._fetch_inputs(analysis_time)
        result = calculate_daily_attainment_prediction(
            analysis_time=analysis_time,
            observations=observations,
            forecasts=forecasts,
        )
        self.storage.save(result)
        payload = result.to_dict()
        write_json(prediction_output_path("daily"), payload)
        notification_state = read_json(daily_notification_state_path())
        notifications, next_state = decide_exceedance_notifications(result, notification_state)
        write_json(daily_notification_state_path(), next_state)
        if notifications:
            from app.scheduled_tasks import get_scheduled_task_service
            from app.scheduled_tasks.models.event import TaskEvent

            service = get_scheduled_task_service()
            for notification in notifications:
                await service.publish_event(TaskEvent(
                    event_id=f"xuchang-daily-attainment-{analysis_time:%Y%m%d%H}-{notification.pollutant.lower().replace('.', '').replace('_', '')}",
                    event_type="xuchang.daily_attainment.predicted_exceedance",
                    occurred_at=analysis_time,
                    attributes={
                        "city": XUCHANG_CITY,
                        "target_date": result.target_date.isoformat(),
                        "target_pollutant": notification.pollutant,
                        "is_attainment_predicted": False,
                        "notification_reason": notification.reason,
                        "has_turnaround_opportunity": notification.reason == "turnaround_opportunity",
                        "predicted_value": notification.predicted_value,
                        "limit": notification.limit,
                        "previous_predicted_value": notification.previous_predicted_value,
                    },
                    payload=payload,
                ))
        logger.info("xuchang_daily_attainment_prediction_completed", **payload)
        return payload

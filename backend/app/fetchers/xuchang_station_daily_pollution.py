"""Confirm prior-day pollution from published station-day data."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pyodbc
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.xcai_station_sql import xcai_connection_string
from app.scenarios.xuchang_transport_escalation import XuchangTransportEscalationService
from app.scheduled_tasks.models import TaskEvent

logger = structlog.get_logger()
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
CONFIRMED_EVENT_TYPE = "xuchang.station_daily_pollution.confirmed"
REQUESTED_EVENT_TYPE = "xuchang.station_daily_source_analysis.requested"
PM25_DAILY_LIMIT = 75.0
O3_8H_DAILY_LIMIT = 160.0


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def evaluate_station_daily_pollution(
    rows: Iterable[dict[str, Any]], *, target_date: date
) -> dict[str, Any]:
    """Evaluate platform-published PM2.5 and O3-8h station-day values."""
    rows_by_station: dict[str, dict[str, Any]] = {}
    for row in rows:
        data_time = row.get("data_time")
        if not isinstance(data_time, datetime) or data_time.date() != target_date:
            continue
        if row.get("station_id"):
            rows_by_station[str(row["station_id"])] = row

    evaluations = []
    events = []
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
        for pollutant, metric_key, observed_indicator in (
            ("PM2.5", "pm25", "PM2.5日均浓度"),
            ("O3", "o3_8h", "O3日最大8小时滑动平均"),
        ):
            metric = evaluation[metric_key]
            if not metric["exceeded"] or evaluation["lat"] is None or evaluation["lon"] is None:
                continue
            event_id = (
                f"xuchang-station-daily-pollution-{target_date:%Y%m%d}-"
                f"{station_id}-{pollutant.lower().replace('.', '')}"
            )
            events.append({
                "event_id": event_id,
                "event_type": CONFIRMED_EVENT_TYPE,
                "occurred_at": datetime.combine(
                    target_date + timedelta(days=1), time.min, tzinfo=TZ_SHANGHAI
                ).isoformat(),
                "status": "confirmed",
                "city": "许昌市",
                "station_id": station_id,
                "station_name": evaluation["station_name"],
                "lat": evaluation["lat"],
                "lon": evaluation["lon"],
                "target_date": target_date.isoformat(),
                "target_pollutant": pollutant,
                "observed_indicator": observed_indicator,
                "daily_value": metric["daily_value"],
                "limit": metric["limit"],
                "source_granularity": "station_day",
                "source_table": "dbo.dat_station_day",
                "trigger": "confirmed_station_daily_exceedance",
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
    return {"target_date": target_date.isoformat(), "evaluations": evaluations, "events": events}


class XuchangStationDailyPollutionFetcher(DataFetcher):
    """Read the prior day's platform-published station-day evaluation once."""

    def __init__(
        self,
        *,
        analysis_service: XuchangTransportEscalationService | None = None,
        now_factory: Callable[[], datetime] = lambda: datetime.now(TZ_SHANGHAI),
    ) -> None:
        super().__init__(
            name="xuchang_station_daily_pollution_fetcher",
            description="许昌站点日污染超标确认与场景二任务触发",
            schedule="5 2 * * *",
            version="2.0.0",
        )
        self.analysis_service = analysis_service or XuchangTransportEscalationService()
        self.now_factory = now_factory

    def load_rows(self, target_date: date) -> list[dict[str, Any]]:
        start = datetime.combine(target_date, time.min)
        end = start + timedelta(days=1)
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT station_id, name, lon, lat, pm25, O38h AS o3_8h, data_time
                FROM dbo.dat_station_day
                WHERE city_area_code = ? AND data_time >= ? AND data_time < ?
                ORDER BY station_id, data_time
                """,
                ["411000", start, end],
            )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        finally:
            connection.close()

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory()
        target_date = now.astimezone(TZ_SHANGHAI).date() - timedelta(days=1)
        result = evaluate_station_daily_pollution(self.load_rows(target_date), target_date=target_date)
        if result["events"]:
            from app.scheduled_tasks import get_scheduled_task_service

            task_service = get_scheduled_task_service()
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

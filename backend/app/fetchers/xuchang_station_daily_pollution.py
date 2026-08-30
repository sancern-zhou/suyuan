"""Build deterministic yesterday-hour pollution review evidence for Xuchang."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
from statistics import median
from statistics import pstdev
from typing import Any
from zoneinfo import ZoneInfo

import pyodbc
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.xcai_station_sql import xcai_connection_string
from app.scenarios.xuchang_transport_escalation import XuchangTransportEscalationService
from app.scheduled_tasks.models import TaskEvent
from app.utils.path_config import format_agent_path, get_data_registry

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


def calculate_pollutant_source_features(rows: list[dict[str, Any]], station_id: str) -> dict[str, Any]:
    """Calculate the composition-based source type shown in the business rule image."""
    samples = []
    for row in rows:
        if str(row.get("station_id") or "") != station_id:
            continue
        pm10, pm25 = _number(row.get("pm10")), _number(row.get("pm25"))
        so2, no2, co = (_number(row.get(field)) for field in ("so2", "no2", "co"))
        if None in (pm10, pm25, so2, no2, co) or pm10 < pm25:
            continue
        pm = pm10 - pm25
        row_sum = so2 + no2 + co + pm25 + pm
        if row_sum <= 0:
            continue
        samples.append({
            "PM": pm / row_sum,
            "SO2": so2 / row_sum,
            "NO2": no2 / row_sum,
            "CO": co / row_sum,
            "PM2.5": pm25 / row_sum,
        })
    if len(samples) < 2:
        return {
            "status": "insufficient_samples",
            "sample_count": len(samples),
            "required_samples": 2,
            "classification": "indeterminate",
            "reason": "at_least_two_complete_composition_samples_required",
        }
    latest = samples[-1]
    means = {key: sum(item[key] for item in samples) / len(samples) for key in latest}
    stddevs = {key: pstdev([item[key] for item in samples]) for key in latest}
    flags = {key: int(latest[key] > means[key] + stddevs[key]) for key in latest}
    flag_tuple = tuple(flags[key] for key in ("SO2", "NO2", "CO", "PM2.5", "PM"))
    classifications = {
        (0, 0, 0, 0, 0): "偏综合型",
        (0, 0, 0, 1, 0): "偏二次型",
        (0, 0, 1, 0, 0): "偏机动车型",
        (1, 0, 0, 0, 0): "偏燃煤型",
        (0, 0, 0, 0, 1): "偏扬尘型",
    }
    return {
        "status": "calculated",
        "sample_count": len(samples),
        "components": {key: round(value, 6) for key, value in latest.items()},
        "historical_means": {key: round(value, 6) for key, value in means.items()},
        "historical_standard_deviations": {key: round(value, 6) for key, value in stddevs.items()},
        "flags": flags,
        "classification": classifications.get(flag_tuple, "其他类型"),
        "flag_rule": "current_proportion > historical_mean + historical_standard_deviation",
        "formula": "ROW_SUM=SO2+NO2+CO+PM2.5+(PM10-PM2.5); PM=PM10-PM2.5",
    }


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
                "source_table": "dbo.dat_station_hour",
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
                SELECT station_id, name, lon, lat, pm25, pm10, o3, no2, so2, co, data_time
                FROM dbo.dat_station_hour
                WHERE city_area_code = ? AND data_time >= ? AND data_time < ?
                ORDER BY station_id, data_time
                """,
                ["411000", start, end],
            )
            columns = [column[0] for column in cursor.description]
            rows.extend(dict(zip(columns, row, strict=True), data_source="hour") for row in cursor.fetchall())
            return rows
        finally:
            connection.close()

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory()
        target_date = now.astimezone(TZ_SHANGHAI).date() - timedelta(days=1)
        result = evaluate_station_daily_pollution(self.load_rows(target_date), target_date=target_date)
        from app.scheduled_tasks import get_scheduled_task_service

        task_service = get_scheduled_task_service()
        review_path = get_data_registry() / "xuchang_station_daily_reviews" / f"{target_date:%Y%m%d}.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        await task_service.publish_event(TaskEvent(
            event_id=f"xuchang-station-daily-review-{target_date:%Y%m%d}",
            event_type=DAILY_REVIEW_EVENT_TYPE,
            occurred_at=datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=TZ_SHANGHAI).isoformat(),
            attributes={"city": "许昌市", "target_date": result["target_date"]},
            payload={
                "city": "许昌市",
                "target_date": result["target_date"],
                "event_count": len(result["events"]),
                "events": result["events"],
                "evidence_package_path": format_agent_path(review_path),
                "template_path": "/home/xckj/suyuan/backend/backend_data_registry/uploads/401ecbb4-c402-4f55-b37c-331e7a88b49d.docx",
            },
        ))
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

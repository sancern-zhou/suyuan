"""Collect hourly Xuchang exceedance-process evidence and request source analysis."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pyodbc
import structlog

from app.db.repositories.weather_repo import WeatherRepository
from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.xuchang_station_daily_exceedance import (
    XUCHANG_ERA5_GRID_POINT,
    XUCHANG_NMC_STATION_ID,
    analyze_boundary_layer,
    analyze_cloud_cover,
    analyze_high_humidity_conversion,
    analyze_temperature_inversion,
    merge_meteo_rows,
)
from app.integrations.xcai_station_sql import xcai_connection_string
from app.scenarios.xuchang_city_exceedance.process import POLLUTANT_FIELDS, detect_processes
from app.scenarios.xuchang_daily_review.township_hourly import load_township_hourly_rows
from app.scenarios.xuchang_transport_escalation.service import XuchangTransportEscalationService
from app.scheduled_tasks.models import TaskEvent

logger = structlog.get_logger()
TZ = ZoneInfo("Asia/Shanghai")
NATIONAL_STATION_IDS = ("1003A", "1005A", "1008A", "1009A", "1011A", "1012A")
CONFIRMED_EVENT = "xuchang.city_pollution_episode.confirmed"
REQUESTED_EVENT = "xuchang.city_source_analysis.requested"
REGIONAL_CITIES = ("郑州市", "开封市", "平顶山市", "漯河市", "周口市", "商丘市", "驻马店市")


def _value(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _temperature(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _local(value: datetime) -> datetime:
    return value.astimezone(TZ).replace(tzinfo=None) if value.tzinfo else value


def _in_window(value: Any, start: datetime, end: datetime) -> bool:
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return False
    return start <= _local(value) <= end


def _station_summary(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("station_id"):
            grouped.setdefault(str(row["station_id"]), []).append(row)
    result = []
    for station_id, samples in grouped.items():
        valid = [(row["data_time"], _value(row.get(field))) for row in samples]
        valid = [(stamp, value) for stamp, value in valid if value is not None]
        if not valid:
            continue
        anchor = samples[0]
        result.append({
            "station_id": station_id, "station_name": anchor.get("name") or station_id,
            "district": anchor.get("district"), "lat": anchor.get("lat"), "lon": anchor.get("lon"),
            "valid_hours": len(valid), "mean": round(sum(item[1] for item in valid) / len(valid), 2),
            "peak": max(item[1] for item in valid),
            "peak_time": max(valid, key=lambda item: item[1])[0].isoformat(),
        })
    return sorted(result, key=lambda item: item["mean"], reverse=True)


class XuchangCityExceedanceFetcher(DataFetcher):
    def __init__(self, analysis_service: XuchangTransportEscalationService | None = None,
                 now_factory=None, township_loader=load_township_hourly_rows) -> None:
        super().__init__(
            name="xuchang_city_exceedance_fetcher",
            description="许昌国控站小时轻度污染及站点偏差过程识别与溯源证据抓取",
            schedule="20 * * * *", version="1.0.0",
        )
        self.analysis_service = analysis_service or XuchangTransportEscalationService()
        self.now_factory = now_factory or (lambda: datetime.now(TZ))
        self.township_loader = township_loader

    def load_national(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        placeholders = ", ".join("?" for _ in NATIONAL_STATION_IDS)
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""SELECT station_id, name, lon, lat, aqi, pollutant,
                                  pm25, pm10, o3, no2, so2, co, data_time
                    FROM dbo.dat_station_hour
                    WHERE city_area_code = ? AND station_id IN ({placeholders})
                      AND data_time >= ? AND data_time <= ?
                    ORDER BY data_time, station_id""",
                ["411000", *NATIONAL_STATION_IDS, start, end],
            )
            columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        finally:
            connection.close()

    def load_regional(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        placeholders = ", ".join("?" for _ in REGIONAL_CITIES)
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""SELECT Area, TimePoint, PM2_5, PM10, O3
                    FROM dbo.CityAQIPublishHistory
                    WHERE TimePoint >= ? AND TimePoint <= ? AND Area IN ({placeholders})
                    ORDER BY Area, TimePoint""", [start, end, *REGIONAL_CITIES],
            )
            return [{"station_id": row[0], "name": row[0], "data_time": row[1],
                     "pm25": row[2], "pm10": row[3], "o3": row[4]} for row in cursor.fetchall()]
        finally:
            connection.close()

    async def load_meteorology(self, start: datetime, end: datetime) -> dict[str, Any]:
        repository = WeatherRepository()
        observed, era5, errors = [], [], []
        try:
            for item in await repository.get_observed_data(XUCHANG_NMC_STATION_ID,
                        start.replace(tzinfo=TZ), end.replace(tzinfo=TZ)):
                observed.append({"time": item.time.isoformat(), "temperature_2m": _temperature(item.temperature_2m),
                    "relative_humidity_2m": _value(item.relative_humidity_2m),
                    "wind_speed_10m_ms": _value(item.wind_speed_10m),
                    "wind_direction_10m": _value(item.wind_direction_10m),
                    "precipitation": _value(item.precipitation)})
        except Exception as exc:
            errors.append(f"nmc:{type(exc).__name__}")
        try:
            for item in await repository.get_weather_data(*XUCHANG_ERA5_GRID_POINT,
                        start.replace(tzinfo=TZ), end.replace(tzinfo=TZ)):
                wind_kmh = _value(item.wind_speed_10m)
                era5.append({"time": item.time.isoformat(), "temperature_2m": _temperature(item.temperature_2m),
                    "relative_humidity_2m": _value(item.relative_humidity_2m),
                    "wind_speed_10m_ms": round(wind_kmh / 3.6, 2) if wind_kmh is not None else None,
                    "wind_direction_10m": _value(item.wind_direction_10m),
                    "precipitation": _value(item.precipitation),
                    "cloud_cover": _value(item.cloud_cover),
                    "boundary_layer_height": _value(item.boundary_layer_height)})
        except Exception as exc:
            errors.append(f"era5:{type(exc).__name__}")
        merged, coverage = merge_meteo_rows(observed, era5)
        return {"status": "available" if merged else "not_available", "rows": merged,
                "source_coverage": coverage, "errors": errors,
                "boundary_layer_analysis": analyze_boundary_layer(merged),
                "cloud_cover_analysis": analyze_cloud_cover(merged),
                "temperature_inversion_analysis": analyze_temperature_inversion(merged)}

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory().astimezone(TZ)
        last_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        scan_start = _local(last_hour - timedelta(hours=71))
        scan_end = _local(last_hour)
        national = self.load_national(scan_start, scan_end)
        township_result = self.township_loader(scan_start, scan_end)
        townships = township_result.get("rows") or []
        processes = detect_processes(national, townships)
        from app.scheduled_tasks import get_scheduled_task_service
        task_service = get_scheduled_task_service()
        requested = []
        for process in processes:
            # Older open processes have already been handled; a normal run only
            # considers recently observed triggers, while a short outage can recover.
            if datetime.fromisoformat(process["end_time"]) < last_hour - timedelta(hours=6):
                continue
            start = max(_local(datetime.fromisoformat(process["start_time"])) - timedelta(hours=6), scan_start)
            end = _local(datetime.fromisoformat(process["end_time"]))
            station_id = process["station_id"]
            field = POLLUTANT_FIELDS[process["target_pollutant"]]
            station_rows = [row for row in (national if process["station_type"] == "national" else townships)
                            if str(row.get("station_id")) == station_id and _in_window(row.get("data_time"), start, end)]
            nearby_townships = [row for row in townships if _in_window(row.get("data_time"), start, end)]
            peer_rows = [row for row in national if _in_window(row.get("data_time"), start, end)]
            try:
                regional_rows = self.load_regional(start, end)
                regional_status = "available"
            except Exception as exc:
                regional_rows, regional_status = [], f"not_available:{type(exc).__name__}"
            meteo = await self.load_meteorology(start, end)
            meteo["high_humidity_conversion_analysis"] = analyze_high_humidity_conversion(
                meteo["rows"], station_rows, station_id)
            valid = [row for row in station_rows if _value(row.get(field)) is not None]
            hourly_rows = [{"time": _local(row["data_time"]).replace(tzinfo=TZ).isoformat(),
                            "concentration": _value(row.get(field))} for row in valid]
            process_start = datetime.fromisoformat(process["start_time"])
            slug = process["target_pollutant"].lower().replace(".", "")
            event_id = f"xuchang-city-{process_start:%Y%m%d%H}-{process['station_type']}-{station_id}-{slug}"
            event = {
                "event_id": event_id, "event_type": CONFIRMED_EVENT, "status": "confirmed",
                "city": "许昌市", "station_id": station_id, "station_name": process["station_name"],
                "station_type": process["station_type"], "lat": process["lat"], "lon": process["lon"],
                "target_date": process_start.date().isoformat(),
                "target_pollutant": process["target_pollutant"], "source_granularity": "station_hour",
                "process_window": {"start": process["start_time"], "last_trigger_hour": process["end_time"],
                                   "evidence_start": start.replace(tzinfo=TZ).isoformat(), "analysis_stage": "initial"},
                "trigger": {"rules": process["triggers"], "hours": process["trigger_hours"],
                            "standard": process["data_standard"]},
                "hourly_rows": hourly_rows,
                "station_hourly": [{**row, "data_time": row["data_time"].isoformat()} for row in station_rows],
                "meteorology_evidence": meteo,
                "township_and_provincial_transport": {
                    "status": "available" if nearby_townships or regional_rows else "not_available",
                    "township_source_status": township_result.get("status"),
                    "regional_source_status": regional_status,
                    "national_station_summary": _station_summary(peer_rows, field),
                    "township_station_summary": _station_summary(nearby_townships, field),
                    "regional_city_summary": _station_summary(regional_rows, field),
                    "interpretation_limit": "同期变化与空间梯度仅为线索，不是传输贡献率"},
                "data_quality": {"target_valid_hours": len(valid),
                    "expected_window_hours": int((end - start).total_seconds() / 3600) + 1,
                    "national_station_rows": len(peer_rows), "township_rows": len(nearby_townships),
                    "regional_rows": len(regional_rows), "meteorology_hours": len(meteo["rows"])},
                "valid_hours": len(valid), "data_rate": len(valid) / max(1, int((end - start).total_seconds() / 3600) + 1),
            }
            ingestion = self.analysis_service.ingest_process_exceedance(event)
            if ingestion["status"] != "requested":
                continue
            job = ingestion["job"]
            await task_service.publish_event(TaskEvent(
                event_id=event_id, event_type=CONFIRMED_EVENT, occurred_at=now.isoformat(),
                attributes={"city": "许昌市", "station_id": station_id, "target_pollutant": event["target_pollutant"]},
                payload={"analysis_id": job["analysis_id"], "process_window": event["process_window"],
                         "target_pollutant": event["target_pollutant"], "station_id": station_id},
            ))
            await task_service.publish_event(TaskEvent(
                event_id=job["event_id"], event_type=REQUESTED_EVENT, occurred_at=now.isoformat(),
                attributes={"city": "许昌市", "station_id": station_id, "target_pollutant": event["target_pollutant"]},
                payload={"analysis_id": job["analysis_id"], "process_window": event["process_window"]},
            ))
            requested.append(job["analysis_id"])
        logger.info("xuchang_city_exceedance_scanned", detected=len(processes), requested=len(requested))
        return {"scan_end": last_hour.isoformat(), "process_count": len(processes),
                "requested_analyses": requested, "township_status": township_result.get("status")}

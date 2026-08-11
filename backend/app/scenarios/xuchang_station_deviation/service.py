"""Detect local station deviations from Xuchang hourly monitoring data.

This module deliberately contains no source attribution or response advice.
It produces the factual trigger context required by the Scenario 1 Agent tool.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import pyodbc
import structlog

from app.integrations.xcai_station_sql import xcai_connection_string
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger()
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
EVENT_TYPE = "xuchang.station_deviation.alert_created"
POLLUTANT_COLUMNS = {
    "PM2.5": "pm25",
    "O3": "o3",
    # The station table publishes NO2 rather than total NOx. Treat it as an
    # explicit screening proxy instead of silently claiming a NOx measurement.
    "NOX": "no2",
}
OBSERVED_INDICATORS = {"PM2.5": "PM2.5", "O3": "O3", "NOX": "NO2"}
DEFAULT_ABSOLUTE_DELTA_THRESHOLDS = {
    "PM2.5": 10.0,
    "O3": 30.0,
    "NOX": 15.0,
}


@dataclass(frozen=True)
class StationDeviationConfig:
    city_area_code: str = "411000"
    city: str = "许昌市"
    deviation_threshold: float = 0.5
    min_station_count: int = 3
    min_data_rate: float = 0.8
    pollutants: tuple[str, ...] = ("PM2.5", "O3", "NOX")
    absolute_delta_thresholds: tuple[tuple[str, float], ...] = (
        ("PM2.5", 10.0),
        ("O3", 30.0),
        ("NOX", 15.0),
    )

    def absolute_delta_threshold(self, pollutant: str) -> float:
        configured = dict(self.absolute_delta_thresholds)
        return configured.get(pollutant, DEFAULT_ABSOLUTE_DELTA_THRESHOLDS.get(pollutant, 0.0))


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _hour(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(minute=0, second=0, microsecond=0)
    return value.astimezone(TZ_SHANGHAI).replace(minute=0, second=0, microsecond=0)


def detect_station_deviations(
    rows: Iterable[dict[str, Any]],
    *,
    expected_station_count: int,
    config: StationDeviationConfig,
) -> dict[str, Any]:
    """Apply the documented leave-one-out station-deviation rule."""
    grouped: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        timestamp = row.get("data_time")
        if not isinstance(timestamp, datetime):
            continue
        grouped[_hour(timestamp)].append(row)

    alerts: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    for timestamp, hour_rows in sorted(grouped.items()):
        station_rows = {
            str(row.get("station_id")): row
            for row in hour_rows
            if row.get("station_id") and _float(row.get("lat")) is not None and _float(row.get("lon")) is not None
        }
        for pollutant in config.pollutants:
            column = POLLUTANT_COLUMNS.get(pollutant)
            if not column:
                continue
            values = [(station_id, row, _float(row.get(column))) for station_id, row in station_rows.items()]
            values = [(station_id, row, value) for station_id, row, value in values if value is not None]
            available_stations = len(values)
            data_rate = available_stations / expected_station_count if expected_station_count else 0.0
            check = {
                "time": timestamp.isoformat(),
                "pollutant": pollutant,
                "observed_indicator": OBSERVED_INDICATORS[pollutant],
                "expected_station_count": expected_station_count,
                "available_station_count": available_stations,
                "data_rate": round(data_rate, 3),
                "status": "checked",
            }
            if expected_station_count < config.min_station_count or available_stations < config.min_station_count:
                check["status"] = "insufficient_station_count"
                checks.append(check)
                continue
            if data_rate < config.min_data_rate:
                check["status"] = "insufficient_data_rate"
                checks.append(check)
                continue
            checks.append(check)

            pollutant_alerts = []
            absolute_threshold = config.absolute_delta_threshold(pollutant)
            for station_id, row, value in values:
                peers = [peer_value for peer_id, _, peer_value in values if peer_id != station_id]
                peer_baseline = median(peers) if peers else 0.0
                if peer_baseline <= 0:
                    continue
                deviation = (value - peer_baseline) / peer_baseline
                absolute_delta = value - peer_baseline
                if deviation <= config.deviation_threshold or absolute_delta <= absolute_threshold:
                    continue
                pollutant_alerts.append({
                    "station_id": station_id,
                    "station_name": row.get("name") or station_id,
                    "lat": _float(row.get("lat")),
                    "lon": _float(row.get("lon")),
                    "station_value": value,
                    "peer_mean": round(peer_baseline, 3),
                    "peer_baseline": round(peer_baseline, 3),
                    "peer_baseline_method": "leave_one_out_median",
                    "absolute_delta": round(absolute_delta, 3),
                    "deviation_ratio": round(deviation, 3),
                    "deviation_percent": round(deviation * 100, 1),
                    "peer_station_count": len(peers),
                })

            if not pollutant_alerts:
                continue
            pollutant_alerts.sort(key=lambda item: (item["deviation_ratio"], item["absolute_delta"]), reverse=True)
            primary = pollutant_alerts[0]
            alerts.append({
                    "event_id": f"xuchang-station-deviation-{timestamp:%Y%m%d%H}-{pollutant.lower().replace('.', '')}",
                    "event_type": EVENT_TYPE,
                    "occurred_at": timestamp.isoformat(),
                    "city": config.city,
                    "city_area_code": config.city_area_code,
                    "target_pollutant": pollutant,
                    "observed_indicator": OBSERVED_INDICATORS[pollutant],
                    "nox_proxy_note": "NO2站点小时浓度作为NOX空间异常筛查代理" if pollutant == "NOX" else None,
                    **primary,
                    "secondary_stations": pollutant_alerts[1:],
                    "available_station_count": available_stations,
                    "expected_station_count": expected_station_count,
                    "data_rate": round(data_rate, 3),
                    "threshold": config.deviation_threshold,
                    "absolute_delta_threshold": absolute_threshold,
                    "rule": "relative_deviation > threshold AND absolute_delta > pollutant_absolute_threshold",
                })
    alerts.sort(key=lambda item: (item["occurred_at"], item["deviation_ratio"]), reverse=True)
    return {"alerts": alerts, "checks": checks}


class XuchangStationDeviationAlertService:
    """Read real station-hour rows, persist Scenario 1 trigger evidence."""

    def __init__(self, config: StationDeviationConfig | None = None, output_root: Path | None = None) -> None:
        self.config = config or StationDeviationConfig(city_area_code=os.getenv("XUCHANG_STATION_CITY_AREA_CODE", "411000"))
        self.output_root = output_root or get_data_registry() / "xuchang_station_deviation_alerts"

    def _query(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        finally:
            connection.close()

    def load_station_rows(self, timestamp: datetime) -> tuple[list[dict[str, Any]], int]:
        start = _hour(timestamp)
        end = start + timedelta(hours=1)
        expected = self._query(
            """
            SELECT MAX(station_count) AS count FROM (
                SELECT COUNT(DISTINCT station_id) AS station_count
                FROM dbo.dat_station_hour
                WHERE city_area_code = ? AND data_time >= DATEADD(hour, -24, ?) AND data_time < ?
                GROUP BY data_time
            ) AS hourly_counts
            """,
            [self.config.city_area_code, start.replace(tzinfo=None), end.replace(tzinfo=None)],
        )
        expected_count = int(expected[0]["count"] or 0) if expected else 0
        rows = self._query(
            """
            SELECT station_id, name, lon, lat, pm25, pm10, o3, no2, so2, co, data_time
            FROM dbo.dat_station_hour
            WHERE city_area_code = ? AND data_time >= ? AND data_time < ?
            ORDER BY data_time, station_id
            """,
            [self.config.city_area_code, start.replace(tzinfo=None), end.replace(tzinfo=None)],
        )
        return rows, expected_count

    def _write_event(self, alert: dict[str, Any]) -> Path:
        timestamp = datetime.fromisoformat(alert["occurred_at"])
        path = self.output_root / timestamp.strftime("%Y%m%d") / f"{alert['event_id']}.json"
        payload = {"schema_version": "1.0", "scenario": "local_station_deviation_upwind_source_screening", **alert}
        self._write_json(path, payload)
        return path

    def write_scenario_output(self, alert: dict[str, Any], output: dict[str, Any]) -> Path:
        timestamp = datetime.fromisoformat(alert["occurred_at"])
        path = self.output_root / timestamp.strftime("%Y%m%d") / f"{alert['event_id']}.scenario-1.json"
        self._write_json(path, {"schema_version": "1.0", **output})
        return path

    def write_evidence_package(self, alert: dict[str, Any], evidence: dict[str, Any]) -> Path:
        timestamp = datetime.fromisoformat(alert["occurred_at"])
        path = self.output_root / timestamp.strftime("%Y%m%d") / f"{alert['event_id']}.evidence.json"
        self._write_json(path, evidence)
        return path

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)
        temp_path.replace(path)

    async def run(self, target_time: datetime | None = None) -> dict[str, Any]:
        # Run after the source hour closes; never inspect a partial current hour.
        target_hour = _hour(target_time or datetime.now(TZ_SHANGHAI) - timedelta(hours=1))
        rows, expected_station_count = self.load_station_rows(target_hour)
        result = detect_station_deviations(rows, expected_station_count=expected_station_count, config=self.config)
        events = []
        for alert in result["alerts"]:
            path = self._write_event(alert)
            events.append({**alert, "event_json_path": format_agent_path(path)})
        return {
            "city": self.config.city,
            "target_hour": target_hour.isoformat(),
            "expected_station_count": expected_station_count,
            "rows": len(rows),
            "alerts": events,
            "checks": result["checks"],
        }

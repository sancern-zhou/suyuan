"""Detect local station deviations from Xuchang hourly monitoring data.

This module deliberately contains no source attribution or response advice.
It produces the factual trigger context required by the Scenario 1 Agent tool.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any
from zoneinfo import ZoneInfo

import pyodbc
import structlog

from app.integrations.xcai_station_sql import xcai_connection_string
from app.utils.path_config import format_agent_path, get_data_registry
from app.scenarios.xuchang_station_deviation.source_features import calculate_pollutant_source_features
from app.scenarios.xuchang_station_deviation.dispatch import resolve_station

logger = structlog.get_logger()
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
EVENT_TYPE = "xuchang.station_deviation.alert_created"
POLLUTANT_COLUMNS = {
    "PM2.5": "pm25",
    "PM10": "pm10",
    "SO2": "so2",
    "NO2": "no2",
    "CO": "co",
    "O3": "o3",
    # The station table publishes NO2 rather than total NOx. Treat it as an
    # explicit screening proxy instead of silently claiming a NOx measurement.
    "NOX": "no2",
}
POLLUTANT_SOURCES = {"PM2.5": "hour", "PM10": "minute", "SO2": "minute", "NO2": "minute", "CO": "minute", "O3": "minute", "NOX": "minute"}
OBSERVED_INDICATORS = {"PM2.5": "PM2.5", "PM10": "PM10", "SO2": "SO2", "NO2": "NO2", "CO": "CO", "O3": "O3", "NOX": "NO2"}
DEFAULT_ABSOLUTE_DELTA_THRESHOLDS = {
    "PM2.5": 10.0,
    "PM10": 10.0,
    "SO2": 5.0,
    "NO2": 10.0,
    "CO": 0.2,
    "O3": 30.0,
    "NOX": 15.0,
}
DEFAULT_LEVEL_DEVIATION_THRESHOLDS = {
    "优": 0.30,
    "良": 0.40,
    "轻度污染": 0.50,
    "中度污染": 0.50,
    "重度污染": 0.50,
    "严重污染": 0.50,
}
DEFAULT_RISE_THRESHOLDS = {
    "PM2.5": (0.10, 5.0, 0.20, 15.0),
    "PM10": (0.08, 10.0, 0.15, 25.0),
    "NO2": (0.15, 8.0, 0.25, 15.0),
    "SO2": (0.20, 5.0, 0.30, 10.0),
    "O3": (0.10, 10.0, 0.20, 20.0),
    "CO": (0.15, 0.3, 0.25, 0.5),
}


@dataclass(frozen=True)
class StationDeviationConfig:
    city_area_code: str = "411000"
    city: str = "许昌市"
    deviation_threshold: float = 0.5
    min_station_count: int = 3
    min_data_rate: float = 0.8
    pollutants: tuple[str, ...] = ("PM2.5", "PM10", "SO2", "NO2", "CO", "O3", "NOX")
    absolute_delta_thresholds: tuple[tuple[str, float], ...] = (
        ("PM2.5", 10.0),
        ("PM10", 10.0),
        ("SO2", 5.0),
        ("NO2", 10.0),
        ("CO", 0.2),
        ("O3", 30.0),
        ("NOX", 15.0),
    )

    def absolute_delta_threshold(self, pollutant: str) -> float:
        configured = dict(self.absolute_delta_thresholds)
        return configured.get(pollutant, DEFAULT_ABSOLUTE_DELTA_THRESHOLDS.get(pollutant, 0.0))

    def deviation_threshold_for(self, air_quality_level: str | None = None) -> float:
        level = air_quality_level or os.getenv("XUCHANG_ALERT_AQI_LEVEL", "良")
        return float(DEFAULT_LEVEL_DEVIATION_THRESHOLDS.get(level, self.deviation_threshold))

    def rise_thresholds(self, pollutant: str) -> tuple[float, float, float, float]:
        return DEFAULT_RISE_THRESHOLDS.get(pollutant, (0.10, 1.0, 0.20, 5.0))


def air_quality_level_from_aqi(value: Any) -> str | None:
    """Map a numeric AQI to the Chinese level used by dynamic thresholds."""
    try:
        aqi = float(value)
    except (TypeError, ValueError):
        return None
    if aqi <= 50:
        return "优"
    if aqi <= 100:
        return "良"
    if aqi <= 150:
        return "轻度污染"
    if aqi <= 200:
        return "中度污染"
    if aqi <= 300:
        return "重度污染"
    return "严重污染"


def evaluate_adverse_meteorology(summary: dict[str, Any] | None) -> dict[str, Any]:
    """Return a conservative five-minute sensitivity decision from weather facts."""
    summary = summary or {}
    wind = _float(summary.get("mean_wind_speed_ms", summary.get("wind_speed")))
    humidity = _float(summary.get("mean_relative_humidity_percent", summary.get("humidity")))
    stable = summary.get("stability") in {"stable", "静稳", "稳定"}
    inversion = bool(summary.get("has_inversion", summary.get("inversion")))
    wind_unfavorable = wind is not None and wind < 2.0
    still = wind is not None and wind < 0.5
    humidity_support = humidity is not None and humidity >= 80.0
    core_conditions = [wind_unfavorable and stable, inversion, still]
    adverse = any(core_conditions)
    # Humidity supports interpretation but never creates an adverse decision.
    sensitivity = 0.75 if adverse else 1.0
    return {
        "adverse": adverse,
        "sensitivity": sensitivity,
        "reasons": [
            name for name, hit in (
                ("低风速且稳定", wind_unfavorable and stable),
                ("静风", still),
                ("逆温", inversion),
                ("高湿辅助", humidity_support),
            ) if hit
        ],
        "threshold_adjustment": "降低至75%" if adverse else "不调整",
        "humidity_is_supporting_only": True,
    }


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _has_mark(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _observed_indicator(pollutant: Any) -> str:
    # NOX 筛查读的是 NO2 列，因子归并时与 NO2 视为同一种污染物。
    name = str(pollutant or "")
    return OBSERVED_INDICATORS.get(name, name)


def _hour(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(minute=0, second=0, microsecond=0)
    return value.astimezone(TZ_SHANGHAI).replace(minute=0, second=0, microsecond=0)


def _slot(value: datetime, source: str) -> datetime:
    value = value if value.tzinfo else value.replace(tzinfo=TZ_SHANGHAI)
    value = value.astimezone(TZ_SHANGHAI)
    if source == "minute":
        return value.replace(minute=(value.minute // 5) * 5, second=0, microsecond=0)
    return _hour(value)


def detect_station_deviations(
    rows: Iterable[dict[str, Any]],
    *,
    expected_station_count: int,
    config: StationDeviationConfig,
    expected_station_counts: dict[str, int] | None = None,
    air_quality_level: str | None = None,
) -> dict[str, Any]:
    """Apply the documented leave-one-out station-deviation rule."""
    grouped: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        timestamp = row.get("data_time")
        if not isinstance(timestamp, datetime):
            continue
        grouped[_slot(timestamp, row.get("data_source", "hour"))].append(row)

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
            source = POLLUTANT_SOURCES.get(pollutant, "hour")
            source_rows = {
                station_id: row for station_id, row in station_rows.items()
                if row.get("data_source", "hour") == source
            }
            marked_station_count = 0
            if source == "minute":
                mark_column = f"{column}_mark"
                marked_station_count = sum(1 for row in source_rows.values() if _has_mark(row.get(mark_column)))
                source_rows = {
                    station_id: row for station_id, row in source_rows.items()
                    if not _has_mark(row.get(mark_column))
                }
            values = [(station_id, row, _float(row.get(column))) for station_id, row in source_rows.items()]
            values = [(station_id, row, value) for station_id, row, value in values if value is not None]
            available_stations = len(values)
            expected_count = (expected_station_counts or {}).get(source, expected_station_count)
            data_rate = available_stations / expected_count if expected_count else 0.0
            check = {
                "time": timestamp.isoformat(),
                "pollutant": pollutant,
                "observed_indicator": OBSERVED_INDICATORS[pollutant],
                "expected_station_count": expected_count,
                "available_station_count": available_stations,
                "marked_station_count": marked_station_count,
                "data_rate": round(data_rate, 3),
                "status": "checked",
            }
            if expected_count < config.min_station_count or available_stations < config.min_station_count:
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
                # Scenario 1 uses the mean of the other five stations as the
                # business baseline. Keep the leave-one-out construction so a
                # high target station cannot inflate its own reference value.
                peer_baseline = mean(peers) if peers else 0.0
                if peer_baseline <= 0:
                    continue
                deviation = (value - peer_baseline) / peer_baseline
                absolute_delta = value - peer_baseline
                deviation_threshold = config.deviation_threshold_for(air_quality_level)
                if deviation <= deviation_threshold or absolute_delta <= absolute_threshold:
                    continue
                pollutant_alerts.append({
                    "station_id": station_id,
                    "station_name": row.get("name") or station_id,
                    "lat": _float(row.get("lat")),
                    "lon": _float(row.get("lon")),
                    "station_value": value,
                    "peer_mean": round(peer_baseline, 3),
                    "peer_baseline": round(peer_baseline, 3),
                    "peer_baseline_method": "leave_one_out_mean",
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
                    "event_id": f"xuchang-station-deviation-{timestamp:%Y%m%d%H%M}-{pollutant.lower().replace('.', '')}",
                    "event_type": EVENT_TYPE,
                    "occurred_at": timestamp.isoformat(),
                    "city": config.city,
                    "city_area_code": config.city_area_code,
                    "target_pollutant": pollutant,
                    "data_source": source,
                    "measurement_granularity": "5min" if source == "minute" else "hour",
                    "observed_indicator": OBSERVED_INDICATORS[pollutant],
                    "nox_proxy_note": "NO2站点小时浓度作为NOX空间异常筛查代理" if pollutant == "NOX" else None,
                    **primary,
                    "secondary_stations": pollutant_alerts[1:],
                    "available_station_count": available_stations,
                    "marked_station_count": marked_station_count,
                    "expected_station_count": expected_count,
                    "data_rate": round(data_rate, 3),
                    "threshold": deviation_threshold,
                    "absolute_delta_threshold": absolute_threshold,
                    "rule": "relative_deviation > threshold AND absolute_delta > pollutant_absolute_threshold",
                })
    alerts.sort(key=lambda item: (item["occurred_at"], item["deviation_ratio"]), reverse=True)
    return {"alerts": alerts, "checks": checks}


def detect_continuous_rises(
    rows: Iterable[dict[str, Any]],
    *,
    config: StationDeviationConfig,
    sensitivity: float = 1.0,
) -> list[dict[str, Any]]:
    """Detect six consecutive five-minute rises with pollutant thresholds."""
    grouped: dict[tuple[str, str], list[tuple[datetime, float, dict[str, Any]]]] = defaultdict(list)
    for row in rows:
        if row.get("data_source") != "minute":
            continue
        timestamp = row.get("data_time")
        if not isinstance(timestamp, datetime):
            continue
        station_id = str(row.get("station_id") or "")
        for pollutant, column in POLLUTANT_COLUMNS.items():
            if pollutant in ("PM2.5", "O3") or not station_id or _has_mark(row.get(f"{column}_mark")):
                continue
            value = _float(row.get(column))
            if value is not None:
                grouped[(station_id, pollutant)].append((timestamp, value, row))
    alerts: list[dict[str, Any]] = []
    for (station_id, pollutant), points in grouped.items():
        points.sort(key=lambda item: item[0])
        for index in range(6, len(points)):
            window = points[index - 6:index + 1]
            if any(window[i][0] - window[i - 1][0] > timedelta(minutes=6) for i in range(1, 7)):
                continue
            values = [item[1] for item in window]
            rises = [values[i] - values[i - 1] for i in range(1, 7)]
            rate_threshold, abs_threshold, total_rate_threshold, total_abs_threshold = config.rise_thresholds(pollutant)
            rate_threshold *= sensitivity
            abs_threshold *= sensitivity
            total_rate_threshold *= sensitivity
            total_abs_threshold *= sensitivity
            if not all(rise > 0 for rise in rises):
                continue
            rates = [rises[i] / values[i] if values[i] > 0 else 0.0 for i in range(6)]
            if not all(rate > rate_threshold or rise > abs_threshold for rate, rise in zip(rates, rises)):
                continue
            total_abs = values[-1] - values[0]
            total_rate = total_abs / values[0] if values[0] > 0 else 0.0
            if total_rate <= total_rate_threshold or total_abs <= total_abs_threshold:
                continue
            row = window[-1][2]
            alerts.append({
                "event_id": f"xuchang-station-rise-{window[-1][0]:%Y%m%d%H%M}-{station_id}-{pollutant.lower().replace('.', '')}",
                "event_type": EVENT_TYPE,
                "occurred_at": window[-1][0].isoformat(),
                "city": row.get("city", "许昌市"),
                "station_id": station_id,
                "station_name": row.get("name") or station_id,
                "target_pollutant": pollutant,
                "data_source": "minute",
                "measurement_granularity": "5min",
                "station_value": values[-1],
                "rise_window_values": values,
                "rise_count": 6,
                "total_rise_rate": round(total_rate, 4),
                "total_rise_abs": round(total_abs, 3),
                "rule": "six_consecutive_5min_rises_and_pollutant_thresholds",
            })
            break
    return alerts


class XuchangStationDeviationAlertService:
    """Read real station-hour rows, persist Scenario 1 trigger evidence."""

    # Six consecutive five-minute rises cover 30 minutes.  One hour gives
    # dispatchers enough lead-in context without turning a minute alert into
    # a daily trend chart.
    MINUTE_TREND_LOOKBACK_MINUTES = 60

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

    def load_station_rows(self, timestamp: datetime) -> tuple[list[dict[str, Any]], dict[str, int]]:
        start = _hour(timestamp) - timedelta(hours=1)
        end = start + timedelta(hours=1)
        source_start = _hour(timestamp) - timedelta(hours=24)
        expected_hour = self._query(
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
        expected_hour_count = int(expected_hour[0]["count"] or 0) if expected_hour else 0
        hour_rows = self._query(
            """
            SELECT station_id, name, lon, lat, pm25, pm10, o3, no2, so2, co, data_time
            FROM dbo.dat_station_hour
            WHERE city_area_code = ? AND data_time >= ? AND data_time < ?
            ORDER BY data_time, station_id
            """,
            [self.config.city_area_code, source_start.replace(tzinfo=None), end.replace(tzinfo=None)],
        )
        for row in hour_rows:
            row["data_source"] = "hour"

        # Keep the current completed slot for detection and retain 24h of
        # minute history so composition features have enough samples.
        minute_start = timestamp.replace(second=0, microsecond=0)
        minute_start = minute_start.replace(minute=(minute_start.minute // 5) * 5)
        minute_end = minute_start + timedelta(minutes=5)
        expected_minute = self._query(
            """
            SELECT MAX(station_count) AS count FROM (
                SELECT COUNT(DISTINCT station_code) AS station_count
                FROM dbo.dat_zhongda_station_minute
                WHERE area = ? AND time_point >= DATEADD(hour, -24, ?) AND time_point < ?
                GROUP BY time_point
            ) AS slot_counts
            """,
            [self.config.city, minute_start.replace(tzinfo=None), minute_end.replace(tzinfo=None)],
        )
        expected_minute_count = int(expected_minute[0]["count"] or 0) if expected_minute else 0
        minute_rows = self._query(
            """
            SELECT station_code AS station_id, station_name AS name,
                   pm25, pm10, o3, no2, so2, co,
                   pm25_mark, pm10_mark, o3_mark, no2_mark, so2_mark, co_mark, nox_mark,
                   time_point AS data_time
            FROM dbo.dat_zhongda_station_minute AS minute_data
            WHERE minute_data.area = ? AND minute_data.time_point >= ? AND minute_data.time_point < ?
            ORDER BY minute_data.time_point, minute_data.station_code
            """,
            [self.config.city, source_start.replace(tzinfo=None), minute_end.replace(tzinfo=None)],
        )
        for row in minute_rows:
            row["data_source"] = "minute"
            station = resolve_station(row, hour_rows)
            row["lon"] = station["longitude"] if station else None
            row["lat"] = station["latitude"] if station else None
            if station:
                row["canonical_station_id"] = station["canonical_station_id"]
                row["coordinate_source"] = station["coordinate_source"]
        return [*hour_rows, *minute_rows], {"hour": expected_hour_count, "minute": expected_minute_count}

    def _write_event(self, alert: dict[str, Any]) -> Path:
        timestamp = datetime.fromisoformat(alert["occurred_at"])
        path = self.output_root / timestamp.strftime("%Y%m%d") / f"{alert['event_id']}.json"
        payload = {"schema_version": "1.0", "scenario": "station_pollution_monitoring_alert", **alert}
        self._write_json(path, payload)
        return path

    def _minute_trend_rows(self, rows: list[dict[str, Any]], target_slot: datetime) -> list[dict[str, Any]]:
        """Return the short-term minute window used by rise detection/charts."""
        window_start = target_slot - timedelta(minutes=self.MINUTE_TREND_LOOKBACK_MINUTES)
        window_end = target_slot + timedelta(minutes=5)
        return [
            row for row in rows
            if row.get("data_source") == "minute"
            and row.get("data_time") is not None
            and window_start <= _slot(row["data_time"], "minute") < window_end
        ]

    def write_timeseries_chart(self, alert: dict[str, Any], rows: list[dict[str, Any]]) -> Path | None:
        """Render a station-comparison trend chart for an alert evidence package."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from app.utils.font_utils import apply_font_to_figure, configure_chinese_font, chinese_font_prop
            configure_chinese_font()
            chinese_font = chinese_font_prop()
        except Exception as exc:  # pragma: no cover - optional rendering dependency
            logger.warning("xuchang_alert_chart_unavailable", error=str(exc))
            return None
        field = POLLUTANT_COLUMNS.get(str(alert.get("target_pollutant")))
        if not field:
            return None
        station_id = str(alert.get("station_id") or "")
        points: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        station_names: dict[str, str] = {}
        for row in rows:
            current_id = str(row.get("station_id") or "")
            name = row.get("name") or row.get("station_name")
            if current_id and name:
                station_names[current_id] = str(name)
            value = _float(row.get(field))
            timestamp = row.get("data_time")
            if value is None or not isinstance(timestamp, datetime):
                continue
            if row.get("data_source") != ("hour" if alert.get("measurement_granularity") == "hour" else "minute"):
                continue
            if row.get("data_source") == "minute" and _has_mark(row.get(f"{field}_mark")):
                continue
            points[str(row.get("station_id") or "")].append((timestamp, value))
        if not points:
            return None
        # The chart is for dispatch use: resolve every legend entry through
        # the station name returned by the monitoring tables and never expose
        # an internal station code to the operator.
        if station_id and alert.get("station_name"):
            station_names[station_id] = str(alert["station_name"])
        fig, ax = plt.subplots(figsize=(10, 4.8), dpi=140)
        chart_times = [timestamp for values in points.values() for timestamp, _ in values]
        chart_start, chart_end = min(chart_times), max(chart_times)
        # Keep the axis tied to the actual short-term samples.  A stale or
        # timezone-shifted event timestamp must not expand the chart to days
        # of empty space.
        span = chart_end - chart_start
        padding = max(timedelta(minutes=2.5), span * 0.05)
        ax.set_xlim(chart_start - padding, chart_end + padding)
        for current_id, values in sorted(points.items()):
            values.sort()
            ax.plot([item[0] for item in values], [item[1] for item in values], marker="o" if len(values) < 20 else None,
                    linewidth=2.2 if current_id == station_id else 1.0,
                    color="#d62728" if current_id == station_id else None,
                    alpha=1.0 if current_id == station_id else 0.65,
                    label=station_names.get(current_id) or "未命名站点")
        event_time = alert.get("occurred_at")
        if event_time:
            try:
                event_dt = datetime.fromisoformat(str(event_time))
                if chart_start.tzinfo is None and event_dt.tzinfo is not None:
                    event_dt = event_dt.replace(tzinfo=None)
                elif chart_start.tzinfo is not None and event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=chart_start.tzinfo)
                if chart_start - padding <= event_dt <= chart_end + padding:
                    ax.axvline(event_dt, color="#d62728", linestyle="--", linewidth=1.4, alpha=0.8)
                    ax.annotate("告警触发", xy=(event_dt, 0.98), xycoords=("data", "axes fraction"),
                                xytext=(5, -5), textcoords="offset points", color="#d62728", fontsize=9,
                                ha="left", va="top", fontproperties=chinese_font)
            except ValueError:
                pass
        peer_mean = _float(alert.get("peer_mean"))
        if peer_mean is not None:
            ax.axhline(peer_mean, color="#777777", linestyle=":", linewidth=1.2, label="其余站点均值")
            threshold = _float(alert.get("threshold"))
            absolute_threshold = _float(alert.get("absolute_delta_threshold")) or 0.0
            if threshold is not None:
                trigger_line = max(peer_mean * (1 + threshold), peer_mean + absolute_threshold)
                ax.axhline(trigger_line, color="#ff7f0e", linestyle="-.", linewidth=1.1, label="相对/绝对触发线")
        signal_labels = []
        if alert.get("rule", "").startswith("six_consecutive"):
            signal_labels.append("单站持续快速上升")
        elif alert.get("peer_mean") is not None:
            signal_labels.append("单站相对区域偏高")
        if alert.get("granularity") == "hour" or alert.get("measurement_granularity") == "hour":
            signal_labels.append("小时数据")
        title_suffix = "｜".join(signal_labels)
        title = f"{alert.get('target_pollutant')}浓度趋势｜{station_names.get(station_id) or '未命名站点'}"
        ax.set_title(f"{title}｜{title_suffix}" if title_suffix else title, fontproperties=chinese_font)
        ax.set_ylabel("浓度", fontproperties=chinese_font)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", fontsize=8, ncol=3, prop=chinese_font)
        apply_font_to_figure(fig)
        fig.autofmt_xdate()
        path = self.output_root / "charts" / f"{alert['event_id']}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return path

    @staticmethod
    def _multifactor_snapshot(
        alerts: list[dict[str, Any]], rows: list[dict[str, Any]],
    ) -> tuple[datetime, list[str], dict[str, str], dict[str, dict[str, tuple[datetime, float]]], dict[str, dict[str, bool]]] | None:
        """Collect per-station values pinned to the alert slot only.

        Minute pollutants come from the alert five-minute slot; PM2.5 falls
        back to the previous completed hour (its screening source).  Readings
        outside the slot are ignored so a missing value renders as "—"
        instead of silently showing stale data from earlier slots.
        """
        try:
            alert_dt = datetime.fromisoformat(str(alerts[0].get("occurred_at") or ""))
        except ValueError:
            return None
        if alert_dt.tzinfo is None:
            alert_dt = alert_dt.replace(tzinfo=TZ_SHANGHAI)
        slot_key = _slot(alert_dt, "minute").replace(tzinfo=None)
        hour_key = slot_key.replace(minute=0) - timedelta(hours=1)
        pollutants = ("PM2.5", "PM10", "SO2", "NO2", "CO", "O3")
        fields = {name: POLLUTANT_COLUMNS[name] for name in pollutants}
        station_ids = sorted({str(row.get("station_id") or "") for row in rows if row.get("station_id")})
        names: dict[str, str] = {}
        latest: dict[str, dict[str, tuple[datetime, float]]] = defaultdict(dict)
        marked: dict[str, dict[str, bool]] = defaultdict(lambda: defaultdict(bool))
        for row in rows:
            sid = str(row.get("station_id") or "")
            if not sid:
                continue
            names[sid] = str(row.get("name") or row.get("station_name") or names.get(sid) or "未命名站点")
            timestamp = row.get("data_time")
            if not isinstance(timestamp, datetime):
                continue
            if timestamp.tzinfo is not None:
                timestamp = timestamp.astimezone(TZ_SHANGHAI).replace(tzinfo=None)
            source = row.get("data_source")
            if source == "minute":
                in_slot = _slot(timestamp, "minute").replace(tzinfo=None) == slot_key
            elif source == "hour":
                in_slot = _hour(timestamp) == hour_key
            else:
                in_slot = False
            if not in_slot:
                continue
            for pollutant, field in fields.items():
                if source == "hour" and pollutant != "PM2.5":
                    continue
                value = _float(row.get(field))
                if value is None:
                    continue
                previous = latest[sid].get(pollutant)
                if previous is None or timestamp > previous[0]:
                    latest[sid][pollutant] = (timestamp, value)
                    marked[sid][pollutant] = _has_mark(row.get(f"{field}_mark"))
        return slot_key, station_ids, names, latest, marked

    def write_multifactor_table(self, alerts: list[dict[str, Any]], rows: list[dict[str, Any]]) -> Path | None:
        """Render a compact six-pollutant table for a multi-factor episode."""
        # NOX 与 NO2 共用同一监测列，按观测指标去重后再计数，避免伪多因子。
        if len({_observed_indicator(a.get("target_pollutant")) for a in alerts}) < 2:
            return None
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.patches import Rectangle
            from app.utils.font_utils import apply_font_to_figure, configure_chinese_font, chinese_font_prop
            configure_chinese_font()
            font = chinese_font_prop()
        except Exception as exc:  # pragma: no cover
            logger.warning("xuchang_multifactor_table_unavailable", error=str(exc))
            return None
        snapshot = self._multifactor_snapshot(alerts, rows)
        if snapshot is None:
            return None
        slot_key, station_ids, names, latest, marked = snapshot
        pollutants = ("PM2.5", "PM10", "SO2", "NO2", "CO", "O3")
        # The composition table is a city-wide monitoring snapshot pinned to
        # the alert slot. Alerts determine which cells are highlighted, while
        # every national-control station with a slot reading keeps its row.
        station_ids = [sid for sid in station_ids if sid in latest]
        if not station_ids:
            return None
        cell_text = [[names.get(sid, "未命名站点")] + [
            f"{latest[sid][p][1]:.2f}*" if p in latest[sid] and marked[sid][p] else
            f"{latest[sid][p][1]:.2f}" if p in latest[sid] else "—"
            for p in pollutants
        ] for sid in station_ids]
        fig, ax = plt.subplots(figsize=(11, max(2.8, 0.55 * len(cell_text) + 1.5)), dpi=160)
        ax.axis("off")
        table = ax.table(cellText=cell_text, colLabels=["站点", *pollutants], cellLoc="center", loc="center",
                         colWidths=[0.22] + [0.13] * len(pollutants))
        table.auto_set_font_size(False); table.set_fontsize(10); table.scale(1, 1.6)
        alerted = {(str(a.get("station_id")), _observed_indicator(a.get("target_pollutant"))) for a in alerts}
        for (row_index, col_index), cell in table.get_celld().items():
            cell.get_text().set_fontproperties(font)
            if row_index == 0:
                cell.set_facecolor("#d9eaf7")
            elif col_index > 0:
                sid = station_ids[row_index - 1]; pollutant = pollutants[col_index - 1]
                if (sid, pollutant) in alerted:
                    cell.set_facecolor("#ffe0e0")
                    cell.set_edgecolor("#d62728"); cell.set_linewidth(2.0)
                if marked[sid][pollutant]:
                    cell.get_text().set_color("#888888")
                    cell.get_text().set_fontstyle("italic")
        ax.set_title(
            f"多因子污染物浓度综合表（{slot_key:%m-%d %H:%M} 快照，PM2.5 为上一小时值；红框为告警因子，灰色斜体*为带标识数据）",
            fontproperties=font, pad=16)
        apply_font_to_figure(fig)
        event_id = alerts[0].get("event_id", "multifactor")
        path = self.output_root / "charts" / f"{event_id}-multifactor-table.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, bbox_inches="tight"); plt.close(fig)
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

    def write_episode_evidence_package(
        self,
        *,
        station_id: str,
        occurred_at: str,
        alerts: list[dict[str, Any]],
    ) -> Path:
        """Persist one evidence envelope for all pollutants in a station episode."""
        timestamp = datetime.fromisoformat(occurred_at)
        # Hourly factors are dispatched separately.  A station/time-only name
        # would overwrite another factor's evidence while its Agent is reading.
        identity = sorted((str(item.get("alert", {}).get("event_id", "")),
                           str(item.get("alert", {}).get("measurement_granularity", "")),
                           str(item.get("alert", {}).get("target_pollutant", ""))) for item in alerts)
        suffix = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:12]
        path = self.output_root / timestamp.strftime("%Y%m%d") / (
            f"xuchang-station-episode-{timestamp:%Y%m%d%H%M}-{station_id}-{suffix}.evidence.json"
        )
        primary_evidence = alerts[0].get("evidence", {}) if alerts else {}
        self._write_json(path, {
            "schema_version": "xuchang_station_deviation_episode_evidence/v1",
            "station_id": station_id,
            "occurred_at": occurred_at,
            # Keep the first alert's evidence fields at the top level for
            # backwards-compatible readers; all pollutant evidence follows
            # in the alerts array.
            **primary_evidence,
            "alerts": alerts,
            "dispatch_media": list(dict.fromkeys(
                path for item in alerts for path in item.get("evidence", {}).get("dispatch_media", [])
            )),
        })
        return path

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)
        temp_path.replace(path)

    async def run(
        self,
        target_time: datetime | None = None,
        *,
        granularity: str = "5min",
        meteorology_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Run after the source five-minute slot closes; PM2.5 is still read
        # from the most recently completed hourly record for that hour.
        if granularity not in {"5min", "hour"}:
            raise ValueError("granularity must be '5min' or 'hour'")
        target_slot = _slot(
            target_time or datetime.now(TZ_SHANGHAI),
            "hour" if granularity == "hour" else "minute",
        )
        rows, expected_station_count = self.load_station_rows(target_slot)
        target_hour = _hour(target_slot).replace(tzinfo=None)
        if granularity == "hour":
            detection_rows = [
                row for row in rows
                if row.get("data_source") == "hour"
                and _hour(row.get("data_time")) == target_hour - timedelta(hours=1)
            ]
        else:
            detection_rows = [
                row for row in rows
                if (
                    row.get("data_source") == "minute"
                    and _slot(row.get("data_time"), "minute") == target_slot
                )
                or (
                    row.get("data_source") == "hour"
                    and _hour(row.get("data_time")) == target_hour - timedelta(hours=1)
                )
            ]
        minute_trend_rows = self._minute_trend_rows(rows, target_slot) if granularity == "5min" else []
        aqi_values = [row.get("aqi") for row in detection_rows if row.get("aqi") is not None]
        air_quality_level = air_quality_level_from_aqi(max(aqi_values)) if aqi_values else None
        result = detect_station_deviations(
            detection_rows,
            expected_station_count=expected_station_count.get("hour", 0),
            expected_station_counts=expected_station_count,
            config=self.config,
            air_quality_level=air_quality_level,
        )
        if granularity == "5min":
            meteo_decision = evaluate_adverse_meteorology(meteorology_summary)
            sensitivity = meteo_decision["sensitivity"]
            result["alerts"].extend(
                detect_continuous_rises(minute_trend_rows, config=self.config, sensitivity=sensitivity)
            )
            unique: dict[str, dict[str, Any]] = {}
            for alert in result["alerts"]:
                unique[alert["event_id"]] = alert
            result["alerts"] = list(unique.values())
        events = []
        alerts_by_station: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for alert in result["alerts"]:
            alerts_by_station[str(alert.get("station_id") or "")].append(alert)
        multifactor_paths = {
            sid: self.write_multifactor_table(items, rows)
            for sid, items in alerts_by_station.items()
            if len({_observed_indicator(a.get("target_pollutant")) for a in items}) >= 2
        }
        for alert in result["alerts"]:
            # Reuse the daily review's composition model. It selects minute
            # pollutants with the matching hourly PM2.5 value when available.
            alert["pollutant_source_features"] = calculate_pollutant_source_features(
                rows,
                str(alert["station_id"]),
            )
            station = resolve_station(alert, [row for row in rows if row.get("data_source") == "hour"])
            if station:
                alert.update(lon=station["longitude"], lat=station["latitude"],
                             canonical_station_id=station["canonical_station_id"],
                             coordinate_source=station["coordinate_source"])
            chart_rows = rows
            if granularity == "5min" and alert.get("measurement_granularity") == "5min":
                chart_rows = minute_trend_rows
            chart_path = self.write_timeseries_chart(alert, chart_rows)
            if chart_path is not None:
                alert["timeseries_chart_path"] = format_agent_path(chart_path)
                alert["timeseries_chart"] = {
                    "path": alert["timeseries_chart_path"],
                    "target_pollutant": alert.get("target_pollutant"),
                    "target_station": alert.get("station_name") or alert.get("station_id"),
                    "trigger_time": alert.get("occurred_at"),
                    "annotations": ["告警触发点", "其余站点均值", "相对/绝对触发线"],
                }
            multifactor_path = multifactor_paths.get(str(alert.get("station_id") or ""))
            if multifactor_path is not None:
                alert["multifactor_table_path"] = format_agent_path(multifactor_path)
                alert["multifactor_table"] = {"path": alert["multifactor_table_path"], "pollutants": ["PM2.5", "PM10", "SO2", "NO2", "CO", "O3"]}
            path = self._write_event(alert)
            events.append({**alert, "event_json_path": format_agent_path(path)})
        return {
            "city": self.config.city,
            "target_slot": target_slot.isoformat(),
            "target_hour": target_slot.isoformat(),
            "expected_station_count": expected_station_count,
            "rows": len(rows),
            "alerts": events,
            "checks": result["checks"],
            "granularity": granularity,
            "air_quality_level": air_quality_level,
            "meteorology_decision": evaluate_adverse_meteorology(meteorology_summary),
        }

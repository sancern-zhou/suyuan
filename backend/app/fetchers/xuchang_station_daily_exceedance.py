"""Confirm prior-day pollution from published station-day data.

Restored legacy scheme: read platform-published station-day evaluation,
confirm PM2.5 / O3-8h daily exceedance, and trigger the unique Scenario 2
source-analysis job.  The reworked hourly-review fetcher
(`xuchang_station_daily_pollution_fetcher`) is kept separately; both schemes
share the idempotent Scenario 2 escalation service.

超标确认后同步抓取当天证据：NMC 许昌观测站逐时实测气象（温、湿、风、
降水）+ ERA5 再分析（边界层高度、云量），实测优先、ERA5 补充垂直结构，
并做四项确定性分析——边界层变化、云量、高湿转化（湿度 + PM2.5/PM10
细粒子占比）、辐射逆温代理判据（温度变化 + 静稳 + 晴夜），以及基于组分
占比的污染物来源类型判定（复用场景一 ``calculate_pollutant_source_
features``）。分析规则全部内嵌在证据字段中，供报告层直接引用。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pyodbc
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.xcai_station_sql import xcai_connection_string
from app.scenarios.xuchang_station_deviation.source_features import (
    calculate_pollutant_source_features,
)
from app.scenarios.xuchang_transport_escalation import XuchangTransportEscalationService
from app.scheduled_tasks.models import TaskEvent

logger = structlog.get_logger()
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
CONFIRMED_EVENT_TYPE = "xuchang.station_daily_pollution.confirmed"
REQUESTED_EVENT_TYPE = "xuchang.station_daily_source_analysis.requested"
PM25_DAILY_LIMIT = 75.0
O3_8H_DAILY_LIMIT = 160.0

# 许昌 ERA5 网格点：grid_point(34.036, 113.852)，与 city_weather_history 采集一致。
XUCHANG_ERA5_GRID_POINT = (34.0, 113.75)
# NMC 许昌观测站（实测温、湿、风、降水）。
XUCHANG_NMC_STATION_ID = "ZzMTA"

# 气象机理分析阈值（规则同步写入证据 payload，报告层不得改写）
HIGH_HUMIDITY_RH_THRESHOLD = 80.0          # 高湿小时：RH >= 80%
HIGH_HUMIDITY_LIKELY_RATIO = 0.5           # 高湿小时占比 >= 50% 且细粒子占优 → likely
HIGH_HUMIDITY_POSSIBLE_RATIO = 0.3         # 高湿小时占比 >= 30% → possible
FINE_PARTICLE_RATIO_THRESHOLD = 0.6        # PM2.5/PM10 >= 0.6 判细粒子占优
FINE_PARTICLE_MIN_SAMPLES = 3              # 细粒子比值最少样本数
INVERSION_COOLING_THRESHOLD_C = 5.0        # 夜间降温 >= 5°C
INVERSION_CALM_WIND_MS = 2.0               # 夜间平均风速 < 2 m/s 判静稳
INVERSION_CLEAR_NIGHT_CLOUD_PERCENT = 30.0  # 夜间平均云量 < 30% 判晴夜
INVERSION_LOW_BLH_M = 150.0                # 夜间边界层均值 <= 150m 判强稳定
LOW_BLH_HOUR_M = 300.0                     # BLH < 300m 计低边界层小时
NOCTURNAL_STABLE_BLH_M = 200.0             # 夜间 BLH 均值 < 200m → 稳定边界层
SHALLOW_DAY_MAX_BLH_M = 500.0              # 全天最大 BLH < 500m → 持续浅边界层
MIN_METEO_HOURS = 6                        # 少于 6 个有效小时判 insufficient_data

NOCTURNAL_HOURS = frozenset([*range(20, 24), *range(0, 7)])   # 20:00–06:59
AFTERNOON_HOURS = frozenset(range(12, 17))                     # 12:00–16:59


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _hour_of(value: Any) -> datetime | None:
    """Parse an ISO/datetime value to a naive Shanghai-local hour."""
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(TZ_SHANGHAI).replace(tzinfo=None)
    return parsed.replace(minute=0, second=0, microsecond=0)


def _series(meteo_rows: list[dict[str, Any]], key: str) -> list[tuple[datetime, float]]:
    series = []
    for row in meteo_rows:
        timestamp = _hour_of(row.get("time"))
        value = _number(row.get(key))
        if timestamp is not None and value is not None:
            series.append((timestamp, value))
    return series


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rounded(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def analyze_boundary_layer(meteo_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic boundary-layer height assessment from hourly ERA5 BLH."""
    series = _series(meteo_rows, "boundary_layer_height")
    if len(series) < MIN_METEO_HOURS:
        return {
            "status": "insufficient_data",
            "valid_hours": len(series),
            "required_hours": MIN_METEO_HOURS,
            "classification": "indeterminate",
        }
    values = [value for _, value in series]
    nocturnal = [value for timestamp, value in series if timestamp.hour in NOCTURNAL_HOURS]
    afternoon = [value for timestamp, value in series if timestamp.hour in AFTERNOON_HOURS]
    daily_max = max(values)
    nocturnal_mean = _mean(nocturnal)
    low_hours = sum(1 for value in values if value < LOW_BLH_HOUR_M)
    if daily_max < SHALLOW_DAY_MAX_BLH_M:
        classification = "persistently_shallow_boundary_layer"
    elif nocturnal_mean is not None and nocturnal_mean < NOCTURNAL_STABLE_BLH_M:
        classification = "nocturnal_stable_boundary_layer"
    else:
        classification = "normal_boundary_layer"
    return {
        "status": "calculated",
        "valid_hours": len(series),
        "unit": "m",
        "daily_min": _rounded(min(values)),
        "daily_max": _rounded(daily_max),
        "daily_mean": _rounded(_mean(values)),
        "daily_amplitude": _rounded(daily_max - min(values)),
        "nocturnal_mean": _rounded(nocturnal_mean),
        "afternoon_mean": _rounded(_mean(afternoon)),
        "low_boundary_layer_hours": low_hours,
        "low_boundary_layer_ratio": _rounded(low_hours / len(values), 3),
        "classification": classification,
        "rules": {
            "low_boundary_layer_hour": f"BLH < {LOW_BLH_HOUR_M} m",
            "persistently_shallow": f"daily_max < {SHALLOW_DAY_MAX_BLH_M} m",
            "nocturnal_stable": (
                f"nocturnal(20-07h) mean BLH < {NOCTURNAL_STABLE_BLH_M} m"
            ),
        },
    }


def analyze_cloud_cover(meteo_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic cloud-cover assessment, nocturnal values feed inversion rule."""
    series = _series(meteo_rows, "cloud_cover")
    if len(series) < MIN_METEO_HOURS:
        return {
            "status": "insufficient_data",
            "valid_hours": len(series),
            "required_hours": MIN_METEO_HOURS,
            "classification": "indeterminate",
        }
    values = [value for _, value in series]
    nocturnal = [value for timestamp, value in series if timestamp.hour in NOCTURNAL_HOURS]
    nocturnal_mean = _mean(nocturnal)
    clear_hours = sum(1 for value in values if value < INVERSION_CLEAR_NIGHT_CLOUD_PERCENT)
    if nocturnal_mean is not None and nocturnal_mean < INVERSION_CLEAR_NIGHT_CLOUD_PERCENT:
        classification = "clear_night_favoring_radiative_cooling"
    elif nocturnal_mean is not None and nocturnal_mean >= 70.0:
        classification = "cloudy_night_suppressing_radiative_cooling"
    else:
        classification = "partly_cloudy_night"
    return {
        "status": "calculated",
        "valid_hours": len(series),
        "unit": "%",
        "daily_mean": _rounded(_mean(values)),
        "nocturnal_mean": _rounded(nocturnal_mean),
        "clear_sky_hours": clear_hours,
        "overcast_hours": sum(1 for value in values if value >= 80.0),
        "classification": classification,
        "rules": {
            "clear_night": f"nocturnal(20-07h) mean cloud cover < {INVERSION_CLEAR_NIGHT_CLOUD_PERCENT}%",
            "clear_sky_hour": f"cloud cover < {INVERSION_CLEAR_NIGHT_CLOUD_PERCENT}%",
        },
    }


def analyze_high_humidity_conversion(
    meteo_rows: list[dict[str, Any]],
    station_hourly_rows: list[dict[str, Any]],
    station_id: str,
) -> dict[str, Any]:
    """Judge secondary-conversion potential from humidity plus fine-particle share.

    高湿转化判据：高湿小时（RH >= 80%）占比结合该站高湿时段 PM2.5/PM10
    细粒子占比与前体物（SO2/NO2）浓度。湿度条件满足但细粒子证据不足时
    单独分级，不冒充 likely。
    """
    rh_series = _series(meteo_rows, "relative_humidity_2m")
    humid_hours = {
        timestamp for timestamp, value in rh_series if value >= HIGH_HUMIDITY_RH_THRESHOLD
    }
    if len(rh_series) < MIN_METEO_HOURS:
        return {
            "status": "insufficient_data",
            "valid_hours": len(rh_series),
            "required_hours": MIN_METEO_HOURS,
            "classification": "indeterminate",
        }
    humid_ratio = len(humid_hours) / len(rh_series)

    fine_ratios: list[float] = []
    so2_values: list[float] = []
    no2_values: list[float] = []
    for row in station_hourly_rows:
        if str(row.get("station_id") or "") != station_id:
            continue
        timestamp = _hour_of(row.get("data_time"))
        if timestamp is None or timestamp not in humid_hours:
            continue
        pm25, pm10 = _number(row.get("pm25")), _number(row.get("pm10"))
        if None not in (pm25, pm10) and pm10 > 0:
            fine_ratios.append(pm25 / pm10)
        so2, no2 = _number(row.get("so2")), _number(row.get("no2"))
        if so2 is not None:
            so2_values.append(so2)
        if no2 is not None:
            no2_values.append(no2)
    fine_ratio_mean = _mean(fine_ratios)

    if humid_ratio >= HIGH_HUMIDITY_LIKELY_RATIO and (
        len(fine_ratios) >= FINE_PARTICLE_MIN_SAMPLES
        and fine_ratio_mean is not None
        and fine_ratio_mean >= FINE_PARTICLE_RATIO_THRESHOLD
    ):
        classification = "high_humidity_secondary_conversion_likely"
    elif humid_ratio >= HIGH_HUMIDITY_LIKELY_RATIO:
        classification = "high_humidity_without_fine_particle_evidence"
    elif humid_ratio >= HIGH_HUMIDITY_POSSIBLE_RATIO:
        classification = "possible_high_humidity_secondary_conversion"
    else:
        classification = "unlikely_high_humidity_secondary_conversion"
    return {
        "status": "calculated",
        "station_id": station_id,
        "hours_with_humidity": len(rh_series),
        "high_humidity_hours": len(humid_hours),
        "high_humidity_ratio": _rounded(humid_ratio, 3),
        "fine_particle_ratio_mean_in_humid_hours": _rounded(fine_ratio_mean, 3),
        "fine_particle_sample_count": len(fine_ratios),
        "so2_mean_in_humid_hours": _rounded(_mean(so2_values)),
        "no2_mean_in_humid_hours": _rounded(_mean(no2_values)),
        "classification": classification,
        "rules": {
            "high_humidity_hour": f"RH >= {HIGH_HUMIDITY_RH_THRESHOLD}%",
            "likely": (
                f"high humidity ratio >= {HIGH_HUMIDITY_LIKELY_RATIO} AND "
                f"PM2.5/PM10 mean >= {FINE_PARTICLE_RATIO_THRESHOLD} "
                f"with >= {FINE_PARTICLE_MIN_SAMPLES} samples"
            ),
            "possible": f"high humidity ratio >= {HIGH_HUMIDITY_POSSIBLE_RATIO}",
            "mechanism": "高湿促进 SO2/NO2 向硫酸盐/硝酸盐二次转化并吸湿增长",
        },
    }


def analyze_temperature_inversion(meteo_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Radiation-inversion proxy from surface cooling, calm wind and clear night.

    地面 2m 温度无法直接测得逆温层；本判据为过程性代理：夜间强降温 +
    静稳小风 + 晴夜少云（或夜间边界层极低）组合判辐射逆温 likely，
    满足两项判 possible。报告表述必须注明是代理判据、非探空实测。
    """
    temp_series = _series(meteo_rows, "temperature_2m")
    wind_series = _series(meteo_rows, "wind_speed_10m_ms")
    if len(temp_series) < MIN_METEO_HOURS:
        return {
            "status": "insufficient_data",
            "valid_hours": len(temp_series),
            "required_hours": MIN_METEO_HOURS,
            "classification": "indeterminate",
        }
    evening_temp = None
    for timestamp, value in temp_series:
        if timestamp.hour == 18:
            evening_temp = value
    if evening_temp is None:
        prior = [value for timestamp, value in temp_series if timestamp.hour >= 16]
        evening_temp = prior[-1] if prior else None
    nocturnal_temps = [
        value for timestamp, value in temp_series if timestamp.hour in NOCTURNAL_HOURS
    ]
    nocturnal_min = min(nocturnal_temps) if nocturnal_temps else None
    cooling = (
        evening_temp - nocturnal_min
        if None not in (evening_temp, nocturnal_min) else None
    )
    nocturnal_wind_ms = _mean([
        value for timestamp, value in wind_series if timestamp.hour in NOCTURNAL_HOURS
    ])
    cloud = analyze_cloud_cover(meteo_rows)
    nocturnal_cloud = cloud.get("nocturnal_mean")
    blh = analyze_boundary_layer(meteo_rows)
    nocturnal_blh = blh.get("nocturnal_mean")

    criteria = {
        "strong_nocturnal_cooling": (
            cooling is not None and cooling >= INVERSION_COOLING_THRESHOLD_C
        ),
        "calm_nocturnal_wind": (
            nocturnal_wind_ms is not None and nocturnal_wind_ms < INVERSION_CALM_WIND_MS
        ),
        "clear_nocturnal_sky": (
            nocturnal_cloud is not None
            and nocturnal_cloud < INVERSION_CLEAR_NIGHT_CLOUD_PERCENT
        ),
    }
    met_count = sum(1 for value in criteria.values() if value)
    strongly_stable_blh = (
        nocturnal_blh is not None
        and nocturnal_wind_ms is not None
        and nocturnal_blh <= INVERSION_LOW_BLH_M
        and nocturnal_wind_ms < INVERSION_CALM_WIND_MS
    )
    if met_count == 3 or strongly_stable_blh:
        classification = "radiation_inversion_likely"
    elif met_count == 2:
        classification = "radiation_inversion_possible"
    else:
        classification = "radiation_inversion_unlikely"
    return {
        "status": "calculated",
        "valid_hours": len(temp_series),
        "evening_temperature_c": _rounded(evening_temp),
        "nocturnal_min_temperature_c": _rounded(nocturnal_min),
        "nocturnal_cooling_c": _rounded(cooling),
        "nocturnal_mean_wind_ms": _rounded(nocturnal_wind_ms, 2),
        "nocturnal_mean_cloud_percent": nocturnal_cloud,
        "nocturnal_mean_boundary_layer_m": nocturnal_blh,
        "criteria": criteria,
        "classification": classification,
        "proxy_note": (
            "基于地面2m温度变化、静稳风速与夜间云量的辐射逆温代理判据，"
            "非探空实测逆温；夜间边界层持续低于150m且静稳时同样判likely"
        ),
        "rules": {
            "strong_cooling": f"18时温度-夜间最低温度 >= {INVERSION_COOLING_THRESHOLD_C}°C",
            "calm_wind": f"nocturnal mean wind < {INVERSION_CALM_WIND_MS} m/s",
            "clear_night": f"nocturnal mean cloud < {INVERSION_CLEAR_NIGHT_CLOUD_PERCENT}%",
            "likely": "all three criteria met, OR nocturnal BLH <= "
                      f"{INVERSION_LOW_BLH_M}m with calm wind",
            "possible": "exactly two of three criteria met",
        },
    }


def normalize_station_name(value: Any) -> str:
    """Strip status suffixes like ``（启用170929）`` for cross-source name matching."""
    text = str(value or "").strip()
    for opener, closer in (("（", "）"), ("(", ")")):
        start = text.find(opener)
        if start != -1:
            end = text.find(closer, start)
            if end != -1:
                text = text[:start] + text[end + 1:]
    return "".join(text.split())


def resolve_hourly_station_codes(
    daily_names: dict[str, str], hourly_names: dict[str, str]
) -> dict[str, str]:
    """Map platform station-day ids to zhongda hourly codes by station name.

    平台日值表与中大源小时表使用两套站点编码（如 3337A 与 1008A），
    同一物理站点名称一致，按去后缀名称建立映射；无法匹配的站点不映射。
    """
    by_name = {
        normalize_station_name(name): code for code, name in hourly_names.items()
    }
    resolved = {}
    for daily_code, daily_name in daily_names.items():
        hourly_code = by_name.get(normalize_station_name(daily_name))
        if hourly_code:
            resolved[str(daily_code)] = hourly_code
    return resolved


def merge_meteo_rows(
    observed_rows: list[dict[str, Any]], era5_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge NMC observed surface variables over ERA5 base rows.

    实测优先：温度、湿度、风速、风向、降水使用 NMC 站点实测覆盖同小时
    ERA5 值；边界层高度与云量仅有 ERA5。返回逐小时融合行与来源覆盖说明。
    """
    observed_by_hour = {
        _hour_of(row.get("time")): row
        for row in observed_rows
        if _hour_of(row.get("time")) is not None
    }
    surface_fields = (
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m_ms",
        "wind_direction_10m",
        "precipitation",
    )
    merged: dict[datetime, dict[str, Any]] = {}
    observed_hours = 0
    for row in era5_rows:
        timestamp = _hour_of(row.get("time"))
        if timestamp is None:
            continue
        item = dict(row)
        observed = observed_by_hour.pop(timestamp, None)
        if observed is not None:
            observed_hours += 1
            for field in surface_fields:
                if observed.get(field) is not None:
                    item[field] = observed[field]
        merged[timestamp] = item
    for timestamp, observed in sorted(observed_by_hour.items()):
        if timestamp not in merged:
            merged[timestamp] = dict(observed)
            observed_hours += 1
    coverage = {
        "observed_source": f"NMC许昌观测站({XUCHANG_NMC_STATION_ID})实测逐时",
        "era5_source": "ERA5再分析0.25°（边界层高度、云量及实测缺测时段补充）",
        "observed_hours": observed_hours,
        "era5_hours": len(era5_rows),
        "merged_hours": len(merged),
        "surface_variable_rule": "温度/湿度/风速/风向/降水优先取实测，缺测时用ERA5；边界层高度与云量取ERA5",
    }
    return [merged[key] for key in sorted(merged)], coverage


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


class XuchangStationDailyExceedanceFetcher(DataFetcher):
    """Read the prior day's station-day evaluation and build mechanism evidence."""

    def __init__(
        self,
        *,
        analysis_service: XuchangTransportEscalationService | None = None,
        now_factory: Callable[[], datetime] = lambda: datetime.now(TZ_SHANGHAI),
    ) -> None:
        super().__init__(
            name="xuchang_station_daily_exceedance_fetcher",
            description="许昌站点日污染超标确认、气象机理证据与场景二任务触发（原方案恢复版）",
            schedule="5 2 * * *",
            version="2.2.0",
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

    def load_station_hourly(
        self, target_date: date, station_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Load same-day hourly pollutants for alerting stations.

        中大源小时表与平台日值表站点编码不同（如 1008A ↔ 3337A），按站点
        名称建立映射后返回，行内 station_id 统一改写为平台日值表编码。
        """
        if not station_ids:
            return []
        start = datetime.combine(target_date, time.min)
        end = start + timedelta(days=1)
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT station_id, name
                FROM dbo.dat_station_day
                WHERE city_area_code = ? AND data_time >= ? AND data_time < ?
                """,
                ["411000", start, end],
            )
            daily_names = {
                str(row[0]): str(row[1] or "") for row in cursor.fetchall()
            }
            cursor.execute(
                """
                SELECT station_code, station_name, pm25, pm10, o3, no2, so2, co, time_point
                FROM dbo.dat_zhongda_station_hour
                WHERE time_point >= ? AND time_point < ?
                  AND area LIKE N'%许昌%'
                ORDER BY station_code, time_point
                """,
                [start, end],
            )
            hourly_rows = [
                {
                    "hourly_station_code": str(row[0]), "name": row[1],
                    "pm25": row[2], "pm10": row[3], "o3": row[4], "no2": row[5],
                    "so2": row[6], "co": row[7], "data_time": row[8],
                }
                for row in cursor.fetchall()
            ]
        finally:
            connection.close()

        hourly_names = {
            row["hourly_station_code"]: str(row["name"] or "")
            for row in hourly_rows
        }
        code_map = resolve_hourly_station_codes(daily_names, hourly_names)
        hourly_to_daily = {hourly: daily for daily, hourly in code_map.items()}
        alert_codes = {str(code) for code in station_ids}
        rows = []
        for row in hourly_rows:
            daily_code = hourly_to_daily.get(row["hourly_station_code"])
            if daily_code is None or daily_code not in alert_codes:
                continue
            rows.append({
                "station_id": daily_code,
                "name": row["name"],
                "pm25": row["pm25"],
                "pm10": row["pm10"],
                "o3": row["o3"],
                "no2": row["no2"],
                "so2": row["so2"],
                "co": row["co"],
                "data_time": row["data_time"],
                "data_source": "hour",
            })
        return rows

    async def load_era5_hourly(self, target_date: date) -> list[dict[str, Any]]:
        """Load hourly ERA5 rows (cloud cover, boundary layer height) for Xuchang."""
        from app.db.repositories.weather_repo import WeatherRepository

        start = datetime.combine(target_date, time.min, tzinfo=TZ_SHANGHAI)
        end = datetime.combine(target_date, time.max, tzinfo=TZ_SHANGHAI)
        lat, lon = XUCHANG_ERA5_GRID_POINT
        rows = await WeatherRepository().get_weather_data(lat, lon, start, end)
        evidence_rows = []
        for item in rows:
            timestamp = item.time
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=TZ_SHANGHAI)
            timestamp = timestamp.astimezone(TZ_SHANGHAI)
            wind_kmh = _number(item.wind_speed_10m)
            evidence_rows.append({
                "time": timestamp.isoformat(),
                "temperature_2m": _number(item.temperature_2m),
                "relative_humidity_2m": _number(item.relative_humidity_2m),
                "wind_speed_10m_kmh": wind_kmh,
                "wind_speed_10m_ms": (
                    round(wind_kmh / 3.6, 2) if wind_kmh is not None else None
                ),
                "wind_direction_10m": _number(item.wind_direction_10m),
                "precipitation": _number(item.precipitation),
                "cloud_cover": _number(item.cloud_cover),
                "boundary_layer_height": _number(item.boundary_layer_height),
            })
        return evidence_rows

    async def load_observed_hourly(self, target_date: date) -> list[dict[str, Any]]:
        """Load hourly NMC observed surface weather for the Xuchang station."""
        from app.db.repositories.weather_repo import WeatherRepository

        start = datetime.combine(target_date, time.min, tzinfo=TZ_SHANGHAI)
        end = datetime.combine(target_date, time.max, tzinfo=TZ_SHANGHAI)
        rows = await WeatherRepository().get_observed_data(
            XUCHANG_NMC_STATION_ID, start, end
        )
        evidence_rows = []
        for item in rows:
            timestamp = item.time
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=TZ_SHANGHAI)
            timestamp = timestamp.astimezone(TZ_SHANGHAI)
            wind_ms = _number(item.wind_speed_10m)
            evidence_rows.append({
                "time": timestamp.isoformat(),
                "temperature_2m": _number(item.temperature_2m),
                "relative_humidity_2m": _number(item.relative_humidity_2m),
                "wind_speed_10m_ms": wind_ms,
                "wind_direction_10m": _number(item.wind_direction_10m),
                "precipitation": _number(item.precipitation),
            })
        return evidence_rows

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory()
        target_date = now.astimezone(TZ_SHANGHAI).date() - timedelta(days=1)
        result = evaluate_station_daily_pollution(self.load_rows(target_date), target_date=target_date)
        if result["events"]:
            alert_station_ids = sorted({event["station_id"] for event in result["events"]})
            era5_rows = await self.load_era5_hourly(target_date)
            observed_rows = await self.load_observed_hourly(target_date)
            merged_rows, source_coverage = merge_meteo_rows(observed_rows, era5_rows)
            station_hourly_rows = self.load_station_hourly(target_date, alert_station_ids)
            boundary_layer_analysis = analyze_boundary_layer(merged_rows)
            cloud_cover_analysis = analyze_cloud_cover(merged_rows)
            inversion_analysis = analyze_temperature_inversion(merged_rows)
            for event in result["events"]:
                station_id = event["station_id"]
                station_rows = [
                    row for row in station_hourly_rows
                    if str(row.get("station_id")) == station_id
                ]
                event["pollutant_source_features"] = calculate_pollutant_source_features(
                    station_hourly_rows, station_id
                )
                event["meteorology_evidence"] = {
                    "status": "available" if merged_rows else "not_available",
                    "source": (
                        "NMC许昌观测站(ZzMTA)实测逐时气象 + ERA5再分析0.25°网格点"
                        "(34.0,113.75)边界层高度与云量；实测优先，ERA5补充"
                    ),
                    "source_coverage": source_coverage,
                    "observed_rows": observed_rows,
                    "rows": merged_rows,
                    "boundary_layer_analysis": boundary_layer_analysis,
                    "cloud_cover_analysis": cloud_cover_analysis,
                    "temperature_inversion_analysis": inversion_analysis,
                    "high_humidity_conversion_analysis": analyze_high_humidity_conversion(
                        merged_rows, station_hourly_rows, station_id
                    ),
                }
                concentration_column = (
                    "pm25" if event["target_pollutant"] == "PM2.5" else "o3"
                )
                event["hourly_rows"] = [
                    {
                        "time": row["data_time"].isoformat(),
                        "concentration": _number(row.get(concentration_column)),
                    }
                    for row in station_rows
                    if _number(row.get(concentration_column)) is not None
                ]
                event["station_hourly"] = [
                    {
                        key: (value.isoformat() if isinstance(value, datetime) else value)
                        for key, value in row.items()
                    }
                    for row in station_rows
                ]
                event["data_quality"] = {
                    "hourly_station_rows": len(station_rows),
                    "expected_hourly_rows": 24,
                    "hourly_completeness_ratio": round(min(len(station_rows) / 24, 1.0), 3),
                    "meteorology_hours": len(merged_rows),
                    "daily_value_status": "confirmed",
                }

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
            "xuchang_station_daily_exceedance_completed",
            target_date=result["target_date"],
            event_count=len(result["events"]),
        )
        return result

"""许昌数据大屏快照聚合 fetcher。

大屏前端不直连 Cube/SQL Server：本任务周期性把整屏数据聚合为一份
snapshot.json，web 进程的 ``/api/xuchang-dashboard/screen-snapshot``
只做文件读（3 个 uvicorn worker 共享同一份快照，同一时刻整屏一致）。

口径红线：城市/区县/乡镇数据一律经 Cube Core 语义层
（``app.tools.query.xuchang_cube_metrics.tool.cube_load``），与对话问数
同源；预报复用 OpenMeteoAirQualityForecast72h / WeatherForecast7Day
（与 ``app.api.xuchang_air_quality_routes`` 同表同口径）；告警读场景一
episode_state.json；播报读定时任务结构化结果表。

地图站点层用 5 分钟数据（2026-10-27 起）：国控站读中大平台站点
5 分钟表（XcAiDb ``dbo.dat_zhongda_station_minute``），乡镇站读
TownFiveMinute（旧云平台替代源，TownStationData 2026-10-21 起停更）。
两个 5 分钟源都不发布 AQI，气泡 AQI/首要污染物按 HJ633 由六参数
推算（aqi_estimated=True，前端标注"推算"）；区县代表点无 5 分钟源，
仍用 SsfbCountyHour 最新可用小时。

调度避开河南 ssfb 三抓取器窗口（城市 :14/:20/:55、站点 :16/:22/:57、
区县 :18/:24/:59）与乡镇 5 分钟抓取（:07/:37），且晚于整点后入库节奏；
本任务只经 Cube 常驻服务读 MySQL 与 XcAiDb 直连，不直连 Crawler MySQL。

写入必须 tmp+rename 原子替换：worker 写、多个 web worker 读同一文件。
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pyodbc
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
# 中大平台表名常量统一从 xuchang_zhongda_station 导入，避免两处字符串漂移。
# 地图国控站与实时头均用 STATION_TABLE（站点 5 分钟，中大 5 分钟口径不发布
# AQI，气泡 AQI 按 HJ633 由六参数推算）。
from app.fetchers.xuchang_zhongda_station import (
    CITY_HOUR_TABLE,
    STATION_TABLE,
)
from app.tools.query.xuchang_cube_metrics.tool import cube_load
from app.scenarios.xuchang_city_exceedance.aqi import hourly_aqi_and_primary
from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

SNAPSHOT_SCHEMA_VERSION = 2
XUCHANG_CITY = "许昌市"
# 与 app/api/xuchang_air_quality_routes.py 同源（XcAiDb WeatherForecast7Day）
XUCHANG_CITY_CODE = "411000"
# NMC 许昌观测站（backend/app/config/weather_targets.py）
MET_STATION_ID = "ZzMTA"

SNAPSHOT_DIR = "xuchang_screen_snapshot"
SNAPSHOT_FILE = "snapshot.json"

GOOD_QUALITIES = {"优", "良"}
# 已关闭但仍在窗口内的告警保留展示，供巡查人员回看
ALERT_WINDOW = timedelta(hours=24)
MAX_ALERTS = 12
MAX_TOWNSHIPS = 80

# ---------------------------------------------------------------- 轮播素材
# 各类素材最多入快照的张数；扫描结果按文件修改时间倒序取最新。
ASSET_WINDOW_DAYS = 3
ASSETS_PER_KIND = 4
# 大屏资产路由允许的扩展名白名单（详见 xuchang_dashboard_routes.asset）
ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg"}
# 素材在 registry 下的根目录（相对路径进快照，绝对路径不出后端）
TRANSPORT_OUTPUT_DIR = "xuchang_transport_analysis"
GEMS_OUTPUT_DIR = "satellite/gems/xuchang"
# 许昌 10 区县代表点（政府驻地，公开稳定坐标；仅作地图辅助层，
# 区县精确排名看左栏排名面板，不用本层做考核口径）
COUNTY_SEAT_COORDINATES: Dict[str, Dict[str, float]] = {
    "魏都区": {"lon": 113.8297, "lat": 34.0243},
    "建安区": {"lon": 113.8350, "lat": 34.1094},
    "鄢陵县": {"lon": 114.1830, "lat": 34.1030},
    "襄城县": {"lon": 113.5010, "lat": 33.8490},
    "禹州市": {"lon": 113.4880, "lat": 34.1400},
    "长葛市": {"lon": 113.7730, "lat": 34.2190},
    "东城区": {"lon": 113.8790, "lat": 34.0350},
    "开发区": {"lon": 113.7906, "lat": 33.9953},
    "示范区": {"lon": 113.8600, "lat": 34.0870},
}
# 乡镇站总数（Cube 目录口径：乡镇站 76 个，2024 起）
TOWNSHIP_TOTAL = 76


# ---------------------------------------------------------------- 工具
def _number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _int_or_none(value: Any) -> Optional[int]:
    number = _number(value)
    return int(number) if number is not None else None


def _clean_aqi(value: Any) -> Optional[int]:
    """AQI 小于等于 0 视为缺测占位（中大表未审核时段会填 0）。"""
    number = _int_or_none(value)
    return number if number is not None and number > 0 else None


def _clean_conc(value: Any) -> Optional[float]:
    """浓度负值视为缺测哨兵（-99/-99000 等）。"""
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return _text(value)


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _flat(rows: List[Dict[str, Any]], cube: str) -> List[Dict[str, Any]]:
    """把 Cube 行的 `Cube.member` 键剥离为裸成员名。"""
    result: List[Dict[str, Any]] = []
    prefix = f"{cube}."
    for row in rows:
        item: Dict[str, Any] = {}
        for key, value in row.items():
            item[key[len(prefix):] if key.startswith(prefix) else key] = value
        result.append(item)
    return result


def _hour_range(cutoff_iso: str) -> List[str]:
    """整小时闭区间 [起, 止]，用于把时间维度过滤锁定到单个小时。"""
    cutoff = _parse_dt(cutoff_iso)
    if cutoff is None:
        raise RuntimeError(f"无法解析数据截止时间: {cutoff_iso!r}")
    start = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
    end = (cutoff + timedelta(minutes=59, seconds=59)).strftime("%Y-%m-%dT%H:%M:%S")
    return [start, end]


def _minute_range(cutoff_iso: str) -> List[str]:
    """5 分钟槽闭区间 [起, 止]，用于把时间维度过滤锁定到单个 5 分钟槽。"""
    cutoff = _parse_dt(cutoff_iso)
    if cutoff is None:
        raise RuntimeError(f"无法解析数据截止时间: {cutoff_iso!r}")
    start = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
    end = (cutoff + timedelta(minutes=4, seconds=59)).strftime("%Y-%m-%dT%H:%M:%S")
    return [start, end]


def _month_end(month_text: str) -> date:
    year, month = (int(part) for part in month_text.split("-"))
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


class XuchangScreenSnapshotFetcher(DataFetcher):
    """聚合许昌数据大屏全屏快照并物化到 data registry。"""

    def __init__(self, now_factory: Callable[[], datetime] = datetime.now) -> None:
        super().__init__(
            name="xuchang_screen_snapshot_fetcher",
            description="许昌数据大屏快照聚合（Cube 语义层+预报表+告警/播报）",
            schedule="6-56/5 * * * *",
            version="1.0.0",
        )
        self.now_factory = now_factory

    # ------------------------------------------------------------ 主流程
    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory().replace(microsecond=0)
        errors: Dict[str, str] = {}

        cutoff = await self._guarded("cutoff", errors, self._detect_cutoff_hour)
        header = city_rank = county_rank = trend = None
        if cutoff:
            header = await self._guarded("header", errors, lambda: self._header(cutoff))
            city_rank = await self._guarded(
                "city_hour_rank", errors, lambda: self._city_hour_rank(cutoff)
            )
            county_rank = await self._guarded(
                "county_hour_rank", errors, lambda: self._county_hour_rank(cutoff)
            )
            trend = await self._guarded(
                "city_trend_24h", errors, lambda: self._city_trend_24h(cutoff)
            )

        forecast = await self._guarded(
            "forecast_72h", errors, lambda: asyncio.to_thread(self._forecast_72h)
        )
        year_target = await self._guarded(
            "year_target", errors, lambda: self._year_target(now.date())
        )
        alerts = await self._guarded(
            "alerts", errors, lambda: asyncio.to_thread(self._alerts)
        )
        broadcast = await self._guarded(
            "broadcast", errors, lambda: asyncio.to_thread(self._broadcast)
        )

        alert_names = {
            name
            for item in (alerts or [])
            if (name := _text(item.get("station_name")))
        }
        stations = await self._guarded(
            "stations", errors, lambda: self._stations(alert_names)
        )
        assets = await self._guarded(
            "assets", errors, lambda: asyncio.to_thread(self._assets)
        )
        rank168 = await self._guarded("rank168", errors, self._rank168)
        minute = await self._guarded(
            "minute", errors, lambda: asyncio.to_thread(self._minute_latest)
        )
        quality = await self._guarded("quality", errors, self._quality)

        # 左侧统计/考核/排名段（官方定版为主）与右侧 NMC 气象预报段
        city_period_stats = await self._guarded(
            "city_period_stats", errors, lambda: self._city_period_stats(now.date())
        )
        province_city_ranking = await self._guarded(
            "province_city_ranking", errors, self._province_city_ranking
        )
        city_year_target_official = await self._guarded(
            "city_year_target_official", errors, self._city_year_target_official
        )
        county_year_targets = await self._guarded(
            "county_year_targets", errors, self._county_year_targets
        )
        rank168_series = await self._guarded("rank168_series", errors, self._rank168_series)
        county_month_report = await self._guarded(
            "county_month_report", errors, self._county_month_report
        )
        nmc_forecast = await self._guarded(
            "nmc_forecast", errors, lambda: asyncio.to_thread(self._nmc_forecast)
        )

        station_data_times = [
            _text(item.get("data_time"))
            for layer in (stations or {}).values()
            for item in (layer or [])
            if _text(item.get("data_time"))
        ]
        latest_station_time = max(station_data_times, default=None)
        snapshot = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "generated_at": now.isoformat(),
            "data_cutoff_hour": cutoff,
            "latest_station_time": latest_station_time,
            "header": header,
            "city_hour_rank": city_rank,
            "county_hour_rank": county_rank,
            "city_trend_24h": trend,
            "forecast_72h": forecast,
            "year_target": year_target,
            "alerts": alerts,
            "broadcast": broadcast,
            "stations": stations,
            "assets": assets,
            "rank168": rank168,
            "minute": minute,
            "quality": quality,
            "city_period_stats": city_period_stats,
            "province_city_ranking": province_city_ranking,
            "city_year_target_official": city_year_target_official,
            "county_year_targets": county_year_targets,
            "rank168_series": rank168_series,
            "county_month_report": county_month_report,
            "nmc_forecast": nmc_forecast,
            "errors": errors or None,
        }
        path = self._write_snapshot(snapshot)

        result = {
            "generated_at": now.isoformat(),
            "data_cutoff_hour": cutoff,
            "path": str(path),
            "bytes": path.stat().st_size,
            "alerts": len(alerts or []),
            "stations": len((stations or {}).get("national", []))
            + len((stations or {}).get("townships", [])),
            "assets": len(assets or []),
            "segments_failed": sorted(errors),
        }
        logger.info("xuchang_screen_snapshot_completed", **result)
        return result

    async def _guarded(self, segment: str, errors: Dict[str, str], factory) -> Any:
        """单段失败置 null 并记错误，整屏不因一段挂掉。"""
        try:
            return await factory()
        except Exception as exc:
            errors[segment] = str(exc)
            logger.warning(
                "xuchang_screen_snapshot_segment_failed",
                segment=segment,
                error=str(exc),
            )
            return None

    def _write_snapshot(self, snapshot: dict[str, Any]) -> Path:
        directory = get_data_registry() / SNAPSHOT_DIR
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / SNAPSHOT_FILE
        temp = directory / f"{SNAPSHOT_FILE}.tmp"
        temp.write_text(
            json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
        )
        temp.replace(target)
        return target

    # ------------------------------------------------------------ 实时段
    async def _detect_cutoff_hour(self) -> str:
        now = self.now_factory()
        start = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:00:00")
        end = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:00:00")
        rows = await cube_load({
            "measures": ["SsfbCityHour.count"],
            "dimensions": ["SsfbCityHour.dataTime"],
            "timeDimensions": [{
                "dimension": "SsfbCityHour.dataTime",
                "dateRange": [start, end],
            }],
            "filters": [{
                "member": "SsfbCityHour.city",
                "operator": "equals",
                "values": [XUCHANG_CITY],
            }],
            "order": {"SsfbCityHour.dataTime": "desc"},
            "limit": 1,
        })
        for row in rows:
            value = _text(row.get("SsfbCityHour.dataTime"))
            if value:
                return value
        raise RuntimeError("近3小时 SsfbCityHour 无许昌数据（ssfb 采集未入库？）")

    async def _header(self, cutoff_iso: str) -> dict[str, Any]:
        rows = await cube_load({
            "measures": [
                "SsfbCityHour.maxAqi", "SsfbCityHour.avgPm25", "SsfbCityHour.avgPm10",
                "SsfbCityHour.avgO3", "SsfbCityHour.avgNo2", "SsfbCityHour.avgSo2",
                "SsfbCityHour.avgCo",
            ],
            "dimensions": ["SsfbCityHour.quality", "SsfbCityHour.primaryPollutant"],
            "timeDimensions": [{
                "dimension": "SsfbCityHour.dataTime",
                "dateRange": _hour_range(cutoff_iso),
            }],
            "filters": [{
                "member": "SsfbCityHour.city",
                "operator": "equals",
                "values": [XUCHANG_CITY],
            }],
            "limit": 1,
        })
        if not rows:
            raise RuntimeError(f"许昌城市小时数据缺失: {cutoff_iso}")
        row = _flat(rows, "SsfbCityHour")[0]
        return {
            "city": XUCHANG_CITY,
            "data_time": cutoff_iso,
            "aqi": _int_or_none(row.get("maxAqi")),
            "quality": _text(row.get("quality")),
            "primary_pollutant": _text(row.get("primaryPollutant")),
            "pm25": _number(row.get("avgPm25")),
            "pm10": _number(row.get("avgPm10")),
            "o3": _number(row.get("avgO3")),
            "no2": _number(row.get("avgNo2")),
            "so2": _number(row.get("avgSo2")),
            "co": _number(row.get("avgCo")),
            "met": await self._observed_met(),
        }

    async def _observed_met(self) -> Optional[dict[str, Any]]:
        """NMC 许昌站最近一条实况气象（大屏头部要素）。"""
        from sqlalchemy import select

        from app.db.models import ObservedWeatherData
        from app.db.weather_database import weather_async_session

        window_start = self.now_factory() - timedelta(hours=6)

        try:
            async with weather_async_session() as session:
                stmt = (
                    select(ObservedWeatherData)
                    .where(
                        ObservedWeatherData.station_id == MET_STATION_ID,
                        ObservedWeatherData.time >= window_start,
                    )
                    .order_by(ObservedWeatherData.time.desc())
                    .limit(1)
                )
                row = (await session.execute(stmt)).scalars().first()
        except Exception as exc:
            logger.warning("xuchang_screen_snapshot_met_failed", error=str(exc))
            return None
        if row is None:
            return None
        return {
            "time": _iso(row.time),
            "temperature": row.temperature_2m,
            "humidity": row.relative_humidity_2m,
            "wind_speed": row.wind_speed_10m,
            "wind_direction": row.wind_direction_10m,
        }

    # ------------------------------------------------------------ 排名段
    async def _city_hour_rank(self, cutoff_iso: str) -> dict[str, Any]:
        rows = await cube_load({
            "measures": [
                "SsfbCityHourRank.rankAqi", "SsfbCityHourRank.avgAqi",
                "SsfbCityHourRank.avgPm25", "SsfbCityHourRank.avgPm10",
            ],
            "dimensions": [
                "SsfbCityHourRank.city", "SsfbCityHourRank.quality",
                "SsfbCityHourRank.primaryPollutant",
            ],
            "timeDimensions": [{
                "dimension": "SsfbCityHourRank.dataTime",
                "dateRange": _hour_range(cutoff_iso),
            }],
            "order": {"SsfbCityHourRank.rankAqi": "asc"},
            "limit": 20,
        })
        return {
            "data_time": cutoff_iso,
            "rows": [
                {
                    "city": _text(item.get("city")),
                    "rank": _int_or_none(item.get("rankAqi")),
                    "aqi": _int_or_none(item.get("avgAqi")),
                    "pm25": _number(item.get("avgPm25")),
                    "quality": _text(item.get("quality")),
                    "primary": _text(item.get("primaryPollutant")),
                }
                for item in _flat(rows, "SsfbCityHourRank")
            ],
        }

    async def _county_hour_rank(self, cutoff_iso: str) -> dict[str, Any]:
        rows = await cube_load({
            "measures": [
                "SsfbCountyHourRank.rankAqi", "SsfbCountyHourRank.avgAqi",
                "SsfbCountyHourRank.avgPm25",
            ],
            "dimensions": [
                "SsfbCountyHourRank.county", "SsfbCountyHourRank.quality",
                "SsfbCountyHourRank.primaryPollutant",
            ],
            "timeDimensions": [{
                "dimension": "SsfbCountyHourRank.dataTime",
                "dateRange": _hour_range(cutoff_iso),
            }],
            "filters": [{
                "member": "SsfbCountyHourRank.city",
                "operator": "equals",
                "values": [XUCHANG_CITY],
            }],
            "order": {"SsfbCountyHourRank.rankAqi": "asc"},
            "limit": 15,
        })
        return {
            "data_time": cutoff_iso,
            "rows": [
                {
                    "county": _text(item.get("county")),
                    "rank": _int_or_none(item.get("rankAqi")),
                    "aqi": _int_or_none(item.get("avgAqi")),
                    "pm25": _number(item.get("avgPm25")),
                    "quality": _text(item.get("quality")),
                    "primary": _text(item.get("primaryPollutant")),
                }
                for item in _flat(rows, "SsfbCountyHourRank")
            ],
        }

    # ------------------------------------------------------------ 趋势/预报段
    async def _city_trend_24h(self, cutoff_iso: str) -> dict[str, Any]:
        cutoff = _parse_dt(cutoff_iso)
        if cutoff is None:
            raise RuntimeError(f"无法解析数据截止时间: {cutoff_iso!r}")
        start = cutoff - timedelta(hours=23)
        rows = await cube_load({
            "measures": [
                "SsfbCityHour.maxAqi", "SsfbCityHour.avgPm25",
                "SsfbCityHour.avgPm10", "SsfbCityHour.avgO3",
            ],
            "dimensions": ["SsfbCityHour.dataTime"],
            "timeDimensions": [{
                "dimension": "SsfbCityHour.dataTime",
                "dateRange": [
                    start.strftime("%Y-%m-%dT%H:00:00"),
                    (cutoff + timedelta(minutes=59, seconds=59)).strftime("%Y-%m-%dT%H:%M:%S"),
                ],
            }],
            "filters": [{
                "member": "SsfbCityHour.city",
                "operator": "equals",
                "values": [XUCHANG_CITY],
            }],
            "order": {"SsfbCityHour.dataTime": "asc"},
            "limit": 48,
        })
        return {
            "rows": [
                {
                    "data_time": _iso(item.get("dataTime")),
                    "aqi": _int_or_none(item.get("maxAqi")),
                    "pm25": _number(item.get("avgPm25")),
                    "pm10": _number(item.get("avgPm10")),
                    "o3": _number(item.get("avgO3")),
                }
                for item in _flat(rows, "SsfbCityHour")
            ],
        }

    def _forecast_72h(self) -> dict[str, Any]:
        """72h 逐时预报 + 5 日预报（与 xuchang_air_quality_routes 同表同口径）。"""
        from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client

        now = self.now_factory()
        client = get_sql_server_client()
        connection = pyodbc.connect(client.connection_string, timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT forecast_time, aqi, pm25
                FROM dbo.OpenMeteoAirQualityForecast72h
                WHERE city_key = ? AND forecast_time >= ?
                ORDER BY forecast_time ASC
                """,
                "xuchang",
                (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            )
            columns = [column[0] for column in cursor.description]
            hourly = [
                {
                    "data_time": _iso(value.get("forecast_time")),
                    "aqi": _clean_aqi(value.get("aqi")),
                    "pm25": _clean_conc(value.get("pm25")),
                }
                for value in (dict(zip(columns, row)) for row in cursor.fetchall())
            ]
            daily = self._load_daily_forecasts(cursor, now.date())
        finally:
            connection.close()
        return {"hourly": hourly, "daily": daily}

    def _load_daily_forecasts(
        self, cursor: pyodbc.Cursor, today: date, days: int = 5
    ) -> List[dict[str, Any]]:
        """XcAiDb WeatherForecast7Day 最近批次中的未来 N 日预报。"""
        cursor.execute(
            """
            SELECT TimePoint, MinAqi, MaxAqi, MaxPollution
            FROM dbo.WeatherForecast7Day
            WHERE CityCode = ?
              AND UpdateDate = (
                  SELECT MAX(UpdateDate) FROM dbo.WeatherForecast7Day AS latest
                  WHERE latest.CityCode = ?
              )
            ORDER BY TimePoint ASC
            """,
            XUCHANG_CITY_CODE,
            XUCHANG_CITY_CODE,
        )
        columns = [column[0] for column in cursor.description]
        batch = [dict(zip(columns, row)) for row in cursor.fetchall()]
        upcoming = [
            row for row in batch
            if isinstance(row.get("TimePoint"), datetime)
            and row["TimePoint"].date() >= today
        ]
        selected = upcoming if len(upcoming) >= days else batch[-days:]
        daily = []
        for row in selected[-days:]:
            min_aqi = _number(row.get("MinAqi"))
            max_aqi = _number(row.get("MaxAqi"))
            if min_aqi is not None and max_aqi is not None:
                aqi = round((min_aqi + max_aqi) / 2)
            else:
                aqi = min_aqi if min_aqi is not None else max_aqi
            daily.append({
                "date": row["TimePoint"].date().isoformat()
                if isinstance(row.get("TimePoint"), datetime) else None,
                "min_aqi": min_aqi,
                "max_aqi": max_aqi,
                "aqi": _int_or_none(aqi),
                "primary_pollutant": _text(row.get("MaxPollution")),
            })
        return daily

    # ------------------------------------------------------------ 达标段
    async def _year_target(self, today: date) -> dict[str, Any]:
        year = str(today.year)

        # 年度目标（许昌市定版表，目标值全库唯一来源）
        target_rows = await cube_load({
            "measures": [
                "XuchangCityYearTarget.pm25Target", "XuchangCityYearTarget.pm10Target",
                "XuchangCityYearTarget.goodDaysTarget", "XuchangCityYearTarget.heavyDaysTarget",
            ],
            "dimensions": ["XuchangCityYearTarget.year"],
            "filters": [{
                "member": "XuchangCityYearTarget.year",
                "operator": "equals",
                "values": [year],
            }],
            "limit": 1,
        })
        targets = _flat(target_rows, "XuchangCityYearTarget")[0] if target_rows else {}

        # 官方累计（省月报 1-N 月，剔沙尘口径，城市级许昌行）
        official_rows = await cube_load({
            "measures": [
                "ProvinceMonthCum.pm25", "ProvinceMonthCum.pm10",
                "ProvinceMonthCum.goodDays", "ProvinceMonthCum.heavyDays",
                "ProvinceMonthCum.goodDaysRatio",
            ],
            "dimensions": ["ProvinceMonthCum.dataMonth"],
            "filters": [
                {"member": "ProvinceMonthCum.level", "operator": "equals", "values": ["city"]},
                {"member": "ProvinceMonthCum.region", "operator": "equals", "values": [XUCHANG_CITY]},
            ],
            "order": {"ProvinceMonthCum.dataMonth": "desc"},
            "limit": 1,
        })
        official = _flat(official_rows, "ProvinceMonthCum")[0] if official_rows else {}
        official_month = _text(official.get("dataMonth"))
        official_month = official_month[:7] if official_month else None

        # 官方期次之后的时段用本地日值自算（SsfbCityDay 自 2026-10-03 起有数据，
        # 未剔沙尘，面板需标注口径），不与官方值混算成单一进度数
        local = None
        if official_month:
            local_from = _month_end(official_month) + timedelta(days=1)
            local_to = today - timedelta(days=1)
            if local_to >= local_from:
                local = await self._local_good_days(local_from, local_to)

        return {
            "year": today.year,
            "targets": {
                "pm25": _number(targets.get("pm25Target")),
                "pm10": _number(targets.get("pm10Target")),
                "good_days": _int_or_none(targets.get("goodDaysTarget")),
                "heavy_days": _int_or_none(targets.get("heavyDaysTarget")),
            },
            "official_cum": {
                "as_of_month": official_month,
                "pm25": _number(official.get("pm25")),
                "pm10": _number(official.get("pm10")),
                "good_days": _int_or_none(official.get("goodDays")),
                "heavy_days": _int_or_none(official.get("heavyDays")),
                "good_days_ratio": _number(official.get("goodDaysRatio")),
            },
            "local_since_official": local,
        }

    async def _local_good_days(self, from_day: date, to_day: date) -> dict[str, Any]:
        rows = await cube_load({
            "measures": ["SsfbCityDay.count", "SsfbCityDay.avgPm25"],
            "dimensions": ["SsfbCityDay.quality"],
            "timeDimensions": [{
                "dimension": "SsfbCityDay.dataDate",
                "dateRange": [from_day.isoformat(), to_day.isoformat()],
            }],
            "filters": [{
                "member": "SsfbCityDay.city",
                "operator": "equals",
                "values": [XUCHANG_CITY],
            }],
            "limit": 10,
        })
        good_days = 0
        days_total = 0
        weighted_pm25 = 0.0
        for item in _flat(rows, "SsfbCityDay"):
            count = int(item.get("count") or 0)
            days_total += count
            if _text(item.get("quality")) in GOOD_QUALITIES:
                good_days += count
            pm25 = _number(item.get("avgPm25"))
            if pm25 is not None:
                weighted_pm25 += pm25 * count
        return {
            "from": from_day.isoformat(),
            "to": to_day.isoformat(),
            "good_days": good_days,
            "days_total": days_total,
            "pm25_avg": round(weighted_pm25 / days_total, 1)
            if days_total and weighted_pm25 else None,
        }

    # ------------------------------------------------------------ 告警/播报段
    def _alerts(self) -> List[dict[str, Any]]:
        """活跃告警 + 24h 内关闭的告警（场景一 episode_state.json）。"""
        from app.scenarios.xuchang_daily_review.episodes import (
            iter_episodes,
            load_episode_state,
        )
        from app.tools.xuchang.station_catalog.coordinates import (
            load_station_coordinates,
            normalize_station_name,
        )

        registry = get_data_registry()
        state = load_episode_state(
            registry / "xuchang_station_deviation_alerts" / "episode_state.json"
        )
        coordinates = load_station_coordinates()
        window_start = self.now_factory() - ALERT_WINDOW

        def coerce_naive(value: Optional[datetime]) -> Optional[datetime]:
            if value is not None and value.tzinfo is not None:
                return value.astimezone().replace(tzinfo=None)
            return value

        alerts: List[dict[str, Any]] = []
        for episode in iter_episodes(state):
            status = _text(episode.get("status")) or "unknown"
            last_seen = coerce_naive(
                _parse_dt(episode.get("last_seen_at") or episode.get("started_at"))
            )
            if status != "active" and (last_seen is None or last_seen < window_start):
                continue
            station_name = _text(episode.get("station_name")) or _text(episode.get("station_id"))
            coord = (
                coordinates.get(normalize_station_name(station_name))
                if station_name else None
            )
            alerts.append({
                "episode_id": _text(episode.get("episode_id")),
                "station_id": _text(episode.get("station_id")),
                "station_name": station_name,
                "target_pollutant": _text(episode.get("target_pollutant")),
                "alert_type": _text(episode.get("alert_type")),
                "status": status,
                "started_at": _text(episode.get("started_at")),
                "last_seen_at": _text(episode.get("last_seen_at")),
                "hour_count": _int_or_none(episode.get("hour_count")),
                "peak_station_value": _number(episode.get("peak_station_value")),
                "peak_deviation_ratio": _number(episode.get("peak_deviation_ratio")),
                "lon": _number(coord.get("longitude")) if coord else None,
                "lat": _number(coord.get("latitude")) if coord else None,
            })
        # 时间倒序后稳定排序：活跃在前
        alerts.sort(key=lambda item: item["last_seen_at"] or "", reverse=True)
        alerts.sort(key=lambda item: item["status"] != "active")
        return alerts[:MAX_ALERTS]

    def _broadcast(self) -> List[dict[str, Any]]:
        """最近定时任务结论/广播（结构化结果表，completed_at 倒序）。"""
        from app.scheduled_tasks.storage.task_result_storage_db import (
            DatabaseTaskResultStorage,
        )

        # _broadcast 由 asyncio.to_thread 调度，当前线程没有运行中的事件循环；
        # 显式经同步桥专用线程池执行，避免 asyncio.run 创建独立连接后在
        # bridge_session 的常驻事件循环上复用（asyncpg 跨 loop 报错）。
        from app.db.sync_bridge import run_db

        records, _total = DatabaseTaskResultStorage(runner=run_db).query_page(
            page=1, page_size=10
        )
        rows = []
        for record in records:
            text = _text(record.broadcast_message) or _text(record.conclusion) or ""
            if not text:
                continue
            if len(text) > 160:
                text = text[:160] + "…"
            moment = record.completed_at or record.started_at
            rows.append({
                "time": _iso(moment),
                "task_name": _text(record.task_name),
                "station_name": _text(record.station_name),
                "text": text,
            })
        return rows

    # ------------------------------------------------------------ 地图站点段
    async def _stations(self, alert_names: set[str]) -> dict[str, Any]:
        national = await asyncio.to_thread(self._national_stations, alert_names)
        townships = await self._township_stations()
        shengkong = await self._shengkong_stations()
        office = await self._office_stations()
        # counties（区县代表点）已从地图下线（2026-11-23 改为真实省控/办事处站），
        # 但 FieldWatchView 的"区县实况"面板仍消费该段，保留在快照中
        counties = await self._county_stations()
        return {
            "national": national,
            "townships": townships,
            "shengkong": shengkong,
            "office": office,
            "counties": counties,
        }

    async def _county_stations(self) -> List[dict[str, Any]]:
        """区县代表点：内置驻地坐标 + SsfbCountyHour 最新小时值。

        坐标是区县政府驻地代表点而非站点位置；考核排名看排名面板。
        最新小时先探测：ssfb 入库可能滞后于墙钟整点，直接锁当前小时
        会整层查空。
        """
        now = self.now_factory()
        probe = await cube_load({
            "measures": ["SsfbCountyHour.count"],
            "dimensions": ["SsfbCountyHour.dataTime"],
            "timeDimensions": [{
                "dimension": "SsfbCountyHour.dataTime",
                "dateRange": [
                    (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:00:00"),
                    (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:00:00"),
                ],
            }],
            "filters": [{
                "member": "SsfbCountyHour.city",
                "operator": "equals",
                "values": [XUCHANG_CITY],
            }],
            "order": {"SsfbCountyHour.dataTime": "desc"},
            "limit": 1,
        })
        latest_time = _text(probe[0].get("SsfbCountyHour.dataTime")) if probe else None
        if not latest_time:
            return []
        rows = await cube_load({
            "measures": [
                "SsfbCountyHour.maxAqi", "SsfbCountyHour.avgPm25",
                "SsfbCountyHour.avgPm10", "SsfbCountyHour.avgO3",
                "SsfbCountyHour.avgSo2", "SsfbCountyHour.avgNo2",
                "SsfbCountyHour.avgCo",
            ],
            "dimensions": [
                "SsfbCountyHour.county", "SsfbCountyHour.quality",
                "SsfbCountyHour.primaryPollutant",
            ],
            "timeDimensions": [{
                "dimension": "SsfbCountyHour.dataTime",
                "dateRange": _hour_range(latest_time),
            }],
            "filters": [{
                "member": "SsfbCountyHour.city",
                "operator": "equals",
                "values": [XUCHANG_CITY],
            }],
            "limit": 15,
        })
        values = {
            _text(item.get("county")): item
            for item in _flat(rows, "SsfbCountyHour")
        }
        stations = []
        for county, coord in COUNTY_SEAT_COORDINATES.items():
            item = values.get(county)
            if item is None:
                continue
            stations.append({
                "station_name": county,
                "type": "county",
                "lon": coord["lon"],
                "lat": coord["lat"],
                "aqi": _int_or_none(item.get("maxAqi")),
                "pm25": _number(item.get("avgPm25")),
                "pm10": _number(item.get("avgPm10")),
                "o3": _number(item.get("avgO3")),
                "so2": _number(item.get("avgSo2")),
                "no2": _number(item.get("avgNo2")),
                "co": _number(item.get("avgCo")),
                "quality": _text(item.get("quality")),
                "primary": _text(item.get("primaryPollutant")),
            })
        return stations

    def _latest_hour_iso(self) -> str:
        """最近整点（本地时间），供区县段锁定时段；cutoff 探测失败时兜底。"""
        now = self.now_factory().replace(minute=0, second=0, microsecond=0)
        return now.strftime("%Y-%m-%dT%H:%M:%S")

    def _national_stations(self, alert_names: set[str]) -> List[dict[str, Any]]:
        """国控站点位（内置坐标）+ 中大平台 5 分钟值。

        5 分钟口径不发布 AQI（列恒 0），气泡 AQI/首要污染物按 HJ633
        由六参数推算（aqi_estimated=True，前端标注"推算"）。
        """
        from app.scenarios.xuchang_city_exceedance.station_catalog import (
            NATIONAL_STATION_META,
        )
        from app.tools.xuchang.station_catalog.coordinates import normalize_station_name
        from app.tools.query.query_xcai_city_history.sql_client import (
            get_sql_server_client,
        )

        now = self.now_factory()
        client = get_sql_server_client()
        connection = pyodbc.connect(client.connection_string, timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP 80 station_name, time_point, aqi, pm25, pm10, o3, so2, no2, co
                FROM {STATION_TABLE}
                WHERE time_point >= ? AND aqi IS NOT NULL
                ORDER BY time_point DESC,
                  CASE parameter_type WHEN 'Act' THEN 0 WHEN 'App' THEN 1 ELSE 2 END,
                  id DESC
                """,
                (now - timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S"),
            )
            columns = [column[0] for column in cursor.description]
            raw = [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            connection.close()

        # 同站多参数行去重，保留最新 time_point 的首条
        latest: Dict[str, dict[str, Any]] = {}
        for row in raw:
            key = normalize_station_name(row.get("station_name"))
            if key and key not in latest:
                latest[key] = row

        alert_keys = {normalize_station_name(name) for name in alert_names}

        stations = []
        for code, meta in NATIONAL_STATION_META.items():
            name_key = normalize_station_name(meta["name"])
            row = latest.get(name_key)
            if not row:
                continue
            conc = {
                "so2": _clean_conc(row.get("so2")),
                "no2": _clean_conc(row.get("no2")),
                "o3": _clean_conc(row.get("o3")),
                "co": _clean_conc(row.get("co")),
                "pm10": _clean_conc(row.get("pm10")),
                "pm25": _clean_conc(row.get("pm25")),
            }
            aqi = _clean_aqi(row.get("aqi"))
            primary = None
            estimated = False
            if aqi is None:
                # 5 分钟口径不发布 AQI（列恒 0）；按 HJ633 由六参数补算
                est_aqi, est_primary = hourly_aqi_and_primary(conc)
                if est_aqi is not None:
                    aqi = int(round(est_aqi))
                    primary = est_primary
                    estimated = True
            stations.append({
                "station_id": code,
                "station_name": meta["name"],
                "type": "national",
                "lon": meta["lon"],
                "lat": meta["lat"],
                "data_time": _iso(row.get("time_point")),
                "aqi": aqi,
                "pm25": conc["pm25"],
                "pm10": conc["pm10"],
                "o3": conc["o3"],
                "so2": conc["so2"],
                "no2": conc["no2"],
                "co": conc["co"],
                "primary": primary,
                "aqi_estimated": estimated,
                "alerting": name_key in alert_keys,
            })
        return stations

    async def _township_stations(self) -> List[dict[str, Any]]:
        """乡镇站点位（TSV 坐标）+ TownFiveMinute 最新 5 分钟值。

        旧云平台替代源（TownStationData 2026-10-21 起停更），原始未审核
        口径；5 分钟不发布 AQI，气泡 AQI 按 HJ633 由六参数推算并标注。
        """
        from app.tools.xuchang.station_catalog.catalog import load_township_coordinates
        from app.tools.xuchang.station_catalog.coordinates import normalize_station_name

        now = self.now_factory()
        start = (now - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S")
        end = (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        probe = await cube_load({
            "measures": ["TownFiveMinute.count"],
            "dimensions": ["TownFiveMinute.dataTime"],
            "timeDimensions": [{
                "dimension": "TownFiveMinute.dataTime",
                "dateRange": [start, end],
            }],
            "order": {"TownFiveMinute.dataTime": "desc"},
            "limit": 1,
        })
        latest_time = _text(probe[0].get("TownFiveMinute.dataTime")) if probe else None
        if not latest_time:
            return []
        rows = await cube_load({
            "measures": [
                "TownFiveMinute.avgPm25", "TownFiveMinute.avgPm10",
                "TownFiveMinute.avgSo2", "TownFiveMinute.avgNo2",
                "TownFiveMinute.avgCo", "TownFiveMinute.avgO3",
                "TownFiveMinute.maxAqi",
            ],
            "dimensions": ["TownFiveMinute.stationName"],
            "timeDimensions": [{
                "dimension": "TownFiveMinute.dataTime",
                "dateRange": _minute_range(latest_time),
            }],
            "order": {"TownFiveMinute.avgPm25": "desc"},
            "limit": MAX_TOWNSHIPS,
        })
        coordinates = load_township_coordinates()
        stations = []
        for item in _flat(rows, "TownFiveMinute"):
            name = _text(item.get("stationName"))
            if not name:
                continue
            coord = coordinates.get(normalize_station_name(name))
            if not coord:
                continue
            conc = {
                "so2": _clean_conc(item.get("avgSo2")),
                "no2": _clean_conc(item.get("avgNo2")),
                "o3": _clean_conc(item.get("avgO3")),
                "co": _clean_conc(item.get("avgCo")),
                "pm10": _clean_conc(item.get("avgPm10")),
                "pm25": _clean_conc(item.get("avgPm25")),
            }
            # 5 分钟口径不发布 AQI，按 HJ633 由六参数推算
            est_aqi, est_primary = hourly_aqi_and_primary(conc)
            stations.append({
                "station_name": name,
                "type": "township",
                "caliber": "src",
                "lon": coord["longitude"],
                "lat": coord["latitude"],
                "data_time": latest_time,
                "aqi": int(round(est_aqi)) if est_aqi is not None else None,
                "aqi_estimated": est_aqi is not None,
                "primary": est_primary,
                "pm25": conc["pm25"],
                "pm10": conc["pm10"],
                "o3": conc["o3"],
                "so2": conc["so2"],
                "no2": conc["no2"],
                "co": conc["co"],
            })
        return stations

    async def _shengkong_stations(self) -> List[dict[str, Any]]:
        """省控站点位（平台 listMap 坐标）+ ShengkongHour 最新小时值。

        旧云平台省控站（tstype=3，8 站；襄城县政府/鄢陵县县政府自
        2026-04 起通讯中断，其余 6 站正常报数）。平台省控仅小时粒度
        （5 分钟各因子集均无数据），气泡 AQI 按 HJ633 由六参数推算并标注。
        """
        from app.tools.xuchang.station_catalog.catalog import load_shengkong_coordinates
        from app.tools.xuchang.station_catalog.coordinates import normalize_station_name

        now = self.now_factory()
        start = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:00:00")
        end = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:00:00")
        probe = await cube_load({
            "measures": ["ShengkongHour.count"],
            "dimensions": ["ShengkongHour.dataTime"],
            "timeDimensions": [{
                "dimension": "ShengkongHour.dataTime",
                "dateRange": [start, end],
            }],
            "order": {"ShengkongHour.dataTime": "desc"},
            "limit": 1,
        })
        latest_time = _text(probe[0].get("ShengkongHour.dataTime")) if probe else None
        if not latest_time:
            return []
        rows = await cube_load({
            "measures": [
                "ShengkongHour.avgPm25", "ShengkongHour.avgPm10",
                "ShengkongHour.avgSo2", "ShengkongHour.avgNo2",
                "ShengkongHour.avgCo", "ShengkongHour.avgO3",
            ],
            "dimensions": ["ShengkongHour.stationName"],
            "timeDimensions": [{
                "dimension": "ShengkongHour.dataTime",
                "dateRange": _hour_range(latest_time),
            }],
            "order": {"ShengkongHour.avgPm25": "desc"},
            "limit": 10,
        })
        coordinates = load_shengkong_coordinates()
        stations = []
        for item in _flat(rows, "ShengkongHour"):
            name = _text(item.get("stationName"))
            if not name:
                continue
            coord = coordinates.get(normalize_station_name(name))
            if not coord:
                continue
            conc = {
                "so2": _clean_conc(item.get("avgSo2")),
                "no2": _clean_conc(item.get("avgNo2")),
                "o3": _clean_conc(item.get("avgO3")),
                "co": _clean_conc(item.get("avgCo")),
                "pm10": _clean_conc(item.get("avgPm10")),
                "pm25": _clean_conc(item.get("avgPm25")),
            }
            est_aqi, est_primary = hourly_aqi_and_primary(conc)
            stations.append({
                "station_name": name,
                "type": "shengkong",
                "lon": coord["longitude"],
                "lat": coord["latitude"],
                "data_time": latest_time,
                "aqi": int(round(est_aqi)) if est_aqi is not None else None,
                "aqi_estimated": est_aqi is not None,
                "primary": est_primary,
                "pm25": conc["pm25"],
                "pm10": conc["pm10"],
                "o3": conc["o3"],
                "so2": conc["so2"],
                "no2": conc["no2"],
                "co": conc["co"],
            })
        return stations

    async def _office_stations(self) -> List[dict[str, Any]]:
        """办事处站点位（平台 listMap 坐标）+ OfficeFiveMinute 最新 5 分钟值。

        旧云平台办事处站（tstype=9，31 个街道办事处，平台仅发布
        PM2.5/PM10 两因子），气泡 AQI 按 HJ633 由两因子推算并标注。
        """
        from app.tools.xuchang.station_catalog.catalog import load_office_coordinates
        from app.tools.xuchang.station_catalog.coordinates import normalize_station_name

        now = self.now_factory()
        start = (now - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S")
        end = (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        probe = await cube_load({
            "measures": ["OfficeFiveMinute.count"],
            "dimensions": ["OfficeFiveMinute.dataTime"],
            "timeDimensions": [{
                "dimension": "OfficeFiveMinute.dataTime",
                "dateRange": [start, end],
            }],
            "order": {"OfficeFiveMinute.dataTime": "desc"},
            "limit": 1,
        })
        latest_time = _text(probe[0].get("OfficeFiveMinute.dataTime")) if probe else None
        if not latest_time:
            return []
        rows = await cube_load({
            "measures": [
                "OfficeFiveMinute.avgPm25", "OfficeFiveMinute.avgPm10",
            ],
            "dimensions": ["OfficeFiveMinute.stationName"],
            "timeDimensions": [{
                "dimension": "OfficeFiveMinute.dataTime",
                "dateRange": _minute_range(latest_time),
            }],
            "order": {"OfficeFiveMinute.avgPm25": "desc"},
            "limit": 40,
        })
        coordinates = load_office_coordinates()
        stations = []
        for item in _flat(rows, "OfficeFiveMinute"):
            name = _text(item.get("stationName"))
            if not name:
                continue
            coord = coordinates.get(normalize_station_name(name))
            if not coord:
                continue
            conc = {
                "pm10": _clean_conc(item.get("avgPm10")),
                "pm25": _clean_conc(item.get("avgPm25")),
                "so2": None,
                "no2": None,
                "o3": None,
                "co": None,
            }
            # 办事处仅 PM2.5/PM10 两因子，AQI 取两因子 IAQI 最大值（推算）
            est_aqi, est_primary = hourly_aqi_and_primary(conc)
            stations.append({
                "station_name": name,
                "type": "office",
                "lon": coord["longitude"],
                "lat": coord["latitude"],
                "data_time": latest_time,
                "aqi": int(round(est_aqi)) if est_aqi is not None else None,
                "aqi_estimated": est_aqi is not None,
                "primary": est_primary,
                "pm25": conc["pm25"],
                "pm10": conc["pm10"],
                "o3": None,
                "so2": None,
                "no2": None,
                "co": None,
            })
        return stations

    # ------------------------------------------------------------ 轮播素材段
    def _assets(self) -> List[dict[str, Any]]:
        """扫描三类轮播素材，按修改时间取各类最新 N 张。

        传输轨迹：xuchang_transport_analysis/YYYYMMDD/{job}.regional-paths.png
        GEMS 卫星：satellite/gems/xuchang/gems_*_xuchang_*.png（许昌区域裁剪）
        快照只存 registry 相对路径，前端经 /api/xuchang-dashboard/asset 出网。
        """
        registry = get_data_registry()
        now = self.now_factory()
        oldest = now.timestamp() - ASSET_WINDOW_DAYS * 86400

        candidates: List[tuple[float, str, str, str]] = []  # (mtime, kind, title, rel)

        transport_root = registry / TRANSPORT_OUTPUT_DIR
        if transport_root.is_dir():
            for path in transport_root.glob("*/[A-Za-z0-9]*.png"):
                stat = path.stat()
                if stat.st_mtime < oldest:
                    continue
                name = path.stem
                role = "近地层企业覆盖图" if ".local" in name else "区域后向轨迹走廊图"
                candidates.append((
                    stat.st_mtime, "transport", role,
                    path.relative_to(registry).as_posix(),
                ))

        gems_root = registry / GEMS_OUTPUT_DIR
        if gems_root.is_dir():
            for path in gems_root.glob("gems_*_xuchang_*.png"):
                stat = path.stat()
                if stat.st_mtime < oldest:
                    continue
                product = path.name.split("_")[1] if "_" in path.name else "GEMS"
                titles = {"AOD": "GEMS 气溶胶光学厚度", "UVAI": "GEMS 紫外气溶胶指数"}
                candidates.append((
                    stat.st_mtime, "gems",
                    titles.get(product, f"GEMS {product} 产品图"),
                    path.relative_to(registry).as_posix(),
                ))

        candidates.sort(key=lambda item: item[0], reverse=True)
        by_kind: Dict[str, int] = {}
        assets: List[dict[str, Any]] = []
        for mtime, kind, title, rel in candidates:
            if by_kind.get(kind, 0) >= ASSETS_PER_KIND:
                continue
            by_kind[kind] = by_kind.get(kind, 0) + 1
            assets.append({
                "kind": kind,
                "title": title,
                "asset_path": rel,
                "taken_at": datetime.fromtimestamp(mtime).replace(microsecond=0).isoformat(),
            })
        return assets

    # ------------------------------------------------------------ P2 扩展段
    async def _rank168(self) -> Optional[dict[str, Any]]:
        """168 重点城市全国排名（部发布月报口径，倒序排名 1=最差）。

        仅做全国排名展示，浓度绝对值看本地口径面板；期次取最新已发布月。
        """
        rows = await cube_load({
            "measures": [
                "Rank168CityMonthly.compositeIndexRank",
                "Rank168CityMonthly.pm25Rank",
                "Rank168CityMonthly.compositeIndex",
                "Rank168CityMonthly.pm25",
            ],
            "dimensions": [
                "Rank168CityMonthly.periodLabel",
                "Rank168CityMonthly.periodType",
                "Rank168CityMonthly.dataMonth",
            ],
            "filters": [
                {"member": "Rank168CityMonthly.periodType", "operator": "equals", "values": ["cum"]},
                {"member": "Rank168CityMonthly.city", "operator": "equals", "values": [XUCHANG_CITY]},
            ],
            "order": {"Rank168CityMonthly.periodEnd": "desc"},
            "limit": 1,
        })
        if not rows:
            return None
        # Cube 对 time 维度派生列的排序可能按字符串处理，取最新期次在 Python 侧兜底。
        row = _flat(rows, "Rank168CityMonthly")[0]
        return {
            "period_label": _text(row.get("periodLabel")),
            "period_type": _text(row.get("periodType")),
            "composite_rank": _int_or_none(row.get("compositeIndexRank")),
            "pm25_rank": _int_or_none(row.get("pm25Rank")),
            "composite_index": _number(row.get("compositeIndex")),
            "pm25": _number(row.get("pm25")),
        }

    def _minute_latest(self) -> Optional[dict[str, Any]]:
        """中大平台最新 5 分钟站点值 + 城市小时值（实时头的分钟级感知）。"""
        from app.tools.query.query_xcai_city_history.sql_client import (
            get_sql_server_client,
        )

        now = self.now_factory()
        client = get_sql_server_client()
        connection = pyodbc.connect(client.connection_string, timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP 1 station_name, time_point, aqi, pm25, pm10, o3, so2, no2, co
                FROM {STATION_TABLE}
                WHERE time_point >= ? AND aqi IS NOT NULL
                ORDER BY time_point DESC,
                  CASE parameter_type WHEN 'Act' THEN 0 WHEN 'App' THEN 1 ELSE 2 END,
                  id DESC
                """,
                (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
            )
            columns = [column[0] for column in cursor.description]
            minute_row = cursor.fetchone()
            cursor.execute(
                f"""
                SELECT TOP 1 area, time_point, aqi, quality, pollutant
                FROM {CITY_HOUR_TABLE}
                WHERE time_point >= ? AND aqi IS NOT NULL
                ORDER BY time_point DESC
                """,
                (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
            )
            city_columns = [column[0] for column in cursor.description]
            city_row = cursor.fetchone()
        finally:
            connection.close()

        result: Dict[str, Any] = {}
        if minute_row is not None:
            values = dict(zip(columns, minute_row))
            # 5 分钟口径不发布 AQI（中大平台恒为 0），只展示六参数浓度
            result["station"] = {
                "station_name": _text(values.get("station_name")),
                "data_time": _iso(values.get("time_point")),
                "pm25": _clean_conc(values.get("pm25")),
                "pm10": _clean_conc(values.get("pm10")),
                "o3": _clean_conc(values.get("o3")),
                "so2": _clean_conc(values.get("so2")),
                "no2": _clean_conc(values.get("no2")),
                "co": _clean_conc(values.get("co")),
            }
        if city_row is not None:
            values = dict(zip(city_columns, city_row))
            result["city"] = {
                "area": _text(values.get("area")),
                "data_time": _iso(values.get("time_point")),
                "aqi": _clean_aqi(values.get("aqi")),
                "quality": _text(values.get("quality")),
                "primary": _text(values.get("pollutant")),
            }
        return result or None

    async def _quality(self) -> Optional[dict[str, Any]]:
        """监测科数据质量：县级站最近整点 / 乡镇站最新 5 分钟在线站点数。

        SsfbSiteHour 覆盖全省县级省控站（过滤许昌后看市级归属）；
        乡镇站走 TownFiveMinute（TownStationData 停更后的替代源，原始口径）。
        """
        latest = self._latest_hour_iso()

        site_rows = await cube_load({
            "measures": ["SsfbSiteHour.onlineSites"],
            "dimensions": [
                "SsfbSiteHour.dataTime", "SsfbSiteHour.city",
            ],
            "timeDimensions": [{
                "dimension": "SsfbSiteHour.dataTime",
                "dateRange": _hour_range(latest),
            }],
            "filters": [{
                "member": "SsfbSiteHour.city",
                "operator": "equals",
                "values": [XUCHANG_CITY],
            }],
            "limit": 5,
        })
        site = {"data_time": None, "online": None}
        for item in _flat(site_rows, "SsfbSiteHour"):
            online = _int_or_none(item.get("onlineSites"))
            if online is not None:
                site = {
                    "data_time": _iso(item.get("dataTime")),
                    "online": online,
                }
                break

        town = None
        now = self.now_factory()
        town_probe = await cube_load({
            "measures": ["TownFiveMinute.count"],
            "dimensions": ["TownFiveMinute.dataTime"],
            "timeDimensions": [{
                "dimension": "TownFiveMinute.dataTime",
                "dateRange": [
                    (now - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S"),
                    (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S"),
                ],
            }],
            "order": {"TownFiveMinute.dataTime": "desc"},
            "limit": 1,
        })
        town_time = _text(town_probe[0].get("TownFiveMinute.dataTime")) if town_probe else None
        if town_time:
            rows = await cube_load({
                "measures": ["TownFiveMinute.onlineSites"],
                "dimensions": ["TownFiveMinute.dataTime"],
                "timeDimensions": [{
                    "dimension": "TownFiveMinute.dataTime",
                    "dateRange": _minute_range(town_time),
                }],
                "limit": 1,
            })
            if rows:
                row = _flat(rows, "TownFiveMinute")[0]
                town = {
                    "data_time": _iso(row.get("dataTime")),
                    "online": _int_or_none(row.get("onlineSites")),
                    "caliber": "src",
                    "total": TOWNSHIP_TOTAL,
                }
        return {"site_hour": site, "town_hour": town}

    # ------------------------------------------------------------ 左侧统计段
    async def _city_period_stats(self, today: date) -> dict[str, Any]:
        """许昌市当月/当年截止昨天的统计（本地日值自算，未剔沙尘，实时参考口径）。

        官方月报发布前这是唯一"截至昨天"的过程数据，面板必须标注口径；
        官方定版值看 city_year_target_official / province_city_ranking 段。
        """
        yesterday = today - timedelta(days=1)
        month_start = yesterday.replace(day=1)
        year_start = yesterday.replace(month=1, day=1)
        month = await self._city_day_aggregate(month_start, yesterday)
        year = await self._city_day_aggregate(year_start, yesterday)
        return {"as_of": yesterday.isoformat(), "month": month, "year": year}

    async def _city_day_aggregate(self, start: date, end: date) -> Optional[dict[str, Any]]:
        if end < start:
            return None
        rows = await cube_load({
            "measures": [
                "SsfbCityDay.count", "SsfbCityDay.avgPm25", "SsfbCityDay.avgPm10",
                "SsfbCityDay.avgO38h", "SsfbCityDay.avgNo2", "SsfbCityDay.avgSo2",
                "SsfbCityDay.avgCo",
            ],
            "dimensions": ["SsfbCityDay.quality", "SsfbCityDay.dataDate"],
            "timeDimensions": [{
                "dimension": "SsfbCityDay.dataDate",
                "dateRange": [start.isoformat(), end.isoformat()],
            }],
            "filters": [{
                "member": "SsfbCityDay.city", "operator": "equals", "values": [XUCHANG_CITY],
            }],
            "limit": 100,
        })
        days_total = 0
        good_days = 0
        sums: Dict[str, float] = {}
        counts: Dict[str, int] = {}
        metrics = ["avgPm25", "avgPm10", "avgO38h", "avgNo2", "avgSo2", "avgCo"]
        for item in _flat(rows, "SsfbCityDay"):
            count = int(item.get("count") or 0)
            days_total += count
            if _text(item.get("quality")) in GOOD_QUALITIES:
                good_days += count
            for key in metrics:
                value = _number(item.get(key))
                if value is not None and count:
                    sums[key] = sums.get(key, 0.0) + value * count
                    counts[key] = counts.get(key, 0) + count
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days_total": days_total,
            "good_days": good_days,
            "good_days_ratio": round(good_days / days_total * 100, 1) if days_total else None,
            "pm25": round(sums["avgPm25"] / counts["avgPm25"], 1) if counts.get("avgPm25") else None,
            "pm10": round(sums["avgPm10"] / counts["avgPm10"], 1) if counts.get("avgPm10") else None,
            "o3_8h": round(sums["avgO38h"] / counts["avgO38h"], 1) if counts.get("avgO38h") else None,
            "no2": round(sums["avgNo2"] / counts["avgNo2"], 1) if counts.get("avgNo2") else None,
            "so2": round(sums["avgSo2"] / counts["avgSo2"], 1) if counts.get("avgSo2") else None,
            "co": round(sums["avgCo"] / counts["avgCo"], 2) if counts.get("avgCo") else None,
            "caliber": "本地日值自算·未剔沙尘（实时参考）",
        }

    async def _province_city_ranking(self) -> dict[str, Any]:
        """全省 19 市(区)官方月报排名（当月 + 1-N 月累计，最新期次）。

        综合指数正序（低=好），rank 由本段按官方值重排（1=最优）。
        """
        result: Dict[str, Any] = {}
        for scope, cube_name in (("month", "ProvinceMonth"), ("cum", "ProvinceMonthCum")):
            latest = await cube_load({
                "measures": [f"{cube_name}.count"],
                "dimensions": [f"{cube_name}.dataMonth"],
                "filters": [{"member": f"{cube_name}.level", "operator": "equals", "values": ["city"]}],
                "order": {f"{cube_name}.dataMonth": "desc"},
                "limit": 1,
            })
            month = _text(latest[0].get(f"{cube_name}.dataMonth")) if latest else None
            if not month:
                continue
            rows = await cube_load({
                "measures": [
                    f"{cube_name}.pm25", f"{cube_name}.pm10", f"{cube_name}.o3",
                    f"{cube_name}.goodDays", f"{cube_name}.heavyDays",
                    f"{cube_name}.compositeIndex",
                    f"{cube_name}.pm25YoY", f"{cube_name}.compositeIndexYoY",
                ],
                "dimensions": [f"{cube_name}.region"],
                "timeDimensions": [{
                    "dimension": f"{cube_name}.dataMonth",
                    "dateRange": [month, _month_end(month[:7]).isoformat()],
                }],
                "filters": [{"member": f"{cube_name}.level", "operator": "equals", "values": ["city"]}],
                "limit": 30,
            })
            entries = []
            for item in _flat(rows, cube_name):
                entries.append({
                    "region": _text(item.get("region")),
                    "pm25": _number(item.get("pm25")),
                    "pm10": _number(item.get("pm10")),
                    "o3": _number(item.get("o3")),
                    "good_days": _int_or_none(item.get("goodDays")),
                    "heavy_days": _int_or_none(item.get("heavyDays")),
                    "composite_index": _number(item.get("compositeIndex")),
                    "pm25_yoy": _number(item.get("pm25YoY")),
                    "composite_index_yoy": _number(item.get("compositeIndexYoY")),
                })
            entries.sort(key=lambda item: (
                item["composite_index"] is None,
                item["composite_index"] if item["composite_index"] is not None else 0,
            ))
            for index, item in enumerate(entries, start=1):
                item["rank"] = index if item["composite_index"] is not None else None
            result[scope] = {"data_month": month[:7], "rows": entries}
        return result

    async def _city_year_target_official(self) -> dict[str, Any]:
        """许昌市年度目标与实际（官方考核定版）+ 当前在途年度目标。"""
        rows = await cube_load({
            "measures": [
                "XuchangCityYearTarget.pm25Target", "XuchangCityYearTarget.pm10Target",
                "XuchangCityYearTarget.goodDaysTarget", "XuchangCityYearTarget.heavyDaysTarget",
                "XuchangCityYearTarget.pm25", "XuchangCityYearTarget.pm10",
                "XuchangCityYearTarget.goodDays", "XuchangCityYearTarget.heavyDays",
            ],
            "dimensions": ["XuchangCityYearTarget.year"],
            "limit": 20,
        })
        years = []
        for item in _flat(rows, "XuchangCityYearTarget"):
            years.append({
                "year": _int_or_none(item.get("year")),
                "pm25_target": _number(item.get("pm25Target")),
                "pm10_target": _number(item.get("pm10Target")),
                "good_days_target": _int_or_none(item.get("goodDaysTarget")),
                "heavy_days_target": _int_or_none(item.get("heavyDaysTarget")),
                "pm25": _number(item.get("pm25")),
                "pm10": _number(item.get("pm10")),
                "good_days": _int_or_none(item.get("goodDays")),
                "heavy_days": _int_or_none(item.get("heavyDays")),
            })
        years.sort(key=lambda item: item["year"] or 0, reverse=True)
        current_year = self.now_factory().year
        finalized = next((item for item in years if (item["year"] or 0) < current_year), None)
        current = next((item for item in years if item["year"] == current_year), None)
        return {"finalized": finalized, "current": current}

    async def _county_year_targets(self) -> dict[str, Any]:
        """许昌 10 县市区年度目标与实际（官方考核定版，默认最新定版年）。"""
        years_probe = await cube_load({
            "measures": ["XuchangCountyYearTarget.count"],
            "dimensions": ["XuchangCountyYearTarget.year"],
            "limit": 20,
        })
        years = sorted(
            (_int_or_none(item.get("year")) for item in _flat(years_probe, "XuchangCountyYearTarget")),
            reverse=True,
        )
        years = [year for year in years if year is not None]
        if not years:
            return {}
        result: Dict[str, Any] = {"years": years, "by_year": {}}
        for year in years[:3]:
            rows = await cube_load({
                "measures": [
                    "XuchangCountyYearTarget.pm25Target", "XuchangCountyYearTarget.pm25",
                    "XuchangCountyYearTarget.pm10Target", "XuchangCountyYearTarget.pm10",
                    "XuchangCountyYearTarget.goodDaysTarget", "XuchangCountyYearTarget.goodDays",
                    "XuchangCountyYearTarget.heavyDaysTarget", "XuchangCountyYearTarget.heavyDays",
                ],
                "dimensions": [
                    "XuchangCountyYearTarget.region", "XuchangCountyYearTarget.regionType",
                    "XuchangCountyYearTarget.pm25Completed", "XuchangCountyYearTarget.goodDaysCompleted",
                    "XuchangCountyYearTarget.heavyDaysCompleted",
                ],
                "filters": [{
                    "member": "XuchangCountyYearTarget.year", "operator": "equals",
                    "values": [str(year)],
                }],
                "limit": 20,
            })
            entries = []
            for item in _flat(rows, "XuchangCountyYearTarget"):
                entries.append({
                    "region": _text(item.get("region")),
                    "region_type": _text(item.get("regionType")),
                    "pm25_target": _number(item.get("pm25Target")),
                    "pm25": _number(item.get("pm25")),
                    "pm10_target": _number(item.get("pm10Target")),
                    "pm10": _number(item.get("pm10")),
                    "good_days_target": _int_or_none(item.get("goodDaysTarget")),
                    "good_days": _int_or_none(item.get("goodDays")),
                    "heavy_days_target": _int_or_none(item.get("heavyDaysTarget")),
                    "heavy_days": _int_or_none(item.get("heavyDays")),
                    "pm25_completed": _text(item.get("pm25Completed")),
                    "good_days_completed": _text(item.get("goodDaysCompleted")),
                    "heavy_days_completed": _text(item.get("heavyDaysCompleted")),
                })
            result["by_year"][str(year)] = entries
        return result

    async def _rank168_series(self) -> dict[str, Any]:
        """168 城全国排名（生态环境部定版）：当月 + 1-N 月累计两个口径。"""
        result: Dict[str, Any] = {}
        for scope in ("month", "cum"):
            rows = await cube_load({
                "measures": [
                    "Rank168CityMonthly.compositeIndexRank", "Rank168CityMonthly.pm25Rank",
                    "Rank168CityMonthly.compositeIndex", "Rank168CityMonthly.pm25",
                ],
                "dimensions": ["Rank168CityMonthly.periodLabel", "Rank168CityMonthly.dataMonth"],
                "filters": [
                    {"member": "Rank168CityMonthly.periodType", "operator": "equals", "values": [scope]},
                    {"member": "Rank168CityMonthly.city", "operator": "equals", "values": [XUCHANG_CITY]},
                ],
                "order": {"Rank168CityMonthly.dataMonth": "desc"},
                "limit": 12,
            })
            entries = [{
                "period_label": _text(item.get("periodLabel")),
                "data_month": (_text(item.get("dataMonth")) or "")[:7],
                "composite_rank": _int_or_none(item.get("compositeIndexRank")),
                "pm25_rank": _int_or_none(item.get("pm25Rank")),
                "composite_index": _number(item.get("compositeIndex")),
                "pm25": _number(item.get("pm25")),
            } for item in _flat(rows, "Rank168CityMonthly")]
            # dataMonth 为 time 维度但排序键在 Cube 层对 varchar 派生列可能失效，
            # 统一在 Python 侧按月份字符串倒序兜底（见 _rank168 同款修复）。
            entries.sort(key=lambda item: item["data_month"], reverse=True)
            result[scope] = entries
        return result

    async def _county_month_report(self) -> dict[str, Any]:
        """许昌 10 县市区官方月报统计（当月 + 1-N 月累计，省/国家平台）。

        region_type: 魏都/开发/东城/示范/建安=国家平台，鄢陵/襄城/禹州/长葛=省平台。
        """
        result: Dict[str, Any] = {}
        for scope, cube_name in (("month", "CountyMonth"), ("cum", "CountyMonthCum")):
            latest = await cube_load({
                "measures": [f"{cube_name}.count"],
                "dimensions": [f"{cube_name}.dataMonth"] if scope == "month" else [f"{cube_name}.periodEnd"],
                "order": {f"{cube_name}.{'dataMonth' if scope == 'month' else 'periodEnd'}": "desc"},
                "limit": 1,
            })
            key = "dataMonth" if scope == "month" else "periodEnd"
            month = _text(latest[0].get(f"{cube_name}.{key}")) if latest else None
            if not month:
                continue
            if scope == "month":
                date_range = [month, _month_end(month[:7]).isoformat()]
            else:
                date_range = [month, month]
            rows = await cube_load({
                "measures": [
                    f"{cube_name}.pm25", f"{cube_name}.pm10", f"{cube_name}.so2",
                    f"{cube_name}.no2", f"{cube_name}.co95", f"{cube_name}.o3_8h_90",
                    f"{cube_name}.goodDays", f"{cube_name}.heavyDays", f"{cube_name}.compositeIndex",
                ],
                "dimensions": [f"{cube_name}.region", f"{cube_name}.regionType"],
                "timeDimensions": [{
                    "dimension": f"{cube_name}.{key}", "dateRange": date_range,
                }],
                "limit": 20,
            })
            entries = []
            for item in _flat(rows, cube_name):
                entries.append({
                    "region": _text(item.get("region")),
                    "region_type": _text(item.get("regionType")),
                    "pm25": _number(item.get("pm25")),
                    "pm10": _number(item.get("pm10")),
                    "so2": _number(item.get("so2")),
                    "no2": _number(item.get("no2")),
                    "co95": _number(item.get("co95")),
                    "o3_8h_90": _number(item.get("o3_8h_90")),
                    "good_days": _int_or_none(item.get("goodDays")),
                    "heavy_days": _int_or_none(item.get("heavyDays")),
                    "composite_index": _number(item.get("compositeIndex")),
                })
            entries.sort(key=lambda item: (
                item["composite_index"] is None,
                item["composite_index"] if item["composite_index"] is not None else 0,
            ))
            result[scope] = {"data_month": month[:7], "rows": entries}
        return result

    # ------------------------------------------------------------ 右侧 NMC 气象预报段
    def _nmc_forecast(self) -> Optional[dict[str, Any]]:
        """NMC 逐 3 小时气象预报（最新发布批次，未来 7 天）。

        与 xuchang_weather_report 同源同口径（XcAiDb XuchangNmcHourlyWeatherForecast）。
        """
        from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client

        now = self.now_factory()
        connection = pyodbc.connect(get_sql_server_client().connection_string, timeout=30)
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT forecast_time, temperature, humidity, wind_speed, wind_direction,
                       precipitation_probability, weather_text, publish_time
                FROM dbo.XuchangNmcHourlyWeatherForecast
                WHERE city_name=N'许昌市' AND forecast_time >= ?
                  AND publish_time=(SELECT MAX(publish_time) FROM dbo.XuchangNmcHourlyWeatherForecast
                                    WHERE city_name=N'许昌市' AND forecast_time >= ?)
                ORDER BY forecast_time
                """,
                now.replace(minute=0, second=0),
                now.replace(minute=0, second=0),
            )
            columns = [column[0] for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            connection.close()
        if not rows:
            return None
        return {
            "publish_time": _iso(rows[0].get("publish_time")),
            "rows": [{
                "time": _iso(item.get("forecast_time")),
                "temperature": _number(item.get("temperature")),
                "humidity": _number(item.get("humidity")),
                "wind_speed": _number(item.get("wind_speed")),
                "wind_direction": _text(item.get("wind_direction")),
                "precipitation_probability": _number(item.get("precipitation_probability")),
                "weather_text": _text(item.get("weather_text")),
            } for item in rows],
        }

"""许昌数据大屏快照聚合 fetcher。

大屏前端不直连 Cube/SQL Server：本任务周期性把整屏数据聚合为一份
snapshot.json，web 进程的 ``/api/xuchang-dashboard/screen-snapshot``
只做文件读（3 个 uvicorn worker 共享同一份快照，同一时刻整屏一致）。

口径红线：城市/区县/乡镇数据一律经 Cube Core 语义层
（``app.tools.query.xuchang_cube_metrics.tool.cube_load``），与对话问数
同源；预报复用 OpenMeteoAirQualityForecast72h / WeatherForecast7Day
（与 ``app.api.xuchang_air_quality_routes`` 同表同口径）；告警读场景一
episode_state.json；播报读定时任务结构化结果表。

调度避开河南 ssfb 三抓取器窗口（城市 :14/:20/:55、站点 :16/:22/:57、
区县 :18/:24/:59），且晚于整点后入库节奏；本任务只经 Cube 常驻服务读
MySQL，不直连 Crawler MySQL。

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
from app.tools.query.xuchang_cube_metrics.tool import cube_load
from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

SNAPSHOT_SCHEMA_VERSION = 1
XUCHANG_CITY = "许昌市"
# 与 app/api/xuchang_air_quality_routes.py 同源（XcAiDb WeatherForecast7Day）
XUCHANG_CITY_CODE = "411000"
# NMC 许昌观测站（backend/app/config/weather_targets.py）
MET_STATION_ID = "ZzMTA"
# 中大平台许昌站点小时表（国控站地图层，2026-10 起 CNEMC 直发下线后
# dat_station_hour 已无数据，国控站小时值以此表为准）
ZHONGDA_STATION_HOUR_TABLE = "dbo.dat_zhongda_station_hour"

SNAPSHOT_DIR = "xuchang_screen_snapshot"
SNAPSHOT_FILE = "snapshot.json"

GOOD_QUALITIES = {"优", "良"}
# 已关闭但仍在窗口内的告警保留展示，供巡查人员回看
ALERT_WINDOW = timedelta(hours=24)
MAX_ALERTS = 12
MAX_TOWNSHIPS = 80


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
            schedule="11,41 * * * *",
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

        snapshot = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "generated_at": now.isoformat(),
            "data_cutoff_hour": cutoff,
            "header": header,
            "city_hour_rank": city_rank,
            "county_hour_rank": county_rank,
            "city_trend_24h": trend,
            "forecast_72h": forecast,
            "year_target": year_target,
            "alerts": alerts,
            "broadcast": broadcast,
            "stations": stations,
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
            "met": await asyncio.to_thread(self._observed_met),
        }

    def _observed_met(self) -> Optional[dict[str, Any]]:
        """NMC 许昌站最近一条实况气象（大屏头部要素）。"""
        from sqlalchemy import select

        from app.db.models import ObservedWeatherData
        from app.db.sync_bridge import run_db
        from app.db.weather_database import weather_async_session

        window_start = self.now_factory() - timedelta(hours=6)

        async def _read():
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
                return (await session.execute(stmt)).scalars().first()

        try:
            row = run_db(_read())
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
                    "aqi": _int_or_none(value.get("aqi")),
                    "pm25": _number(value.get("pm25")),
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

        alerts: List[dict[str, Any]] = []
        for episode in iter_episodes(state):
            status = _text(episode.get("status")) or "unknown"
            last_seen = _parse_dt(episode.get("last_seen_at") or episode.get("started_at"))
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

        records, _total = DatabaseTaskResultStorage().query_page(page=1, page_size=10)
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
        return {"national": national, "townships": townships}

    def _national_stations(self, alert_names: set[str]) -> List[dict[str, Any]]:
        """国控站点位（内置坐标）+ 中大平台小时值。"""
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
                SELECT TOP 80 station_name, time_point, aqi, pm25, pm10, o3
                FROM {ZHONGDA_STATION_HOUR_TABLE}
                WHERE time_point >= ? AND aqi IS NOT NULL
                ORDER BY time_point DESC, id DESC
                """,
                (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
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
            stations.append({
                "station_id": code,
                "station_name": meta["name"],
                "type": "national",
                "lon": meta["lon"],
                "lat": meta["lat"],
                "data_time": _iso(row.get("time_point")),
                "aqi": _int_or_none(row.get("aqi")),
                "pm25": _number(row.get("pm25")),
                "pm10": _number(row.get("pm10")),
                "o3": _number(row.get("o3")),
                "alerting": name_key in alert_keys,
            })
        return stations

    async def _township_stations(self) -> List[dict[str, Any]]:
        """乡镇站点位（TSV 坐标）+ TownHour 最新小时值，审核口径优先。"""
        from app.tools.xuchang.station_catalog.catalog import load_township_coordinates
        from app.tools.xuchang.station_catalog.coordinates import normalize_station_name

        now = self.now_factory()
        start = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:00:00")
        end = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:00:00")
        for caliber in ("app", "src"):
            probe = await cube_load({
                "measures": ["TownHour.count"],
                "dimensions": ["TownHour.dataTime"],
                "timeDimensions": [{
                    "dimension": "TownHour.dataTime",
                    "dateRange": [start, end],
                }],
                "filters": [{
                    "member": "TownHour.caliber",
                    "operator": "equals",
                    "values": [caliber],
                }],
                "order": {"TownHour.dataTime": "desc"},
                "limit": 1,
            })
            if not probe:
                continue
            latest_time = _text(probe[0].get("TownHour.dataTime"))
            if not latest_time:
                continue
            rows = await cube_load({
                "measures": ["TownHour.avgPm25", "TownHour.maxAqi"],
                "dimensions": ["TownHour.stationName"],
                "timeDimensions": [{
                    "dimension": "TownHour.dataTime",
                    "dateRange": _hour_range(latest_time),
                }],
                "filters": [{
                    "member": "TownHour.caliber",
                    "operator": "equals",
                    "values": [caliber],
                }],
                "order": {"TownHour.maxAqi": "desc"},
                "limit": MAX_TOWNSHIPS,
            })
            coordinates = load_township_coordinates()
            stations = []
            for item in _flat(rows, "TownHour"):
                name = _text(item.get("stationName"))
                if not name:
                    continue
                coord = coordinates.get(normalize_station_name(name))
                if not coord:
                    continue
                stations.append({
                    "station_name": name,
                    "type": "township",
                    "caliber": caliber,
                    "lon": coord["longitude"],
                    "lat": coord["latitude"],
                    "data_time": latest_time,
                    "aqi": _int_or_none(item.get("maxAqi")),
                    "pm25": _number(item.get("avgPm25")),
                })
            if stations:
                return stations
        return []

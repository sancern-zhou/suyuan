"""Henan 18-city daily air-quality ranking（官方日值升序排序，取原值不聚合）。

背景：河南省空气质量 APP（月/年累计排名来源）已于 2026-09 停服。城市**日**排名
由本任务对官方发布日值直接排序展示（取原值，不做修约与聚合）。

**月/年累计统计已改为官方口径**（河南省环境空气质量月报附表，
见 ``DataCrawler.ProvinceMonthReport`` 与本目录 ``backfill_province_month/``），
本任务此前产出的本地手算 monthly/yearly 已停用并删除历史行（2026-10-16），
避免本地计算口径与官方发布值不一致。

结果写入 DataCrawler MySQL ``SsfbCityRanking``（仅 period_type=daily），
每日重算当期，幂等覆盖；每次运行顺带清理历史遗留的 monthly/yearly 行。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import aiomysql
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.henan_ssfb_client import HenanSsfbClient
from config.settings import settings

logger = structlog.get_logger()

RANKING_TABLE = "SsfbCityRanking"

RANKING_DDL = """
CREATE TABLE IF NOT EXISTS SsfbCityRanking (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    PeriodType VARCHAR(10) NOT NULL,
    Period VARCHAR(10) NOT NULL,
    City VARCHAR(50) NOT NULL,
    GroupID INT NULL,
    DataStart DATE NULL,
    DataEnd DATE NULL,
    Days INT NULL,
    ValidDays INT NULL,
    PmValidDays INT NULL,
    PM25 DOUBLE NULL,
    PM10 DOUBLE NULL,
    SO2 DOUBLE NULL,
    NO2 DOUBLE NULL,
    CO DOUBLE NULL,
    O3_8H DOUBLE NULL,
    RankPM25 INT NULL,
    RankPM10 INT NULL,
    RankSO2 INT NULL,
    RankNO2 INT NULL,
    RankO3 INT NULL,
    RankCO INT NULL,
    ComputedAt DATETIME NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY UK_SsfbCityRanking (PeriodType, Period, City)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

RANKING_UPSERT = """
INSERT INTO SsfbCityRanking
    (PeriodType, Period, City, GroupID, DataStart, DataEnd, Days, ValidDays, PmValidDays,
     PM25, PM10, SO2, NO2, CO, O3_8H,
     RankPM25, RankPM10, RankSO2, RankNO2, RankO3, RankCO,
     ComputedAt)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    GroupID=VALUES(GroupID), DataStart=VALUES(DataStart), DataEnd=VALUES(DataEnd),
    Days=VALUES(Days), ValidDays=VALUES(ValidDays), PmValidDays=VALUES(PmValidDays),
    PM25=VALUES(PM25), PM10=VALUES(PM10), SO2=VALUES(SO2), NO2=VALUES(NO2),
    CO=VALUES(CO), O3_8H=VALUES(O3_8H),
    RankPM25=VALUES(RankPM25), RankPM10=VALUES(RankPM10),
    RankSO2=VALUES(RankSO2), RankNO2=VALUES(RankNO2), RankO3=VALUES(RankO3),
    RankCO=VALUES(RankCO), ComputedAt=VALUES(ComputedAt)
"""

# 本地历史遗留的月/年累计行清理（官方口径改由 ProvinceMonthReport 提供）
PURGE_LEGACY_PERIODS = "DELETE FROM SsfbCityRanking WHERE PeriodType <> 'daily'"

DAY_QUERY = """
SELECT City AS city, GroupID AS group_id, DataTime AS data_time,
       PM25 AS pm25, PM10 AS pm10, O3_8H AS o3_8h, NO2 AS no2, SO2 AS so2, CO AS co
FROM SsfbCityDay
WHERE DataTime >= %s AND DataTime < %s
ORDER BY city, data_time
"""

# 实测源接口日值的 PM10 字段自 2026-10 起不再发布，小时值仍正常；
# PM10 日均按"本城当日小时算术平均"补齐后参与排序。
HOUR_PM10_QUERY = """
SELECT City AS city, DATE(DataTime) AS data_date, AVG(PM10) AS pm10_mean
FROM SsfbCityHour
WHERE DataTime >= %s AND DataTime < %s AND PM10 IS NOT NULL
GROUP BY City, DATE(DataTime)
"""


def compute_rank(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """升序并列排名（standard competition：1,1,3），None 不参与排名。"""
    ranked = sorted(
        (row for row in rows if row.get(key) is not None),
        key=lambda row: row[key],
    )
    result: list[dict[str, Any]] = []
    current_value = None
    current_rank = 0
    for index, row in enumerate(ranked, start=1):
        if row[key] != current_value:
            current_value = row[key]
            current_rank = index
        result.append({**row, "rank": current_rank})
    null_rows = [{**row, "rank": None} for row in rows if row.get(key) is None]
    return result + null_rows


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def build_daily_ranking_rows(
    period: str,
    city_values: dict[str, tuple[int | None, dict[str, float | None]]],
    computed_at: datetime,
) -> list[dict[str, Any]]:
    """对官方发布日值排序展示（取原值，不做修约与聚合）。"""
    metric_keys = {"pm25": "rank_pm25", "pm10": "rank_pm10", "so2": "rank_so2",
                   "no2": "rank_no2", "co": "rank_co", "o3_8h": "rank_o3"}
    ranked_by_metric = {
        column: compute_rank(
            [
                {"city": city, "value": values.get(key)}
                for city, (_, values) in city_values.items()
            ],
            key="value",
        )
        for key, column in metric_keys.items()
    }
    ranks: dict[str, dict[str, int | None]] = {city: {} for city in city_values}
    for column, rows in ranked_by_metric.items():
        for row in rows:
            ranks[row["city"]][column] = row["rank"]

    return [
        {
            "period_type": "daily",
            "period": period,
            "city": city,
            "group_id": city_values[city][0],
            **{key: city_values[city][1].get(key) for key in metric_keys},
            **ranks[city],
            "computed_at": computed_at,
        }
        for city in city_values
    ]


class XuchangHenanRankingRecalcFetcher(DataFetcher):
    """Daily official-value ranking of Henan 18 city groups (daily only)."""

    def __init__(
        self,
        client: HenanSsfbClient | None = None,
        now_factory=lambda: datetime.now(),
        mysql_config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            name="xuchang_henan_ranking_recalc_fetcher",
            description="河南18城市组官方日值排序(日排名,取原值不聚合)入库DataCrawler;月/年累计改走官方月报",
            schedule="10 6 * * *",
            version="4.0.0",
        )
        self.client = client or HenanSsfbClient()
        self.now_factory = now_factory
        self.mysql_config = mysql_config or self._mysql_config_from_settings()

    @staticmethod
    def _mysql_config_from_settings() -> dict[str, Any]:
        url = settings.crawler_mysql_url.split("://", 1)[1]
        auth_host, database = url.split("/", 1)
        credentials, host_port = auth_host.rsplit("@", 1)
        user, password = credentials.split(":", 1)
        host, port = host_port.split(":")
        return {
            "host": host,
            "port": int(port),
            "user": user,
            "password": password,
            "db": database.split("?", 1)[0],
            "autocommit": False,
        }

    def _load_city_days(self, start: str, end: str) -> list[dict[str, Any]]:
        import aiomysql as _aiomysql

        async def _run():
            conn = await _aiomysql.connect(**self.mysql_config)
            try:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(DAY_QUERY, (start, end))
                    return list(await cursor.fetchall())
            finally:
                conn.close()

        return _run_sync(_run())

    def _load_pm10_hour_means(self, start: str, end: str) -> dict[tuple[str, date], float]:
        async def _run():
            conn = await aiomysql.connect(**self.mysql_config)
            try:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(HOUR_PM10_QUERY, (start, end))
                    return list(await cursor.fetchall())
            finally:
                conn.close()

        rows = _run_sync(_run())
        return {
            (row["city"], row["data_date"]): float(row["pm10_mean"])
            for row in rows
            if row.get("pm10_mean") is not None
        }

    def _collect(self, fetched_at: datetime) -> dict[str, Any]:
        today = fetched_at.date()
        yesterday = today - timedelta(days=1)
        query_start = f"{yesterday - timedelta(days=1):%Y-%m-%d} 00:00:00"
        query_end = f"{today + timedelta(days=1):%Y-%m-%d} 00:00:00"

        day_rows = self._load_city_days(query_start, query_end)
        if not day_rows:
            raise ValueError("SsfbCityDay returned no rows for ranking calculation")
        _fill_pm10_from_hours(day_rows, self._load_pm10_hour_means(query_start, query_end))

        daily_rows: list[dict[str, Any]] = []
        daily_periods: list[str] = []
        for window_end in (yesterday, yesterday - timedelta(days=1)):
            city_map = self._aggregate_window(day_rows, window_end, window_end)
            if len(city_map) != 18:
                continue
            city_values: dict[str, tuple[int | None, dict[str, float | None]]] = {}
            for city, (group_id, days) in city_map.items():
                if not days:
                    continue
                day = days[0]
                city_values[city] = (
                    group_id,
                    {
                        "pm25": _number(day.get("pm25")),
                        "pm10": _number(day.get("pm10")),
                        "so2": _number(day.get("so2")),
                        "no2": _number(day.get("no2")),
                        "co": _number(day.get("co")),
                        "o3_8h": _number(day.get("o3_8h")),
                    },
                )
            if len(city_values) == 18:
                daily_periods.append(window_end.isoformat())
                daily_rows.extend(
                    build_daily_ranking_rows(window_end.isoformat(), city_values, fetched_at)
                )
        return {
            "daily": daily_rows,
            "daily_periods": daily_periods,
            "day_count": len(day_rows),
        }

    @staticmethod
    def _aggregate_window(
        day_rows: list[dict[str, Any]], start: date, end: date
    ) -> dict[str, tuple[int | None, list[dict[str, Any]]]]:
        window: dict[str, tuple[int | None, list[dict[str, Any]]]] = {}
        for row in day_rows:
            day = row["data_time"].date() if isinstance(row["data_time"], datetime) else row["data_time"]
            if not (start <= day <= end):
                continue
            city = row["city"]
            group_id, days = window.setdefault(city, (row.get("group_id"), []))
            days.append(row)
        return window

    async def fetch_and_store(self) -> dict[str, Any]:
        fetched_at = self.now_factory().replace(microsecond=0)
        collected = self._collect(fetched_at)
        saved = await self._save(collected)
        daily_pm25 = {
            row["period"]: row["rank_pm25"] for row in collected["daily"]
            if row["city"] == "许昌市"
        }
        result = {
            "fetched_at": fetched_at.isoformat(),
            "day_rows": collected["day_count"],
            "saved_daily": saved["daily"],
            "daily_periods": collected["daily_periods"],
            "xuchang_pm25_rank_daily": daily_pm25,
        }
        logger.info("xuchang_henan_ranking_recalc_completed", **result)
        return result

    async def _save(self, collected: dict[str, Any]) -> dict[str, int]:
        conn = await aiomysql.connect(**self.mysql_config)
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(RANKING_DDL)
                counts: dict[str, int] = {}
                rows = collected["daily"]
                if rows:
                    await cursor.executemany(
                        RANKING_UPSERT, [_ranking_params(row) for row in rows]
                    )
                counts["daily"] = len(rows)
                # 清理本地手算的月/年累计历史行（官方口径改由 ProvinceMonthReport 提供）
                await cursor.execute(PURGE_LEGACY_PERIODS)
                counts["purged_legacy"] = cursor.rowcount
            await conn.commit()
            return counts
        except Exception:
            await conn.rollback()
            raise
        finally:
            conn.close()


def _fill_pm10_from_hours(
    day_rows: list[dict[str, Any]], hour_means: dict[tuple[str, date], float]
) -> int:
    """日值 PM10 缺失时用本城当日小时均值补齐，返回补齐行数。"""
    filled = 0
    for row in day_rows:
        if row.get("pm10") is not None:
            continue
        day = row["data_time"].date() if isinstance(row["data_time"], datetime) else row["data_time"]
        mean = hour_means.get((row["city"], day))
        if mean is not None:
            row["pm10"] = mean
            filled += 1
    if filled:
        logger.info("xuchang_ranking_pm10_filled_from_hours", filled=filled)
    return filled


def _run_sync(coro: Any) -> Any:
    """在异步 fetcher 里执行同步采集路径的辅助（采集在执行线程内完成）。"""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def _ranking_params(row: dict[str, Any]) -> tuple:
    return (
        row["period_type"], row["period"], row["city"], row.get("group_id"),
        row.get("data_start"), row.get("data_end"), row.get("days"),
        row.get("valid_days"), row.get("pm_valid_days"),
        row["pm25"], row["pm10"], row["so2"], row["no2"],
        row["co"], row["o3_8h"],
        row["rank_pm25"], row["rank_pm10"],
        row["rank_so2"], row["rank_no2"], row["rank_o3"], row["rank_co"],
        row["computed_at"],
    )

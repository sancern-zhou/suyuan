"""Recalculate Henan city cumulative concentration rankings from SsfbCityDay.

背景：河南省空气质量 APP（月/年累计排名的唯一外部来源）已于 2026-09 停服，
XcAiDb.dbo.HenanCityAccumulateRanking 自 2026-08 后不再更新；同时全国城市
日发布历史（CityDayAQIPublishHistory）长期缺济源。本 fetcher 用我们自己
采集的 18 城市组日值（SsfbCityDay，含济源）按透明口径重算**单项浓度累计
与排名**（不做综合指数计算与排名）：

- 单项浓度：SO2/NO2/PM10/PM2.5 为算术月均/年均，O3 取日最大 8 小时值第 90
  百分位（nearest-rank），CO 取日均值第 95 百分位（nearest-rank）；
- 排名：单项浓度均**数值越低排名越靠前**，相同值并列
  （standard competition：1,1,3）；
- PM10 缺口：源日值接口 2026-10 起不发布 PM10，由本城小时均值补齐；
- 对照列：保留省 APP 官方最后月份（2026-08 及以前）的 zong/rank 供口径对照。

结果写入 DataCrawler MySQL ``SsfbCityRanking``（period_type=monthly/yearly），
每天全量重算当期，幂等覆盖。API 已停服导致的历史空窗（2026-09 起）可由
回算任务按 SsfbCityDay 覆盖范围重建（更早月份无本地日值，不回算）。
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any

import aiomysql
import pyodbc
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.henan_ssfb_client import HenanSsfbClient
from app.integrations.xcai_station_sql import xcai_connection_string
from config.settings import settings

logger = structlog.get_logger()

RANKING_TABLE = "SsfbCityRanking"

RANK_METRICS = ("pm25", "pm10", "so2", "no2", "o3_8h_90", "co_95")

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
    CO95 DOUBLE NULL,
    O3_8H_90 DOUBLE NULL,
    RankPM25 INT NULL,
    RankPM10 INT NULL,
    RankSO2 INT NULL,
    RankNO2 INT NULL,
    RankO3 INT NULL,
    RankCO INT NULL,
    OfficialZong DOUBLE NULL,
    OfficialRank INT NULL,
    ComputedAt DATETIME NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY UK_SsfbCityRanking (PeriodType, Period, City)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

RANKING_UPSERT = """
INSERT INTO SsfbCityRanking
    (PeriodType, Period, City, GroupID, DataStart, DataEnd, Days, ValidDays, PmValidDays,
     PM25, PM10, SO2, NO2, CO95, O3_8H_90,
     RankPM25, RankPM10, RankSO2, RankNO2, RankO3, RankCO,
     OfficialZong, OfficialRank, ComputedAt)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    GroupID=VALUES(GroupID), DataStart=VALUES(DataStart), DataEnd=VALUES(DataEnd),
    Days=VALUES(Days), ValidDays=VALUES(ValidDays), PmValidDays=VALUES(PmValidDays),
    PM25=VALUES(PM25), PM10=VALUES(PM10), SO2=VALUES(SO2), NO2=VALUES(NO2),
    CO95=VALUES(CO95), O3_8H_90=VALUES(O3_8H_90),
    RankPM25=VALUES(RankPM25), RankPM10=VALUES(RankPM10),
    RankSO2=VALUES(RankSO2), RankNO2=VALUES(RankNO2), RankO3=VALUES(RankO3),
    RankCO=VALUES(RankCO), OfficialZong=VALUES(OfficialZong),
    OfficialRank=VALUES(OfficialRank), ComputedAt=VALUES(ComputedAt)
"""

DAY_QUERY = """
SELECT City AS city, GroupID AS group_id, DataTime AS data_time,
       PM25 AS pm25, PM10 AS pm10, O3_8H AS o3_8h, NO2 AS no2, SO2 AS so2, CO AS co
FROM SsfbCityDay
WHERE DataTime >= %s AND DataTime < %s
ORDER BY city, data_time
"""

# 实测源接口日值的 PM10(pm1) 字段自 2026-10 起不再发布，小时值仍正常；
# PM10 日均按"本城当日小时算术平均"补齐（口径：小时均值近似 24h 采样均值，
# 与国标连续采样口径存在差异，已在 SsfbCityRanking 口径说明中标注）。
HOUR_PM10_QUERY = """
SELECT City AS city, DATE(DataTime) AS data_date, AVG(PM10) AS pm10_mean
FROM SsfbCityHour
WHERE DataTime >= %s AND DataTime < %s AND PM10 IS NOT NULL
GROUP BY City, DATE(DataTime)
"""

OFFICIAL_QUERY = """
SELECT city, zong, city_rank
FROM dbo.HenanCityAccumulateRanking
WHERE period_type = 'monthly' AND period = ?
"""


def percentile_nearest_rank(sorted_values: list[float], p: float) -> float | None:
    """Nearest-rank 百分位（ceil(p/100 * n) 位），与官方口径验证一致。"""
    if not sorted_values:
        return None
    rank = max(1, -(-int(p * len(sorted_values)) // 100))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def compute_rank(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """升序并列排名（standard competition：1,2,2,4），None 不参与排名。"""
    ranked = [
        sorted(
            (row for row in rows if row.get(key) is not None),
            key=lambda row: row[key],
        ),
    ][0]
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


class AggregationResult:
    """单城市一段时间的单项浓度累计指标。"""

    def __init__(self, city: str, group_id: int | None) -> None:
        self.city = city
        self.group_id = group_id
        self.days = 0
        self.valid_days = 0
        self.pm_valid_days = 0
        self.series: dict[str, list[float]] = {
            key: [] for key in ("pm25", "pm10", "so2", "no2", "co", "o3_8h")
        }

    def add_day(self, row: dict[str, Any]) -> None:
        self.days += 1
        pm25 = _number(row.get("pm25"))
        pm10 = _number(row.get("pm10"))
        if pm25 is not None:
            self.pm_valid_days += 1
        complete = True
        for key in self.series:
            value = _number(row.get(key))
            if value is None:
                complete = False
                continue
            self.series[key].append(value)
        if complete:
            self.valid_days += 1

    def _mean(self, key: str) -> float | None:
        values = self.series[key]
        return sum(values) / len(values) if values else None

    @property
    def pm25(self) -> float | None:
        return self._mean("pm25")

    @property
    def pm10(self) -> float | None:
        return self._mean("pm10")

    @property
    def so2(self) -> float | None:
        return self._mean("so2")

    @property
    def no2(self) -> float | None:
        return self._mean("no2")

    @property
    def o3_8h_90(self) -> float | None:
        return percentile_nearest_rank(sorted(self.series["o3_8h"]), 90)

    @property
    def co_95(self) -> float | None:
        return percentile_nearest_rank(sorted(self.series["co"]), 95)

    @classmethod
    def from_days(cls, city: str, group_id: int | None, days: list[dict[str, Any]]) -> "AggregationResult":
        result = cls(city, group_id)
        for row in days:
            result.add_day(row)
        return result


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def build_ranking_rows(
    period_type: str,
    period: str,
    city_stats: dict[str, tuple[int | None, list[dict[str, Any]]]],
    official: dict[str, dict[str, Any]],
    computed_at: datetime,
) -> list[dict[str, Any]]:
    """聚合 + 排名 + 官方对照，产出 SsfbCityRanking 行。"""
    aggregations: dict[str, AggregationResult] = {}
    for city, (group_id, days) in city_stats.items():
        aggregations[city] = AggregationResult.from_days(city, group_id, days)

    ranked_by_metric = {
        metric: compute_rank(
            [
                {"city": city, "value": getattr(aggregations[city], metric)}
                for city in aggregations
            ],
            key="value",
        )
        for metric in RANK_METRICS
    }
    ranks: dict[str, dict[str, int | None]] = {
        city: {} for city in aggregations
    }
    for metric, rows in ranked_by_metric.items():
        column = {
            "pm25": "rank_pm25",
            "pm10": "rank_pm10",
            "so2": "rank_so2",
            "no2": "rank_no2",
            "o3_8h_90": "rank_o3",
            "co_95": "rank_co",
        }[metric]
        for row in rows:
            ranks[row["city"]][column] = row["rank"]

    rows: list[dict[str, Any]] = []
    for city, agg in aggregations.items():
        official_row = official.get(_official_city_key(city)) or {}
        rows.append(
            {
                "period_type": period_type,
                "period": period,
                "city": city,
                "group_id": agg.group_id,
                "pm25": agg.pm25,
                "pm10": agg.pm10,
                "so2": agg.so2,
                "no2": agg.no2,
                "co_95": agg.co_95,
                "o3_8h_90": agg.o3_8h_90,
                "days": agg.days,
                "valid_days": agg.valid_days,
                "pm_valid_days": agg.pm_valid_days,
                **ranks[city],
                "official_zong": _number(official_row.get("zong")),
                "official_rank": (
                    int(official_row["rank"])
                    if official_row.get("rank") is not None
                    else None
                ),
                "computed_at": computed_at,
            }
        )
    return rows


def _official_city_key(city: str) -> str:
    # 官方表城市名不带"市"（许昌/济源），采集侧统一带"市"。
    return city[:-1] if city.endswith("市") else city


class XuchangHenanRankingRecalcFetcher(DataFetcher):
    """Daily recalculation of monthly/yearly Henan city rankings."""

    def __init__(
        self,
        client: HenanSsfbClient | None = None,
        now_factory=lambda: datetime.now(),
        mysql_config: dict[str, Any] | None = None,
        official_query: Any = None,
    ) -> None:
        super().__init__(
            name="xuchang_henan_ranking_recalc_fetcher",
            description="基于SsfbCityDay重算河南18城市组月/年单项浓度累计与排名入库DataCrawler",
            schedule="10 6 * * *",
            version="1.0.0",
        )
        self.client = client or HenanSsfbClient()
        self.now_factory = now_factory
        self.mysql_config = mysql_config or self._mysql_config_from_settings()
        self.official_query = official_query or _load_official_rankings

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

    def _collect(self, fetched_at: datetime) -> dict[str, Any]:
        today = fetched_at.date()
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)
        query_start = f"{year_start:%Y-%m-%d} 00:00:00"
        query_end = f"{today + timedelta(days=1):%Y-%m-%d} 00:00:00"

        day_rows = self._load_city_days(query_start, query_end)
        if not day_rows:
            raise ValueError("SsfbCityDay returned no rows for ranking recalculation")
        _fill_pm10_from_hours(day_rows, self._load_pm10_hour_means(query_start, query_end))

        monthly = self._aggregate_window(day_rows, month_start, today)
        yearly = self._aggregate_window(day_rows, year_start, today)

        official = self.official_query(month_start.strftime("%Y-%m"))
        monthly_rows = build_ranking_rows(
            "monthly", month_start.strftime("%Y-%m"), monthly, official, fetched_at
        )
        yearly_rows = build_ranking_rows(
            "yearly", str(year_start.year), yearly, {}, fetched_at
        )
        return {
            "monthly": monthly_rows,
            "yearly": yearly_rows,
            "day_count": len(day_rows),
        }

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


    def _load_city_days(self, start: str, end: str) -> list[dict[str, Any]]:
        """同步读 MySQL（fetcher 运行在 to_thread/事件循环外的一次调用内）。"""
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

    async def fetch_and_store(self) -> dict[str, Any]:
        fetched_at = self.now_factory().replace(microsecond=0)
        collected = self._collect(fetched_at)
        saved = await self._save(collected)
        pm25_ranks = {row["city"]: row["rank_pm25"] for row in collected["monthly"]}
        result = {
            "fetched_at": fetched_at.isoformat(),
            "day_rows": collected["day_count"],
            "saved_monthly": saved["monthly"],
            "saved_yearly": saved["yearly"],
            "xuchang_pm25_rank": pm25_ranks.get("许昌市"),
            "jiyuan_pm25_rank": pm25_ranks.get("济源市"),
        }
        logger.info("xuchang_henan_ranking_recalc_completed", **result)
        return result

    async def _save(self, collected: dict[str, Any]) -> dict[str, int]:
        conn = await aiomysql.connect(**self.mysql_config)
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(RANKING_DDL)
                counts = {}
                for kind in ("monthly", "yearly"):
                    rows = collected[kind]
                    if rows:
                        await cursor.executemany(
                            RANKING_UPSERT, [_ranking_params(row) for row in rows]
                        )
                    counts[kind] = len(rows)
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
        row["period_type"], row["period"], row["city"], row["group_id"],
        row.get("data_start"), row.get("data_end"), row["days"],
        row["valid_days"], row["pm_valid_days"],
        row["pm25"], row["pm10"], row["so2"], row["no2"],
        row["co_95"], row["o3_8h_90"],
        row["rank_pm25"], row["rank_pm10"],
        row["rank_so2"], row["rank_no2"], row["rank_o3"], row["rank_co"],
        row["official_zong"], row["official_rank"], row["computed_at"],
    )


def _load_official_rankings(period: str) -> dict[str, dict[str, Any]]:
    """读省 APP 官方对照（XcAiDb）。接口停服后历史月份仍可对照。"""
    try:
        connection = pyodbc.connect(xcai_connection_string(), timeout=30)
    except pyodbc.Error as exc:
        logger.warning("xuchang_ranking_official_unavailable", error=str(exc))
        return {}
    try:
        cursor = connection.cursor()
        cursor.execute(OFFICIAL_QUERY, period)
        return {
            row[0]: {"zong": row[1], "rank": row[2]}
            for row in cursor.fetchall()
        }
    finally:
        connection.close()

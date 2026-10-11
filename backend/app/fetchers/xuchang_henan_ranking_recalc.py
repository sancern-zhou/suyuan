"""Rank Henan cities on the officially published daily values (SsfbCityDay).

背景：河南省空气质量 APP（月/年累计排名的唯一外部来源）已于 2026-09 停服；
全国城市日发布历史（CityDayAQIPublishHistory）长期缺济源。本 fetcher 对
我们自己采集的 18 城市组日值（SsfbCityDay，含济源）**仅做排序展示**：

- 排序对象为官方发布的当日浓度值，本任务**不做任何聚合统计计算**
  （不计算月均/年均/百分位等统计量——环境统计口径以官方发布为准）;
- 排名规则：**数值越低排名越靠前**，相同值并列（standard competition：1,1,3）；
- 某城市某参数当日值缺失时不参与该参数排名（Rank 为空），不做数据补齐；
- 月度及以上统计（含同比/达标/综合指数）一律以官方发布为准，不在本地生成。

结果写入 DataCrawler MySQL ``SsfbCityRanking``（period_type='daily'，
period=YYYY-MM-DD），每日重算昨日与前日，幂等覆盖。
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

RANK_METRICS = ("pm25", "pm10", "so2", "no2", "o3_8h", "co")

RANKING_DDL = """
CREATE TABLE IF NOT EXISTS SsfbCityRanking (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    PeriodType VARCHAR(10) NOT NULL,
    Period VARCHAR(10) NOT NULL,
    City VARCHAR(50) NOT NULL,
    GroupID INT NULL,
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
    (PeriodType, Period, City, GroupID,
     PM25, PM10, SO2, NO2, CO, O3_8H,
     RankPM25, RankPM10, RankSO2, RankNO2, RankO3, RankCO,
     ComputedAt)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    GroupID=VALUES(GroupID),
    PM25=VALUES(PM25), PM10=VALUES(PM10), SO2=VALUES(SO2), NO2=VALUES(NO2),
    CO=VALUES(CO), O3_8H=VALUES(O3_8H),
    RankPM25=VALUES(RankPM25), RankPM10=VALUES(RankPM10),
    RankSO2=VALUES(RankSO2), RankNO2=VALUES(RankNO2), RankO3=VALUES(RankO3),
    RankCO=VALUES(RankCO), ComputedAt=VALUES(ComputedAt)
"""

DAY_QUERY = """
SELECT City AS city, GroupID AS group_id, DataTime AS data_time,
       PM25 AS pm25, PM10 AS pm10, O3_8H AS o3_8h, NO2 AS no2, SO2 AS so2, CO AS co
FROM SsfbCityDay
WHERE DataTime >= %s AND DataTime < %s
ORDER BY city, data_time
"""


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


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


def build_ranking_rows(
    period: str,
    city_values: dict[str, tuple[int | None, dict[str, float | None]]],
    computed_at: datetime,
) -> list[dict[str, Any]]:
    """对官方发布日值排序（无聚合计算），产出 SsfbCityRanking 行。"""
    ranked_by_metric = {
        metric: compute_rank(
            [
                {"city": city, "value": values.get(metric)}
                for city, (_, values) in city_values.items()
            ],
            key="value",
        )
        for metric in RANK_METRICS
    }
    ranks: dict[str, dict[str, int | None]] = {
        city: {} for city in city_values
    }
    column_map = {
        "pm25": "rank_pm25",
        "pm10": "rank_pm10",
        "so2": "rank_so2",
        "no2": "rank_no2",
        "o3_8h": "rank_o3",
        "co": "rank_co",
    }
    for metric, rows in ranked_by_metric.items():
        for row in rows:
            ranks[row["city"]][column_map[metric]] = row["rank"]

    return [
        {
            "period_type": "daily",
            "period": period,
            "city": city,
            "group_id": city_values[city][0],
            "pm25": city_values[city][1].get("pm25"),
            "pm10": city_values[city][1].get("pm10"),
            "so2": city_values[city][1].get("so2"),
            "no2": city_values[city][1].get("no2"),
            "co": city_values[city][1].get("co"),
            "o3_8h": city_values[city][1].get("o3_8h"),
            **ranks[city],
            "computed_at": computed_at,
        }
        for city in city_values
    ]


def _chunked(values: list[int], size: int) -> list[list[int]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


class XuchangHenanRankingRecalcFetcher(DataFetcher):
    """Daily ranking of officially published city daily values (no aggregation)."""

    def __init__(
        self,
        client: HenanSsfbClient | None = None,
        now_factory=lambda: datetime.now(),
        mysql_config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            name="xuchang_henan_ranking_recalc_fetcher",
            description="对官方发布日值(SsfbCityDay)排序生成18城市组日排名入库DataCrawler",
            schedule="10 6 * * *",
            version="2.0.0",
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

    def _collect(self, fetched_at: datetime) -> dict[str, Any]:
        today = fetched_at.date()
        yesterday = today - timedelta(days=1)
        query_start = f"{yesterday - timedelta(days=1):%Y-%m-%d} 00:00:00"
        query_end = f"{today:%Y-%m-%d} 00:00:00"

        day_rows = self._load_city_days(query_start, query_end)
        if not day_rows:
            raise ValueError("SsfbCityDay returned no rows for daily ranking")

        daily_rows: list[dict[str, Any]] = []
        daily_periods: list[str] = []
        # 昨日为主，前日兜底；18 城市组齐全才产出单日排名
        for window_end in (yesterday, yesterday - timedelta(days=1)):
            city_values: dict[str, tuple[int | None, dict[str, float | None]]] = {}
            for row in day_rows:
                day = row["data_time"].date() if isinstance(row["data_time"], datetime) else row["data_time"]
                if day != window_end:
                    continue
                city = row["city"]
                if city in city_values:
                    continue
                city_values[city] = (
                    row.get("group_id"),
                    {
                        "pm25": _number(row.get("pm25")),
                        "pm10": _number(row.get("pm10")),
                        "so2": _number(row.get("so2")),
                        "no2": _number(row.get("no2")),
                        "co": _number(row.get("co")),
                        "o3_8h": _number(row.get("o3_8h")),
                    },
                )
            if len(city_values) == 18:
                daily_periods.append(window_end.isoformat())
                daily_rows.extend(
                    build_ranking_rows(window_end.isoformat(), city_values, fetched_at)
                )
        return {"daily": daily_rows, "daily_periods": daily_periods}

    async def fetch_and_store(self) -> dict[str, Any]:
        fetched_at = self.now_factory().replace(microsecond=0)
        collected = self._collect(fetched_at)
        saved = await self._save(collected)
        daily_ranks = {
            row["period"]: row["rank_pm25"] for row in collected["daily"]
            if row["city"] == "许昌市"
        }
        result = {
            "fetched_at": fetched_at.isoformat(),
            "saved_daily": saved["daily"],
            "daily_periods": collected["daily_periods"],
            "xuchang_pm25_rank_daily": daily_ranks,
        }
        logger.info("xuchang_henan_ranking_recalc_completed", **result)
        return result

    async def _save(self, collected: dict[str, Any]) -> dict[str, int]:
        conn = await aiomysql.connect(**self.mysql_config)
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(RANKING_DDL)
                rows = collected["daily"]
                if rows:
                    await cursor.executemany(
                        RANKING_UPSERT, [_ranking_params(row) for row in rows]
                    )
                counts = {"daily": len(rows)}
            await conn.commit()
            return counts
        except Exception:
            await conn.rollback()
            raise
        finally:
            conn.close()


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
        row["pm25"], row["pm10"], row["so2"], row["no2"], row["co"], row["o3_8h"],
        row["rank_pm25"], row["rank_pm10"],
        row["rank_so2"], row["rank_no2"], row["rank_o3"], row["rank_co"],
        row["computed_at"],
    )

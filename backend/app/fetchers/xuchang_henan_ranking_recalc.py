"""Henan city cumulative rankings (local calculation, clearly non-official).

背景：河南省空气质量 APP（月/年累计排名来源）已于 2026-09 停服，中台仅
覆盖许昌市；为避免 Agent 自行计算导致口径漂移，由本任务统一计算河南省
18 城市组（含济源）的月/年累计统计与排名（另有日粒度排序）。

**口径声明：本任务产出为本地计算结果，不代表官方口径**，仅供省内城市
横向对比参考。修约规则与官方报表一致：

- 修约：银行家算法（四舍六入五成双，ROUND_HALF_EVEN）；
- 精度：PM2.5 与 CO 保留一位小数，PM10/SO2/NO2/O3 取整数；
- 单项浓度：SO2/NO2/PM10/PM2.5 为算术月均/年均，O3 取日最大 8 小时值
  第 90 百分位（nearest-rank），CO 取日均值第 95 百分位（nearest-rank），
  聚合后按上述规则修约，排名基于修约后的值；
- 排名规则：**数值越低排名越靠前**，相同值并列（standard competition：1,1,3）；
- PM10 缺口：源日值接口 2026-10 起不发布 PM10，由本城小时均值补齐后再
  参与统计；
- 日粒度（daily）：仅对官方发布日值排序展示，取原值不做修约与聚合。

结果写入 DataCrawler MySQL ``SsfbCityRanking``
（period_type=daily/monthly/yearly），每日重算当期，幂等覆盖。
月度及以上统计的官方口径以河南省生态环境厅/驻市监测中心发布为准。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any

import aiomysql
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.henan_ssfb_client import HenanSsfbClient
from config.settings import settings

logger = structlog.get_logger()

RANKING_TABLE = "SsfbCityRanking"

# 修约精度（位小数）：PM2.5 与 CO 一位小数，其余污染物整数
ROUND_PLACES = {"pm25": 1, "co": 1, "pm10": 0, "so2": 0, "no2": 0, "o3_8h_90": 0, "o3_8h": 0}

RANK_METRICS = ("pm25", "pm10", "so2", "no2", "o3_8h", "co")

RANK_COLUMN_MAP = {
    "pm25": "rank_pm25",
    "pm10": "rank_pm10",
    "so2": "rank_so2",
    "no2": "rank_no2",
    "o3_8h": "rank_o3",
    "co": "rank_co",
}

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

DAY_QUERY = """
SELECT City AS city, GroupID AS group_id, DataTime AS data_time,
       PM25 AS pm25, PM10 AS pm10, O3_8H AS o3_8h, NO2 AS no2, SO2 AS so2, CO AS co
FROM SsfbCityDay
WHERE DataTime >= %s AND DataTime < %s
ORDER BY city, data_time
"""

# 实测源接口日值的 PM10 字段自 2026-10 起不再发布，小时值仍正常；
# PM10 日均按"本城当日小时算术平均"补齐后参与统计。
HOUR_PM10_QUERY = """
SELECT City AS city, DATE(DataTime) AS data_date, AVG(PM10) AS pm10_mean
FROM SsfbCityHour
WHERE DataTime >= %s AND DataTime < %s AND PM10 IS NOT NULL
GROUP BY City, DATE(DataTime)
"""


def round_half_even(value: float | None, places: int) -> float | None:
    """银行家算法修约（四舍六入五成双）。"""
    if value is None:
        return None
    quantum = Decimal("0.1") if places == 1 else Decimal("1")
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_EVEN))


def percentile_nearest_rank(sorted_values: list[float], p: float) -> float | None:
    """Nearest-rank 百分位（ceil(p/100 * n) 位）。"""
    if not sorted_values:
        return None
    rank = max(1, -(-int(p * len(sorted_values)) // 100))
    return sorted_values[min(rank, len(sorted_values)) - 1]


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


class CityCumulative:
    """单城市一段时间的累计统计（聚合后按官方修约规则修约）。"""

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

    def _o3_8h_90(self) -> float | None:
        return percentile_nearest_rank(sorted(self.series["o3_8h"]), 90)

    def _co_95(self) -> float | None:
        return percentile_nearest_rank(sorted(self.series["co"]), 95)

    def rounded_metrics(self) -> dict[str, float | None]:
        """聚合 → 修约（银行家算法，PM2.5/CO 一位小数，其余整数）。

        返回键与表列对齐：O3_8H 装 O3-8h 第 90 百分位，CO 装 CO 第 95 百分位。
        """
        raw = {
            "pm25": self._mean("pm25"),
            "pm10": self._mean("pm10"),
            "so2": self._mean("so2"),
            "no2": self._mean("no2"),
            "o3_8h": self._o3_8h_90(),
            "co": self._co_95(),
        }
        return {
            key: round_half_even(value, ROUND_PLACES.get(key, 0))
            for key, value in raw.items()
        }

    @classmethod
    def from_days(cls, city: str, group_id: int | None, days: list[dict[str, Any]]) -> "CityCumulative":
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


def build_cumulative_ranking_rows(
    period_type: str,
    period: str,
    city_cumulatives: dict[str, CityCumulative],
    computed_at: datetime,
) -> list[dict[str, Any]]:
    """修约 → 排名（基于修约后的值），产出累计统计排名行。"""
    metrics_by_city = {
        city: agg.rounded_metrics() for city, agg in city_cumulatives.items()
    }
    ranked_by_metric = {
        metric: compute_rank(
            [
                {"city": city, "value": metrics_by_city[city].get(metric)}
                for city in city_cumulatives
            ],
            key="value",
        )
        for metric in RANK_METRICS
    }
    ranks: dict[str, dict[str, int | None]] = {city: {} for city in city_cumulatives}
    for metric, rows in ranked_by_metric.items():
        for row in rows:
            ranks[row["city"]][RANK_COLUMN_MAP[metric]] = row["rank"]

    return [
        {
            "period_type": period_type,
            "period": period,
            "city": city,
            "group_id": city_cumulatives[city].group_id,
            "days": city_cumulatives[city].days,
            "valid_days": city_cumulatives[city].valid_days,
            "pm_valid_days": city_cumulatives[city].pm_valid_days,
            **metrics_by_city[city],
            **ranks[city],
            "computed_at": computed_at,
        }
        for city in city_cumulatives
    ]


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


def _chunked(values: list[int], size: int) -> list[list[int]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


class XuchangHenanRankingRecalcFetcher(DataFetcher):
    """Daily local calculation of Henan 18-city cumulative rankings (non-official)."""

    def __init__(
        self,
        client: HenanSsfbClient | None = None,
        now_factory=lambda: datetime.now(),
        mysql_config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            name="xuchang_henan_ranking_recalc_fetcher",
            description="本地计算河南18城市组月/年累计统计与排名(银行家修约,非官方口径)入库DataCrawler",
            schedule="10 6 * * *",
            version="3.0.0",
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
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)
        yesterday = today - timedelta(days=1)
        query_start = f"{year_start:%Y-%m-%d} 00:00:00"
        query_end = f"{today + timedelta(days=1):%Y-%m-%d} 00:00:00"

        day_rows = self._load_city_days(query_start, query_end)
        if not day_rows:
            raise ValueError("SsfbCityDay returned no rows for ranking calculation")
        _fill_pm10_from_hours(day_rows, self._load_pm10_hour_means(query_start, query_end))

        monthly_cities = self._cumulative_window(day_rows, month_start, today)
        yearly_cities = self._cumulative_window(day_rows, year_start, today)

        monthly_rows = build_cumulative_ranking_rows(
            "monthly", month_start.strftime("%Y-%m"), monthly_cities, fetched_at
        )
        yearly_rows = build_cumulative_ranking_rows(
            "yearly", str(year_start.year), yearly_cities, fetched_at
        )

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
            "monthly": monthly_rows,
            "yearly": yearly_rows,
            "daily": daily_rows,
            "daily_periods": daily_periods,
            "day_count": len(day_rows),
        }

    @staticmethod
    def _cumulative_window(
        day_rows: list[dict[str, Any]], start: date, end: date
    ) -> dict[str, CityCumulative]:
        window: dict[str, CityCumulative] = {}
        for row in day_rows:
            day = row["data_time"].date() if isinstance(row["data_time"], datetime) else row["data_time"]
            if not (start <= day <= end):
                continue
            city = row["city"]
            if city not in window:
                window[city] = CityCumulative(city, row.get("group_id"))
            window[city].add_day(row)
        return window

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
        monthly_pm25 = {row["city"]: row["rank_pm25"] for row in collected["monthly"]}
        daily_pm25 = {
            row["period"]: row["rank_pm25"] for row in collected["daily"]
            if row["city"] == "许昌市"
        }
        result = {
            "fetched_at": fetched_at.isoformat(),
            "day_rows": collected["day_count"],
            "saved_monthly": saved["monthly"],
            "saved_yearly": saved["yearly"],
            "saved_daily": saved["daily"],
            "daily_periods": collected["daily_periods"],
            "xuchang_pm25_rank_monthly": monthly_pm25.get("许昌市"),
            "xuchang_pm25_rank_daily": daily_pm25,
            "jiyuan_pm25_rank_monthly": monthly_pm25.get("济源市"),
        }
        logger.info("xuchang_henan_ranking_recalc_completed", **result)
        return result

    async def _save(self, collected: dict[str, Any]) -> dict[str, int]:
        conn = await aiomysql.connect(**self.mysql_config)
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(RANKING_DDL)
                counts = {}
                for kind in ("monthly", "yearly", "daily"):
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
        row["period_type"], row["period"], row["city"], row.get("group_id"),
        row.get("data_start"), row.get("data_end"), row.get("days"),
        row.get("valid_days"), row.get("pm_valid_days"),
        row["pm25"], row["pm10"], row["so2"], row["no2"],
        row["co"], row["o3_8h"],
        row["rank_pm25"], row["rank_pm10"],
        row["rank_so2"], row["rank_no2"], row["rank_o3"], row["rank_co"],
        row["computed_at"],
    )

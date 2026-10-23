"""Fetch Henan real-time publish data at county (区县) granularity.

数据来源为河南省空气质量实时发布系统（详见
``app.integrations.henan_ssfb_client``）。平台前端"区县"页签即调用
城市组接口（airQualityGroupHours/Days）的区县口径（queryType=2），
cityIDs 传区县树（GetGroupCountyTree，189 叶子）+ 济源示范区（218，
不在树中但可查），因此本采集与平台"区县"数据完全同源同口径：

- ``xuchang_henan_county_publish_fetcher``：全省区县（含济源、功能
  区）的小时值与日值 → ``SsfbCountyHour`` / ``SsfbCountyDay``，目录
  → ``SsfbDimCounty``；
- 区县**排名不落表**：排名语义在 cube 语义层
  ``SsfbCountyHourRank`` / ``SsfbCountyDayRank``（MySQL 8 窗口函数
  实时现算，升序并列），经 xuchang_cube_metrics 工具实时查询，与平
  台"区县排名"一致（2026-10-10 全省 188 区县锚点逐位核对）。

注意：区县日值在次日白天陆续发布，个别区县（如郑州经开区/许昌开发
区）发布偏晚，靠回看两日 + 每天 07/10/13/16/19/22 时随首波抓取自动
补齐；小时值三波窗口策略与城市/站点一致（见
``xuchang_henan_ssfb_publish.resolve_collection_window``）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.xuchang_henan_ssfb_publish import (
    MYSQL_EXECUTEMANY_CHUNK,
    COUNTY_RECONCILE_LOOKBACK_DAYS,
    COUNTY_WAVE_MINUTES,
    HenanSsfbMySqlStorage,
    day_fetch_dates,
    resolve_collection_window,
    wave_schedule,
)
from app.integrations.henan_ssfb_client import (
    JIYUAN_COUNTY_GROUP_ID,
    HenanSsfbClient,
    county_groups_from_tree,
    normalize_city_name,
)

logger = structlog.get_logger()

COUNTY_HOUR_TABLE = "SsfbCountyHour"
COUNTY_DAY_TABLE = "SsfbCountyDay"
DIM_COUNTY_TABLE = "SsfbDimCounty"

DIM_COUNTY_DDL = """
CREATE TABLE IF NOT EXISTS SsfbDimCounty (
    GroupID INT NOT NULL PRIMARY KEY,
    CountyName VARCHAR(50) NOT NULL,
    CityName VARCHAR(50) NOT NULL,
    CityCode VARCHAR(20) NULL,
    UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

DIM_COUNTY_UPSERT = """
INSERT INTO SsfbDimCounty (GroupID, CountyName, CityName, CityCode) VALUES (%s, %s, %s, %s)
ON DUPLICATE KEY UPDATE CountyName=VALUES(CountyName), CityName=VALUES(CityName),
    CityCode=VALUES(CityCode)
"""

COUNTY_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    County VARCHAR(50) NOT NULL,
    City VARCHAR(50) NULL,
    CityCode VARCHAR(20) NULL,
    GroupID INT NOT NULL,
    DataTime DATETIME NOT NULL,
    AQI INT NULL,
    Quality VARCHAR(20) NULL,
    Grade INT NULL,
    PM25 DOUBLE NULL,
    PM10 DOUBLE NULL,
    O3 DOUBLE NULL,
    O3_8H DOUBLE NULL,
    NO2 DOUBLE NULL,
    SO2 DOUBLE NULL,
    CO DOUBLE NULL,
    MainPollutant VARCHAR(50) NULL,
    FetchedAt DATETIME NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY UK_{table} (GroupID, DataTime)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

COUNTY_UPSERT_SQL_TEMPLATE = """
INSERT INTO {table}
    (County, City, CityCode, GroupID, DataTime, AQI, Quality, Grade,
     PM25, PM10, O3, O3_8H, NO2, SO2, CO, MainPollutant, FetchedAt)
VALUES ({placeholders})
ON DUPLICATE KEY UPDATE
    County=VALUES(County), City=VALUES(City), CityCode=VALUES(CityCode),
    AQI=VALUES(AQI), Quality=VALUES(Quality), Grade=VALUES(Grade),
    PM25=VALUES(PM25), PM10=VALUES(PM10), O3=VALUES(O3), O3_8H=VALUES(O3_8H),
    NO2=VALUES(NO2), SO2=VALUES(SO2), CO=VALUES(CO),
    MainPollutant=VALUES(MainPollutant), FetchedAt=VALUES(FetchedAt)
"""

COUNTY_RECORD_COLUMNS = (
    "county", "city", "city_code", "group_id", "data_time", "aqi", "quality",
    "grade", "pm25", "pm10", "o3", "o3_8h", "no2", "so2", "co",
    "main_pollutant", "fetched_at",
)


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _int_number(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None


def _county_record(
    row: dict[str, Any],
    county_meta: dict[int, dict[str, Any]],
    fetched_at: datetime,
    kind: str,
) -> dict[str, Any] | None:
    group_id = _int_number(row.get("groupID"))
    if group_id is None:
        return None
    meta = county_meta.get(group_id, {})
    county = normalize_city_name(row.get("groupName")) or meta.get("name", "")
    if not county:
        return None
    when = _parse_time(row.get("lst"))
    if when is None or when > fetched_at:
        # 接口会返回当日尚未发布的小时段(全 NULL)，丢弃未来时段。
        return None
    return {
        "county": county,
        "city": meta.get("city") or normalize_city_name(row.get("area")) or None,
        "city_code": meta.get("code"),
        "group_id": group_id,
        "data_time": when if kind == "hour" else when.replace(hour=0, minute=0),
        "aqi": _int_number(row.get("aqi")),
        "quality": str(row.get("quality") or "").strip() or None,
        "grade": _int_number(row.get("grade")),
        "pm25": _number(row.get("pm25")),
        "pm10": _number(row.get("pm10")),
        "o3": _number(row.get("o3")),
        "o3_8h": _number(row.get("o3_8H")),
        "no2": _number(row.get("no2")),
        "so2": _number(row.get("so2")),
        "co": _number(row.get("co")),
        "main_pollutant": str(row.get("primary_pollutant_name") or "").strip() or None,
        "fetched_at": fetched_at,
    }


def _chunked(rows: list[tuple], size: int) -> list[list[tuple]]:
    return [rows[index:index + size] for index in range(0, len(rows), size)]


class HenanCountyMySqlStorage(HenanSsfbMySqlStorage):
    """Upsert ssfb county rows into the local DataCrawler MySQL database."""

    async def save(self, records: list[dict[str, Any]], kind: str) -> int:
        """持久化区县记录；kind 决定目标表（hour/day）。"""
        if not records:
            return 0
        table = COUNTY_HOUR_TABLE if kind == "hour" else COUNTY_DAY_TABLE
        ddl = COUNTY_DDL.format(table=table)
        sql_template = COUNTY_UPSERT_SQL_TEMPLATE
        ordered = COUNTY_RECORD_COLUMNS
        placeholders = ",".join(["%s"] * len(ordered))
        upsert_sql = sql_template.format(table=table, placeholders=placeholders)
        rows = [
            tuple(record[column] for column in ordered)
            for record in records
        ]
        connection = await self._connect()
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(ddl)
                for chunk in _chunked(rows, MYSQL_EXECUTEMANY_CHUNK):
                    await cursor.executemany(upsert_sql, chunk)
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise
        finally:
            connection.close()
        return len(rows)

    async def upsert_dim_county(
        self, counties: dict[int, dict[str, Any]]
    ) -> int:
        """维护 SsfbDimCounty（区县目录，含济源）。"""
        connection = await self._connect()
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(DIM_COUNTY_DDL)
                await cursor.executemany(
                    DIM_COUNTY_UPSERT,
                    [
                        (group_id, meta.get("name"), meta.get("city"), meta.get("code"))
                        for group_id, meta in sorted(counties.items())
                    ],
                )
            await connection.commit()
            return len(counties)
        except Exception:
            await connection.rollback()
            raise
        finally:
            connection.close()


class XuchangHenanCountyPublishFetcher(DataFetcher):
    """Hourly rollup of Henan county-group data (platform-consistent)."""

    def __init__(
        self,
        client: HenanSsfbClient | None = None,
        storage: HenanCountyMySqlStorage | None = None,
        now_factory=lambda: datetime.now(),
    ) -> None:
        super().__init__(
            name="xuchang_henan_county_publish_fetcher",
            description="抓取河南实时发布系统全省区县(含济源/功能区)小时/日值入库DataCrawler",
            schedule=wave_schedule(COUNTY_WAVE_MINUTES),
            version="1.2.0",
        )
        self.client = client or HenanSsfbClient()
        self.storage = storage or HenanCountyMySqlStorage()
        self.now_factory = now_factory

    def _target_counties(
        self, tree: list[dict[str, Any]]
    ) -> dict[int, dict[str, Any]]:
        """区县目录 = 区县树叶子 + 济源（218，平台区县排名同款全集）。"""
        counties = county_groups_from_tree(tree)
        if JIYUAN_COUNTY_GROUP_ID not in counties:
            counties[JIYUAN_COUNTY_GROUP_ID] = {
                "name": "济源市",
                "city": "济源市",
                "code": None,
            }
        return counties

    def _collect(self, fetched_at: datetime) -> dict[str, Any]:
        window = resolve_collection_window(
            fetched_at,
            COUNTY_WAVE_MINUTES,
            reconcile_lookback_days=COUNTY_RECONCILE_LOOKBACK_DAYS,
        )

        counties = self._target_counties(self.client.county_tree())
        if not counties:
            raise ValueError("ssfb county tree returned no counties")
        county_ids = sorted(counties)

        hours = self.client.group_hours(
            county_ids, window["hour_start"], window["hour_end"], query_type="2"
        )
        day_rows: list[dict[str, Any]] = []
        if window["fetch_days"]:
            # 区县日值发布偏晚（个别功能区次日下午才出），回看两日自动补齐。
            for day_text in day_fetch_dates(fetched_at):
                day_rows.extend(
                    self.client.group_days(
                        county_ids, day_text, day_text, query_type="2"
                    )
                )
        hour_records = [
            record
            for row in hours
            if (record := _county_record(row, counties, fetched_at, "hour")) is not None
        ]
        day_records = [
            record
            for row in day_rows
            if (record := _county_record(row, counties, fetched_at, "day")) is not None
        ]
        return {
            "hour": hour_records,
            "day": day_records,
            "counties": counties,
            "window": window,
        }

    async def fetch_and_store(self) -> dict[str, Any]:
        fetched_at = self.now_factory().replace(microsecond=0)
        collected = self._collect(fetched_at)
        saved_hour = await self.storage.save(collected["hour"], "hour")
        saved_day = await self.storage.save(collected["day"], "day")
        dim_counties = await self.storage.upsert_dim_county(collected["counties"])
        result = {
            "fetched_at": fetched_at.isoformat(),
            "hour_start": collected["window"]["hour_start"],
            "days_fetched": collected["window"]["fetch_days"],
            "hour_rows": len(collected["hour"]),
            "saved_hour_rows": saved_hour,
            "day_rows": len(collected["day"]),
            "saved_day_rows": saved_day,
            "dim_counties": dim_counties,
        }
        logger.info("xuchang_henan_county_publish_completed", **result)
        return result

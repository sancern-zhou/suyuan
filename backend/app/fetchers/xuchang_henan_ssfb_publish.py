"""Fetch Henan real-time publish data (18 cities incl. Jiyuan + Xuchang sites).

数据来源为河南省空气质量实时发布系统（详见
``app.integrations.henan_ssfb_client``）。该平台小时/日值仅保留约
最近 8 天。三波采样点保持每小时 3 次（首波覆盖整点后约 15-20 分钟的
按小时发布、次波覆盖迟到发布、第三波覆盖平台 :27-:28 批量修正），但
每波只回看最近少数小时：首波 6 小时、次波/三波 2 小时，每日 00:xx
首波再做一次 3 天全量对账补齐断档（此前每波都重拉"昨日 00:00 →
今日 23:00"全窗口，重复率约 150 倍）。日值单独降频：次日 06:45 后
才发布（夜间为空发布）、个别区县次日下午才出，07:00 起每 3 小时随
首波抓一次即可。结果写入本地 MySQL 采集库 ``DataCrawler``（与
``CityDay``/``CityYearPm25Avg`` 等长历史表同库）：

- ``xuchang_henan_ssfb_city_publish_fetcher``：18 个城市组（含济源，
  queryType=1）的小时值与日值 → ``SsfbCityHour`` / ``SsfbCityDay``。
  济源在既有发布历史中长期缺失，此表用于后续排名补缺。
- ``xuchang_henan_ssfb_site_publish_fetcher``：站点树"县级"根下许昌
  市辖区内的县级站（queryType=2，自动剔除国控 GK）的小时值与日值 →
  ``SsfbSiteHour`` / ``SsfbSiteDay``。

区县组接口无独立数据（区县 ID 被平台错误映射回城市组），区县口径
需用站点数据聚合，故不采集区县组。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import aiomysql
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.henan_ssfb_client import (
    HenanSsfbClient,
    build_henan_district_directory,
    city_groups_from_tree,
    normalize_city_name,
    site_leaves_from_tree,
)
from config.settings import settings

logger = structlog.get_logger()

CITY_HOUR_TABLE = "SsfbCityHour"
CITY_DAY_TABLE = "SsfbCityDay"
SITE_HOUR_TABLE = "SsfbSiteHour"
SITE_DAY_TABLE = "SsfbSiteDay"
DIM_CITY_TABLE = "SsfbDimCity"
DIM_DISTRICT_TABLE = "SsfbDimDistrict"
DIM_SITE_TABLE = "SsfbDimSite"

DIM_CITY_DDL = """
CREATE TABLE IF NOT EXISTS SsfbDimCity (
    GroupID INT NOT NULL PRIMARY KEY,
    CityName VARCHAR(50) NOT NULL,
    CityCode VARCHAR(20) NULL,
    UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

DIM_DISTRICT_DDL = """
CREATE TABLE IF NOT EXISTS SsfbDimDistrict (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    CityName VARCHAR(50) NOT NULL,
    DistrictName VARCHAR(50) NOT NULL,
    DistrictCode VARCHAR(20) NULL,
    RootName VARCHAR(20) NULL,
    UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY UK_SsfbDimDistrict (CityName, DistrictName, RootName)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

DIM_SITE_DDL = """
CREATE TABLE IF NOT EXISTS SsfbDimSite (
    SiteID INT NOT NULL PRIMARY KEY,
    SiteName VARCHAR(100) NOT NULL,
    County VARCHAR(50) NULL,
    OnlineType VARCHAR(10) NULL,
    UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

DIM_CITY_UPSERT = """
INSERT INTO SsfbDimCity (GroupID, CityName, CityCode) VALUES (%s, %s, %s)
ON DUPLICATE KEY UPDATE CityName=VALUES(CityName), CityCode=VALUES(CityCode)
"""

DIM_DISTRICT_UPSERT = """
INSERT INTO SsfbDimDistrict (CityName, DistrictName, DistrictCode, RootName)
VALUES (%s, %s, %s, %s)
ON DUPLICATE KEY UPDATE DistrictCode=VALUES(DistrictCode), RootName=VALUES(RootName)
"""

DIM_SITE_UPSERT = """
INSERT INTO SsfbDimSite (SiteID, SiteName, County, OnlineType) VALUES (%s, %s, %s, %s)
ON DUPLICATE KEY UPDATE SiteName=VALUES(SiteName), County=VALUES(County), OnlineType=VALUES(OnlineType)
"""

# "县级"根分支 + 许昌市辖区内的县级站；GK(国控)不采集。
# 全省采集：站点树两根（省辖市=城区站 92 区县分组 / 县级=县·县级市站 101 区县分组）
# 合计覆盖全省 193 个区县（含功能区）；国控站（GK）剔除。
SITE_EXCLUDED_TYPES = {"GK"}

SITE_REQUEST_CHUNK_SIZE = 80
MYSQL_EXECUTEMANY_CHUNK = 200

# ---- 采集窗口策略（三波采样，窗口按波次收窄）----
# 首波回看 6 小时，覆盖平台按小时发布（约整点后 15-20 分钟）与几分钟级
# 迟到；次波/三波回看 2 小时，覆盖迟到发布与平台 :27-:28 批量修正。
FIRST_WAVE_LOOKBACK_HOURS = 6
RETRY_WAVE_LOOKBACK_HOURS = 2
# 每日 00:xx 首波做一次全量对账，回看 3 天（平台保留约 8 天，取 3 天覆盖
# 周末级断档）；手动作业（分钟不在调度波次内）也按该窗口执行。
RECONCILE_HOUR = 0
RECONCILE_LOOKBACK_DAYS = 3
# 日值发布节奏：次日约 06:45 后开始发布（00:45-06:45 为空发布），个别
# 区县次日下午才出。07:00 起每 3 小时随首波抓一次。
DAY_FETCH_HOURS = frozenset({7, 10, 13, 16, 19, 22})

# 三波分钟必须与 ``schedule`` 一致（窗口判定依赖当前分钟属于哪一波），
# 由 wave_schedule() 从同一元组生成，避免两处漂移。
CITY_WAVE_MINUTES = (14, 20, 55)
SITE_WAVE_MINUTES = (16, 22, 57)
COUNTY_WAVE_MINUTES = (18, 24, 59)


def wave_schedule(wave_minutes: tuple[int, ...]) -> str:
    """由波次分钟生成 cron 表达式，保证调度与窗口策略同源。"""
    return ",".join(str(minute) for minute in wave_minutes) + " * * * *"


def resolve_collection_window(
    fetched_at: datetime, wave_minutes: tuple[int, ...]
) -> dict[str, Any]:
    """按波次解析小时值查询窗口与本轮是否抓日值。

    窗口右端固定为当日 23:00，平台只返回已发布时段（未发布/未来时段由
    记录过滤丢弃）。返回 ``hour_start``/``hour_end`` 查询字符串与
    ``fetch_days`` 标记。
    """
    hour_floor = fetched_at.replace(minute=0, second=0, microsecond=0)
    minute = fetched_at.minute
    # 对账窗口按整日对齐（回看 N 天的 00:00 起），与旧的"昨日 00:00"口径同型。
    reconcile_start = (hour_floor - timedelta(days=RECONCILE_LOOKBACK_DAYS)).replace(hour=0)
    if minute not in wave_minutes:
        # 手动/补数运行：按全量对账窗口，顺带刷新日值。
        start, fetch_days = reconcile_start, True
    elif minute == wave_minutes[0] and fetched_at.hour == RECONCILE_HOUR:
        start, fetch_days = reconcile_start, False
    elif minute == wave_minutes[0]:
        start = hour_floor - timedelta(hours=FIRST_WAVE_LOOKBACK_HOURS)
        fetch_days = fetched_at.hour in DAY_FETCH_HOURS
    else:
        start, fetch_days = hour_floor - timedelta(hours=RETRY_WAVE_LOOKBACK_HOURS), False
    return {
        "hour_start": f"{start:%Y-%m-%d %H:%M:%S}",
        "hour_end": f"{hour_floor.replace(hour=23):%Y-%m-%d %H:%M:%S}",
        "fetch_days": fetch_days,
    }


def day_fetch_dates(fetched_at: datetime) -> list[str]:
    """日值回看两日 [D-2, D-1]（D 为运行日）：次日发布 + 迟到记录自动补齐。"""
    day_start = fetched_at.date() - timedelta(days=1)
    return [(day_start - timedelta(days=1)).isoformat(), day_start.isoformat()]

CITY_UPsert_SQL_TEMPLATE = """
INSERT INTO {table}
    (City, CityCode, GroupID, DataTime, AQI, Quality, Grade,
     PM25, PM10, O3, O3_8H, NO2, SO2, CO, MainPollutant, FetchedAt)
VALUES ({placeholders})
ON DUPLICATE KEY UPDATE
    CityCode=VALUES(CityCode), GroupID=VALUES(GroupID), AQI=VALUES(AQI),
    Quality=VALUES(Quality), Grade=VALUES(Grade), PM25=VALUES(PM25),
    PM10=VALUES(PM10), O3=VALUES(O3), O3_8H=VALUES(O3_8H), NO2=VALUES(NO2),
    SO2=VALUES(SO2), CO=VALUES(CO), MainPollutant=VALUES(MainPollutant),
    FetchedAt=VALUES(FetchedAt)
"""

SITE_UPSERT_SQL_TEMPLATE = """
INSERT INTO {table}
    (SiteID, SiteName, OnlineType, City, County, Area, DataTime,
     AQI, Quality, Grade, PM25, PM10, O3, O3_8H, NO2, SO2, CO,
     MainPollutant, FetchedAt)
VALUES ({placeholders})
ON DUPLICATE KEY UPDATE
    SiteName=VALUES(SiteName), OnlineType=VALUES(OnlineType),
    City=VALUES(City), County=VALUES(County), Area=VALUES(Area),
    AQI=VALUES(AQI), Quality=VALUES(Quality), Grade=VALUES(Grade),
    PM25=VALUES(PM25), PM10=VALUES(PM10), O3=VALUES(O3), O3_8H=VALUES(O3_8H),
    NO2=VALUES(NO2), SO2=VALUES(SO2), CO=VALUES(CO),
    MainPollutant=VALUES(MainPollutant), FetchedAt=VALUES(FetchedAt)
"""

_CITY_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    City VARCHAR(50) NOT NULL,
    CityCode VARCHAR(20) NULL,
    GroupID INT NULL,
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
    UNIQUE KEY UK_{table} (City, DataTime)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_SITE_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    SiteID INT NOT NULL,
    SiteName VARCHAR(100) NULL,
    OnlineType VARCHAR(10) NULL,
    City VARCHAR(50) NULL,
    County VARCHAR(50) NULL,
    Area VARCHAR(50) NULL,
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
    UNIQUE KEY UK_{table} (SiteID, DataTime)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


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


def _city_record(
    row: dict[str, Any], group_names: dict[int, dict[str, Any]], fetched_at: datetime, kind: str
) -> dict[str, Any] | None:
    group_id = _int_number(row.get("groupID"))
    if group_id is None:
        return None
    group_meta = group_names.get(group_id, {})
    city = normalize_city_name(row.get("groupName")) or group_meta.get("name", "")
    if not city:
        return None
    when = _parse_time(row.get("lst"))
    if when is None or when > fetched_at:
        # 接口会返回当日尚未发布的小时段(全 NULL)，丢弃未来时段。
        return None
    return {
        "city": city,
        "city_code": str(row.get("Code") or "").strip() or group_meta.get("code"),
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


def _site_record(
    row: dict[str, Any],
    site_meta: dict[int, dict[str, Any]],
    fetched_at: datetime,
    kind: str,
) -> dict[str, Any] | None:
    site_id = _int_number(row.get("siteID"))
    if site_id is None:
        return None
    meta = site_meta.get(site_id, {})
    when = _parse_time(row.get("lst"))
    if when is None or when > fetched_at:
        # 接口会返回当日尚未发布的小时段(全 NULL)，丢弃未来时段。
        return None
    return {
        "site_id": site_id,
        "site_name": str(row.get("siteName") or meta.get("site_name") or "").strip() or None,
        "online_type": str(row.get("onlineType") or meta.get("online_type") or "").strip() or None,
        "city": meta.get("city") or normalize_city_name(row.get("area")) or None,
        "county": meta.get("county"),
        "area": str(row.get("area") or "").strip() or None,
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


def _chunked(values: list[int], size: int) -> list[list[int]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


class HenanSsfbMySqlStorage:
    """Upsert ssfb rows into the local DataCrawler MySQL database."""

    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.crawler_mysql_url

    def _connection_kwargs(self) -> dict[str, Any]:
        # settings.crawler_mysql_url 为 SQLAlchemy aiomysql 方言 URL。
        parsed = self._url.split("://", 1)[1]
        auth_host, database = parsed.split("/", 1)
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

    async def _connect(self) -> aiomysql.Connection:
        return await aiomysql.connect(**self._connection_kwargs())

    async def save(self, records: list[dict[str, Any]], kind: str) -> int:
        """持久化城市或站点记录；kind 决定目标表（hour/day）。"""
        if not records:
            return 0
        if records[0].get("site_id") is not None:
            table = SITE_HOUR_TABLE if kind == "hour" else SITE_DAY_TABLE
            time_column = "DataTime"
            ddl = _SITE_DDL.format(table=table)
            sql_template = SITE_UPSERT_SQL_TEMPLATE
            ordered = (
                "site_id", "site_name", "online_type", "city", "county", "area",
                "data_time", "aqi", "quality", "grade", "pm25", "pm10", "o3",
                "o3_8h", "no2", "so2", "co", "main_pollutant", "fetched_at",
            )
        else:
            table = CITY_HOUR_TABLE if kind == "hour" else CITY_DAY_TABLE
            time_column = "DataTime"
            ddl = _CITY_DDL.format(table=table)
            sql_template = CITY_UPsert_SQL_TEMPLATE
            ordered = (
                "city", "city_code", "group_id", "data_time", "aqi", "quality",
                "grade", "pm25", "pm10", "o3", "o3_8h", "no2", "so2", "co",
                "main_pollutant", "fetched_at",
            )
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
                for chunk in _chunked_rows(rows, MYSQL_EXECUTEMANY_CHUNK):
                    await cursor.executemany(upsert_sql, chunk)
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise
        finally:
            connection.close()
        return len(rows)


    async def upsert_dim_city(self, groups: dict[int, dict[str, Any]]) -> int:
        """维护 SsfbDimCity（18 城市组目录，含济源）。"""
        connection = await self._connect()
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(DIM_CITY_DDL)
                await cursor.executemany(
                    DIM_CITY_UPSERT,
                    [
                        (group_id, meta.get("name"), meta.get("code"))
                        for group_id, meta in sorted(groups.items())
                    ],
                )
            await connection.commit()
            return len(groups)
        except Exception:
            await connection.rollback()
            raise
        finally:
            connection.close()

    async def upsert_dim_district(self, tree: list[dict[str, Any]]) -> int:
        """维护 SsfbDimDistrict（全省区县目录）。"""
        rows = build_henan_district_directory(tree)
        connection = await self._connect()
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(DIM_DISTRICT_DDL)
                await cursor.executemany(
                    DIM_DISTRICT_UPSERT,
                    [
                        (row["city"], row["name"], row["code"], row["system"])
                        for row in rows
                    ],
                )
            await connection.commit()
            return len(rows)
        except Exception:
            await connection.rollback()
            raise
        finally:
            connection.close()

    async def upsert_dim_site(self, sites: list[dict[str, Any]]) -> int:
        """维护 SsfbDimSite（许昌县级站目录，剔除国控）。"""
        connection = await self._connect()
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(DIM_SITE_DDL)
                await cursor.executemany(
                    DIM_SITE_UPSERT,
                    [
                        (
                            site["site_id"], site["site_name"],
                            site.get("county"), site.get("online_type"),
                        )
                        for site in sites
                    ],
                )
            await connection.commit()
            return len(sites)
        except Exception:
            await connection.rollback()
            raise
        finally:
            connection.close()


def _chunked_rows(rows: list[tuple], size: int) -> list[list[tuple]]:
    return [rows[index:index + size] for index in range(0, len(rows), size)]


class XuchangHenanSsfbCityPublishFetcher(DataFetcher):
    """Hourly rollup of the 18 Henan city groups (incl. Jiyuan)."""

    def __init__(
        self,
        client: HenanSsfbClient | None = None,
        storage: HenanSsfbMySqlStorage | None = None,
        now_factory=lambda: datetime.now(),
    ) -> None:
        super().__init__(
            name="xuchang_henan_ssfb_city_publish_fetcher",
            description="抓取河南实时发布系统18城市组(含济源)小时/日值入库DataCrawler",
            schedule=wave_schedule(CITY_WAVE_MINUTES),
            version="1.1.0",
        )
        self.client = client or HenanSsfbClient()
        self.storage = storage or HenanSsfbMySqlStorage()
        self.now_factory = now_factory

    def _collect(self, fetched_at: datetime) -> dict[str, Any]:
        window = resolve_collection_window(fetched_at, CITY_WAVE_MINUTES)

        group_names = city_groups_from_tree(self.client.city_tree())
        if not group_names:
            raise ValueError("ssfb city tree returned no groups")
        city_ids = sorted(group_names)

        hours = self.client.group_hours(
            city_ids, window["hour_start"], window["hour_end"]
        )
        days: list[dict[str, Any]] = []
        if window["fetch_days"]:
            day_start, day_end = day_fetch_dates(fetched_at)
            days = self.client.group_days(city_ids, day_start, day_end)
        return {
            "hour": [
                record
                for row in hours
                if (record := _city_record(row, group_names, fetched_at, "hour")) is not None
            ],
            "day": [
                record
                for row in days
                if (record := _city_record(row, group_names, fetched_at, "day")) is not None
            ],
            "group_names": group_names,
            "window": window,
        }

    async def fetch_and_store(self) -> dict[str, Any]:
        fetched_at = self.now_factory().replace(microsecond=0)
        collected = self._collect(fetched_at)
        saved_hour = await self.storage.save(collected["hour"], "hour")
        saved_day = await self.storage.save(collected["day"], "day")
        dim_cities = await self.storage.upsert_dim_city(collected["group_names"])
        cities = sorted({record["city"] for record in collected["hour"]})
        result = {
            "fetched_at": fetched_at.isoformat(),
            "hour_start": collected["window"]["hour_start"],
            "days_fetched": collected["window"]["fetch_days"],
            "hour_rows": len(collected["hour"]),
            "saved_hour_rows": saved_hour,
            "day_rows": len(collected["day"]),
            "saved_day_rows": saved_day,
            "dim_cities": dim_cities,
            "cities": cities,
        }
        logger.info("xuchang_henan_ssfb_city_publish_completed", **result)
        return result


class XuchangHenanSsfbSitePublishFetcher(DataFetcher):
    """Hourly rollup of Xuchang county-level sites from the county tree."""

    def __init__(
        self,
        client: HenanSsfbClient | None = None,
        storage: HenanSsfbMySqlStorage | None = None,
        now_factory=lambda: datetime.now(),
        request_chunk_size: int = SITE_REQUEST_CHUNK_SIZE,
    ) -> None:
        super().__init__(
            name="xuchang_henan_ssfb_site_publish_fetcher",
            description="抓取河南实时发布系统全省区县站点(两根树,剔除国控)小时/日值入库DataCrawler",
            schedule=wave_schedule(SITE_WAVE_MINUTES),
            version="1.2.0",
        )
        self.client = client or HenanSsfbClient()
        self.storage = storage or HenanSsfbMySqlStorage()
        self.now_factory = now_factory
        self.request_chunk_size = request_chunk_size

    def _target_sites(self, tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sites = site_leaves_from_tree(tree)
        return [site for site in sites if site.get("online_type") not in SITE_EXCLUDED_TYPES]

    def _collect(self, fetched_at: datetime) -> dict[str, Any]:
        window = resolve_collection_window(fetched_at, SITE_WAVE_MINUTES)

        tree = self.client.station_tree()
        sites = self._target_sites(tree)
        if not sites:
            raise ValueError("ssfb station tree returned no sites")
        site_meta = {site["site_id"]: site for site in sites}

        hour_records: list[dict[str, Any]] = []
        day_records: list[dict[str, Any]] = []
        day_dates = day_fetch_dates(fetched_at) if window["fetch_days"] else []
        for chunk in _chunked(sorted(site_meta), self.request_chunk_size):
            for row in self.client.site_hours(chunk, window["hour_start"], window["hour_end"]):
                record = _site_record(row, site_meta, fetched_at, "hour")
                if record is not None:
                    hour_records.append(record)
            if not day_dates:
                continue
            # 站点日接口只接受单日查询（跨日范围返回 HTTP 500）。
            for day_text in day_dates:
                for row in self.client.site_days(chunk, day_text, day_text):
                    record = _site_record(row, site_meta, fetched_at, "day")
                    if record is not None:
                        day_records.append(record)
        return {
            "hour": hour_records,
            "day": day_records,
            "tree": tree,
            "window": window,
        }

    async def fetch_and_store(self) -> dict[str, Any]:
        fetched_at = self.now_factory().replace(microsecond=0)
        collected = self._collect(fetched_at)
        saved_hour = await self.storage.save(collected["hour"], "hour")
        saved_day = await self.storage.save(collected["day"], "day")
        dim_districts = await self.storage.upsert_dim_district(collected["tree"])
        dim_sites = await self.storage.upsert_dim_site(
            self._target_sites(collected["tree"])
        )
        counties = sorted({
            record["county"] for record in collected["hour"] if record["county"]
        })
        result = {
            "fetched_at": fetched_at.isoformat(),
            "hour_start": collected["window"]["hour_start"],
            "days_fetched": collected["window"]["fetch_days"],
            "hour_rows": len(collected["hour"]),
            "saved_hour_rows": saved_hour,
            "day_rows": len(collected["day"]),
            "saved_day_rows": saved_day,
            "dim_districts": dim_districts,
            "dim_sites": dim_sites,
            "counties": counties,
        }
        logger.info("xuchang_henan_ssfb_site_publish_completed", **result)
        return result

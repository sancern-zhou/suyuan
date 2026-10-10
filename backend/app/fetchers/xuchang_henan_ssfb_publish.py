"""Fetch Henan real-time publish data (18 cities incl. Jiyuan + Xuchang sites).

数据来源为河南省空气质量实时发布系统（详见
``app.integrations.henan_ssfb_client``）。该平台小时/日值仅保留约
最近 8 天，因此采集按小时滚动并回看昨日全天，断档可在下一次运行
自动补齐。结果写入本地 MySQL 采集库 ``DataCrawler``（与
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
from itertools import islice
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
SITE_TREE_ROOT = "县级"
SITE_TARGET_CITIES = {"许昌市"}
SITE_EXCLUDED_TYPES = {"GK"}

SITE_REQUEST_CHUNK_SIZE = 80
MYSQL_EXECUTEMANY_CHUNK = 200

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
            schedule="25 * * * *",
            version="1.0.0",
        )
        self.client = client or HenanSsfbClient()
        self.storage = storage or HenanSsfbMySqlStorage()
        self.now_factory = now_factory

    def _collect(self, fetched_at: datetime) -> dict[str, Any]:
        today = fetched_at.date()
        day_start = today - timedelta(days=1)
        hour_start = f"{day_start:%Y-%m-%d} 00:00:00"
        hour_end = f"{today:%Y-%m-%d} 23:00:00"
        day_start_text = f"{day_start - timedelta(days=1):%Y-%m-%d}"
        day_end_text = f"{day_start:%Y-%m-%d}"

        group_names = city_groups_from_tree(self.client.city_tree())
        if not group_names:
            raise ValueError("ssfb city tree returned no groups")
        city_ids = sorted(group_names)

        hours = self.client.group_hours(city_ids, hour_start, hour_end)
        days = self.client.group_days(city_ids, day_start_text, day_end_text)
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
            description="抓取河南实时发布系统许昌市县级站(剔除国控)小时/日值入库DataCrawler",
            schedule="45 * * * *",
            version="1.0.0",
        )
        self.client = client or HenanSsfbClient()
        self.storage = storage or HenanSsfbMySqlStorage()
        self.now_factory = now_factory
        self.request_chunk_size = request_chunk_size

    def _target_sites(self, tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sites = site_leaves_from_tree(
            tree,
            root_names={SITE_TREE_ROOT},
            city_names=SITE_TARGET_CITIES,
        )
        return [site for site in sites if site.get("online_type") not in SITE_EXCLUDED_TYPES]

    def _collect(self, fetched_at: datetime) -> dict[str, Any]:
        today = fetched_at.date()
        day_start = today - timedelta(days=1)
        hour_start = f"{day_start:%Y-%m-%d} 00:00:00"
        hour_end = f"{today:%Y-%m-%d} 23:00:00"

        tree = self.client.station_tree()
        sites = self._target_sites(tree)
        if not sites:
            raise ValueError("ssfb station tree returned no Xuchang county sites")
        site_meta = {site["site_id"]: site for site in sites}

        hour_records: list[dict[str, Any]] = []
        day_records: list[dict[str, Any]] = []
        day_dates = [
            (day_start - timedelta(days=1)).isoformat(),
            day_start.isoformat(),
        ]
        for chunk in _chunked(sorted(site_meta), self.request_chunk_size):
            for row in self.client.site_hours(chunk, hour_start, hour_end):
                record = _site_record(row, site_meta, fetched_at, "hour")
                if record is not None:
                    hour_records.append(record)
            # 站点日接口只接受单日查询（跨日范围返回 HTTP 500）。
            for day_text in day_dates:
                for row in self.client.site_days(chunk, day_text, day_text):
                    record = _site_record(row, site_meta, fetched_at, "day")
                    if record is not None:
                        day_records.append(record)
        return {"hour": hour_records, "day": day_records, "tree": tree}

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

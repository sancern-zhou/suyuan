"""抓取空气质量信息联网系统（许昌市空气质量管控平台）办事处站 5 分钟与省控站小时数据。

2026-11-23 实测定版的平台协议（漏带 tsno 曾致两次"平台不提供"误判）：
- airData/page **必须携带 tsno=<站码>**，不带 tsno 时 tstype 参数被平台
  忽略、恒返回乡镇站全集行，省控/办事处须逐站查询；
- 因子集字典 air_data_type：type=1 乡镇全因子、type=4 省控全因子（六参数，
  仅小时粒度）、type=5 办事处 PM2.5/PM10 专属（其余因子平台恒返回 null）；
- 站点类型 tstype：3=省控站（8 站）、4=乡镇站（76 站）、9=办事处站（31 站）。

落库：
- OfficeStationFiveMinute：办事处站 5 分钟与官方小时（PM25/PM10 两因子，
  IsHour=0/1 严格区分），滚动保留 30 天（过期行每轮删除），
  uk: Tsno+CollectionTime+IsHour+IsAudit 幂等；
- ShengkongStationHour：省控站逐小时（六参数），同保留策略。

调度与既有 Crawler MySQL 抓取器错峰（严禁同分钟并发连 Crawler MySQL，
曾触发 Packet sequence number wrong）：乡镇 5 分钟 7,37、乡镇小时 11、
省控 13、办事处 9,39；ssfb 三波 14/16/18/20/22/24/55/57/59 不冲突。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import aiomysql
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.xuchang.town_cloud_client import TownCloudClient
from app.tools.xuchang.station_catalog.catalog import normalize_oldcloud_extra_stations
from config.settings import settings

logger = structlog.get_logger()

MYSQL_EXECUTEMANY_CHUNK = 200


def _number(value: Any) -> float | None:
    if value in (None, "", "-", "NA"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


class _StationMySqlStorage:
    """通用建表 / upsert / 过期清理（按子类 DDL/SQL 驱动）。"""

    table: str = ""
    ddl: str = ""
    upsert_sql: str = ""
    record_fields: tuple[str, ...] = ()

    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.crawler_mysql_url

    def _connection_kwargs(self) -> dict[str, Any]:
        # 与 HenanSsfbMySqlStorage 相同：解析 SQLAlchemy aiomysql URL。
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

    async def _prepare_schema(self, cursor: Any) -> None:
        await cursor.execute(self.ddl)

    async def save(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        rows = [tuple(record[field] for field in self.record_fields) for record in records]
        connection = await aiomysql.connect(**self._connection_kwargs())
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(self.ddl)
                for start in range(0, len(rows), MYSQL_EXECUTEMANY_CHUNK):
                    await cursor.executemany(
                        self.upsert_sql, rows[start:start + MYSQL_EXECUTEMANY_CHUNK]
                    )
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise
        finally:
            connection.close()
        return len(rows)

    async def purge_expired(self, retention_days: int) -> int:
        """删除超过保留期的行（滚动窗口，过期丢弃）。"""
        cutoff = datetime.now() - timedelta(days=retention_days)
        connection = await aiomysql.connect(**self._connection_kwargs())
        try:
            async with connection.cursor() as cursor:
                await self._prepare_schema(cursor)
                affected = await cursor.execute(
                    f"DELETE FROM {self.table} WHERE CollectionTime < %s", (cutoff,)
                )
            await connection.commit()
            return affected
        except Exception:
            await connection.rollback()
            raise
        finally:
            connection.close()


_OFFICE_TABLE = "OfficeStationFiveMinute"
_OFFICE_DDL = f"""
CREATE TABLE IF NOT EXISTS {_OFFICE_TABLE} (
    Id BIGINT AUTO_INCREMENT PRIMARY KEY,
    Tsno VARCHAR(32) NOT NULL,
    StationName VARCHAR(128) NULL,
    CountyName VARCHAR(64) NULL,
    CollectionTime DATETIME NOT NULL,
    IsAudit TINYINT NOT NULL DEFAULT 0,
    IsHour TINYINT NOT NULL DEFAULT 0,
    PM25 DOUBLE NULL,
    PM10 DOUBLE NULL,
    FetchTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY UK_OfficeStationFiveMinute (Tsno, CollectionTime, IsHour, IsAudit)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""
_OFFICE_UPSERT = f"""
INSERT INTO {_OFFICE_TABLE} (
    Tsno, StationName, CountyName, CollectionTime, IsAudit, IsHour, PM25, PM10
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    StationName=VALUES(StationName),
    CountyName=VALUES(CountyName),
    PM25=VALUES(PM25), PM10=VALUES(PM10),
    FetchTime=CURRENT_TIMESTAMP
"""
_OFFICE_FIELDS = (
    "tsno", "station_name", "county_name", "collection_time", "is_audit", "is_hour",
    "pm25", "pm10",
)

_SHENGKONG_TABLE = "ShengkongStationHour"
_SHENGKONG_DDL = f"""
CREATE TABLE IF NOT EXISTS {_SHENGKONG_TABLE} (
    Id BIGINT AUTO_INCREMENT PRIMARY KEY,
    Tsno VARCHAR(32) NOT NULL,
    StationName VARCHAR(128) NULL,
    CountyName VARCHAR(64) NULL,
    CollectionTime DATETIME NOT NULL,
    IsAudit TINYINT NOT NULL DEFAULT 0,
    SO2 DOUBLE NULL,
    NO2 DOUBLE NULL,
    NO DOUBLE NULL,
    NOX DOUBLE NULL,
    CO DOUBLE NULL,
    O3 DOUBLE NULL,
    PM10 DOUBLE NULL,
    PM25 DOUBLE NULL,
    FetchTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY UK_ShengkongStationHour (Tsno, CollectionTime, IsAudit)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""
_SHENGKONG_UPSERT = f"""
INSERT INTO {_SHENGKONG_TABLE} (
    Tsno, StationName, CountyName, CollectionTime, IsAudit,
    SO2, NO2, NO, NOX, CO, O3, PM10, PM25
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    StationName=VALUES(StationName),
    CountyName=VALUES(CountyName),
    SO2=VALUES(SO2), NO2=VALUES(NO2), NO=VALUES(NO), NOX=VALUES(NOX),
    CO=VALUES(CO), O3=VALUES(O3), PM10=VALUES(PM10), PM25=VALUES(PM25),
    FetchTime=CURRENT_TIMESTAMP
"""
_SHENGKONG_FIELDS = (
    "tsno", "station_name", "county_name", "collection_time", "is_audit",
    "so2", "no2", "no_val", "nox", "co", "o3", "pm10", "pm25",
)


def office_record_from_row(
    row: dict[str, Any], tsno: str, county: str | None, is_hour: bool = False
) -> dict[str, Any] | None:
    """平台 airData 行（type=5 办事处因子集）→ 落库记录；缺时间戳丢弃。

    办事处因子集仅 PM2.5/PM10 有值，其余因子平台恒返回 null，不落库。
    """
    collection_time = _parse_time(row.get("collectionTime"))
    if collection_time is None:
        return None
    return {
        "tsno": tsno,
        "station_name": str(row.get("name") or "").strip() or None,
        "county_name": county,
        "collection_time": collection_time,
        "is_audit": 0,
        "is_hour": int(is_hour),
        "pm25": _number(row.get("pm25")),
        "pm10": _number(row.get("pm10")),
    }


def shengkong_record_from_row(
    row: dict[str, Any], tsno: str, county: str | None, is_hour: bool = True
) -> dict[str, Any] | None:
    """平台 airData 行（type=4 省控因子集）→ 落库记录；缺时间戳丢弃。"""
    collection_time = _parse_time(row.get("collectionTime"))
    if collection_time is None:
        return None
    return {
        "tsno": tsno,
        "station_name": str(row.get("name") or "").strip() or None,
        "county_name": county,
        "collection_time": collection_time,
        "is_audit": 0,
        "so2": _number(row.get("so2")),
        "no2": _number(row.get("no2")),
        "no_val": _number(row.get("no")),
        "nox": _number(row.get("nox")),
        "co": _number(row.get("co")),
        "o3": _number(row.get("o3")),
        "pm10": _number(row.get("pm10")),
        "pm25": _number(row.get("pm25")),
    }


class _PerStationOldCloudFetcher(DataFetcher):
    """逐站抓取骨架：目录（tstype）→ 逐站 airData（tsno+factor_type）。"""

    #: 平台站点类型（3=省控站 / 9=办事处站）
    platform_tstype: str = "4"
    #: air_data_type 因子集（1=乡镇全因子 / 4=省控全因子 / 5=办事处双因子）
    factor_type: str = "1"
    #: timeStep（1=5分钟 / 2=小时）
    time_step: int = 1
    #: 行 → 落库记录的转换函数（子类提供 tsno/county 绑定）
    record_builder: Any = None
    #: 办事处 5 分钟与小时共用一张表，以 IsHour 区分粒度。
    is_hour = False

    def __init__(
        self,
        client: TownCloudClient | None = None,
        storage: _StationMySqlStorage | None = None,
        now_factory=lambda: datetime.now(),
    ) -> None:
        super().__init__(
            name="unset",
            description="unset",
            schedule="0 * * * *",
            version="1.0.0",
        )
        self.client = client or TownCloudClient()
        self.storage = storage
        self.now_factory = now_factory

    # 子类覆盖
    def _window(self, now: datetime) -> tuple[datetime, datetime]:
        raise NotImplementedError

    async def fetch_and_store(self) -> dict[str, Any]:
        start, end = self._window(self.now_factory().replace(second=0, microsecond=0))
        stations = await asyncio.to_thread(self.client.fetch_station_directory, self.platform_tstype)
        # 平台办事处目录 countyIdStr 可能为空；与站点目录共用同一份已核实归属表，
        # 不在各抓取器另建区县映射。
        catalog_stations = normalize_oldcloud_extra_stations(
            stations, "office" if self.platform_tstype == "9" else "shengkong"
        )
        county_by_code = {
            str(item["station_code"]): str(item.get("district") or "").strip() or None
            for item in catalog_stations
        }
        records: list[dict[str, Any]] = []
        station_errors: dict[str, str] = {}
        empty_stations: list[str] = []
        for station in stations:
            tsno = str(station.get("tsno") or "").strip()
            name = str(station.get("name") or "").strip()
            county = str(station.get("countyIdStr") or "").strip() or county_by_code.get(tsno)
            if not tsno:
                continue
            try:
                rows = await asyncio.to_thread(
                    self.client.fetch_air_data,
                    start,
                    end,
                    time_step=self.time_step,
                    is_audit=0,
                    tstype=self.platform_tstype,
                    factor_type=self.factor_type,
                    tsno=tsno,
                )
            except Exception as exc:  # noqa: BLE001 - 单站失败不拖垮整轮
                station_errors[name or tsno] = str(exc)
                continue
            if not rows:
                empty_stations.append(name or tsno)
                continue
            built = 0
            for row in rows:
                record = self.record_builder(row, tsno, county, is_hour=self.is_hour)
                if record is not None:
                    records.append(record)
                    built += 1
            if not built:
                empty_stations.append(name or tsno)
        saved = purged = 0
        if self.storage is not None:
            saved = await self.storage.save(records)
            purged = await self.storage.purge_expired(settings.oldcloud_extra_retention_days)
        result = {
            "window": f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}",
            "stations": len(stations),
            "station_errors": station_errors,
            "empty_stations": empty_stations,
            "records": len(records),
            "saved": saved,
            "purged": purged,
        }
        logger.info(f"{self.name}_completed", **result)
        return result


class XuchangOfficeFiveMinuteFetcher(_PerStationOldCloudFetcher):
    """办事处站（tstype=9，31 站）逐 5 分钟 PM2.5/PM10 → OfficeStationFiveMinute。"""

    platform_tstype = "9"
    factor_type = "5"
    time_step = 1
    record_builder = staticmethod(office_record_from_row)

    def __init__(
        self,
        client: TownCloudClient | None = None,
        storage: _StationMySqlStorage | None = None,
        now_factory=lambda: datetime.now(),
    ) -> None:
        self.storage = storage or OfficeStationMySqlStorage()
        super().__init__(client=client, storage=self.storage, now_factory=now_factory)
        self.name = "xuchang_office_five_minute_fetcher"
        self.description = (
            "抓取空气质量信息联网系统(许昌市空气质量管控平台)办事处站5分钟PM2.5/PM10入库DataCrawler"
            "(tstype=9&type=5逐站查询,仅保留30天)"
        )
        self.schedule = "4,9,15,25,35,45 * * * *"

    def _window(self, now: datetime) -> tuple[datetime, datetime]:
        lookback = min(settings.office_five_minute_lookback_minutes, 4320)
        return now - timedelta(minutes=lookback), now


class OfficeStationMySqlStorage(_StationMySqlStorage):
    table = _OFFICE_TABLE
    ddl = _OFFICE_DDL
    upsert_sql = _OFFICE_UPSERT
    record_fields = _OFFICE_FIELDS

    async def _prepare_schema(self, cursor: Any) -> None:
        # 既有 5 分钟表原位升级；唯一键含粒度，整点 5 分钟与官方小时可共存。
        await super()._prepare_schema(cursor)
        await cursor.execute(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME='IsHour'",
            (self.table,),
        )
        if (await cursor.fetchone())[0]:
            return
        await cursor.execute(f"ALTER TABLE {self.table} ADD COLUMN IsHour TINYINT NOT NULL DEFAULT 0 AFTER IsAudit")
        await cursor.execute(f"ALTER TABLE {self.table} DROP INDEX UK_OfficeStationFiveMinute")
        await cursor.execute(
            f"ALTER TABLE {self.table} ADD UNIQUE KEY UK_OfficeStationFiveMinute "
            "(Tsno, CollectionTime, IsHour, IsAudit)"
        )


class XuchangOfficeHourFetcher(XuchangOfficeFiveMinuteFetcher):
    """办事处站官方小时 PM2.5/PM10，与乡镇小时高值检测共用数据窗口。"""

    time_step = 2
    is_hour = True

    def __init__(
        self,
        client: TownCloudClient | None = None,
        storage: OfficeStationMySqlStorage | None = None,
        now_factory=lambda: datetime.now(),
    ) -> None:
        super().__init__(client=client, storage=storage, now_factory=now_factory)
        self.name = "xuchang_office_hour_fetcher"
        self.description = (
            "抓取空气质量信息联网系统(许昌市空气质量管控平台)办事处站小时PM2.5/PM10"
            "入OfficeStationFiveMinute(IsHour=1，仅保留30天)"
        )
        # 平台小时值整点后约 30 秒~1 分钟发布（2026-11-25 逐分钟实测）；
        # 办事处小时 :3、乡镇小时 :5、省控 :17（省控 ~:15 发布）、大屏 :16、
        # 高值提醒 :19/:44，均错峰。
        self.schedule = "3 * * * *"

    def _window(self, now: datetime) -> tuple[datetime, datetime]:
        lookback = min(settings.town_hour_lookback_hours, 720)
        return now - timedelta(hours=lookback), now


class ShengkongStationMySqlStorage(_StationMySqlStorage):
    table = _SHENGKONG_TABLE
    ddl = _SHENGKONG_DDL
    upsert_sql = _SHENGKONG_UPSERT
    record_fields = _SHENGKONG_FIELDS


class XuchangShengkongStationFetcher(_PerStationOldCloudFetcher):
    """省控站（tstype=3，8 站）逐小时六参数 → ShengkongStationHour。

    平台省控仅小时粒度（5 分钟各因子集实测均 0 行），为本表最优粒度。
    """

    platform_tstype = "3"
    factor_type = "4"
    time_step = 2
    record_builder = staticmethod(shengkong_record_from_row)

    def __init__(
        self,
        client: TownCloudClient | None = None,
        storage: ShengkongStationMySqlStorage | None = None,
        now_factory=lambda: datetime.now(),
    ) -> None:
        self.storage = storage or ShengkongStationMySqlStorage()
        super().__init__(client=client, storage=self.storage, now_factory=now_factory)
        self.name = "xuchang_shengkong_station_fetcher"
        self.description = (
            "抓取空气质量信息联网系统(许昌市空气质量管控平台)省控站小时六参数入库DataCrawler"
            "(tstype=3&type=4逐站查询,仅保留30天)"
        )
        # 省控小时值整点后约 15 分钟发布（2026-11-25 实测 20/21 两边界一致），
        # :13 会在最新小时发布前跑、永远慢一拍，改 :17 后高值告警 :19 判定
        # 才能含省控站。
        self.schedule = "17 * * * *"

    def _window(self, now: datetime) -> tuple[datetime, datetime]:
        lookback = min(settings.shengkong_hour_lookback_hours, 720)
        return now - timedelta(hours=lookback), now

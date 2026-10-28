"""抓取空气质量信息联网系统（旧云平台）许昌乡镇站 5 分钟数据。

Crawler MySQL 的 TownStationData（乡镇站小时/日值）自 2026-10-21 起由
政府侧停更，本抓取器从旧云平台替代源拉取 5 分钟粒度数据，落库到
DataCrawler.TownStationFiveMinute，并只保留最近 30 天（过期行每轮删除）。

- 数据窗口每轮回看 3 小时（平台 5 分钟数据限查 3 天以内，回看窗口
  保证迟到数据可在后续轮次补齐；upsert 幂等）；
- airData 行不带 tsno，每轮先拉 airNetwork 站点目录，按站名关联站码
  后落库（许昌 76 站站名实测唯一，均带区县前缀）；
- 调度 7,37 * * * *：与 ssfb 三波（14/20/55、16/22/57、18/24/59）、
  县级补充（:27-:28 修正）、transport_analysis（26,31,40,50）错峰，
  避免并发连接 Crawler MySQL 触发 Packet sequence number wrong；
- isAudit=0 原始口径（该平台 5 分钟数据无审核流）。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import aiomysql
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.town_cloud_client import TownCloudClient
from config.settings import settings

logger = structlog.get_logger()

TABLE = "TownStationFiveMinute"

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    Id BIGINT AUTO_INCREMENT PRIMARY KEY,
    Tsno VARCHAR(32) NOT NULL,
    StationName VARCHAR(128) NULL,
    CountyCode VARCHAR(16) NULL,
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
    AQI DOUBLE NULL,
    ChiefPollutant VARCHAR(32) NULL,
    PollutionLevel VARCHAR(8) NULL,
    FetchTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY UK_TownStationFiveMinute (Tsno, CollectionTime, IsAudit)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

UPSERT_SQL = f"""
INSERT INTO {TABLE} (
    Tsno, StationName, CountyCode, CountyName, CollectionTime, IsAudit,
    SO2, NO2, NO, NOX, CO, O3, PM10, PM25, AQI, ChiefPollutant, PollutionLevel
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    StationName=VALUES(StationName),
    CountyCode=VALUES(CountyCode),
    CountyName=VALUES(CountyName),
    SO2=VALUES(SO2), NO2=VALUES(NO2), NO=VALUES(NO), NOX=VALUES(NOX),
    CO=VALUES(CO), O3=VALUES(O3), PM10=VALUES(PM10), PM25=VALUES(PM25),
    AQI=VALUES(AQI), ChiefPollutant=VALUES(ChiefPollutant),
    PollutionLevel=VALUES(PollutionLevel),
    FetchTime=CURRENT_TIMESTAMP
"""

# 行字段顺序与 UPSERT_SQL 占位符一一对应
RECORD_FIELDS = (
    "tsno", "station_name", "county_code", "county_name", "collection_time",
    "is_audit", "so2", "no2", "no_val", "nox", "co", "o3", "pm10", "pm25",
    "aqi", "chief_pollutant", "pollution_level",
)

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


def build_station_key(name: Any) -> str:
    """airData 行关联站点目录的键（站名，许昌 76 站实测唯一，均带区县前缀）。"""
    return str(name or "").strip()


def record_from_row(
    row: dict[str, Any], station_tsno: dict[str, str]
) -> dict[str, Any] | None:
    """平台 airData/page 行 → 落库记录；缺站码/时间戳/目录未命中的行丢弃。

    airData 行不带 tsno，站码由站点目录按站名关联得到。
    """
    collection_time = _parse_time(row.get("collectionTime"))
    key = build_station_key(row.get("name"))
    tsno = station_tsno.get(key, "")
    if not tsno or collection_time is None:
        return None
    return {
        "tsno": tsno,
        "station_name": str(row.get("name") or "").strip() or None,
        "county_code": str(row.get("countyId") or "").strip() or None,
        "county_name": str(row.get("countyIdStr") or "").strip() or None,
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
        "aqi": _number(row.get("aqi")),
        "chief_pollutant": str(row.get("chiefPollutant") or "").strip() or None,
        "pollution_level": str(row.get("pollutionLevel") or "").strip() or None,
    }


class TownFiveMinuteMySqlStorage:
    """TownStationFiveMinute 表的建表 / upsert / 过期清理。"""

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

    async def save(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        rows = [tuple(record[field] for field in RECORD_FIELDS) for record in records]
        connection = await aiomysql.connect(**self._connection_kwargs())
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(DDL)
                for start in range(0, len(rows), MYSQL_EXECUTEMANY_CHUNK):
                    await cursor.executemany(
                        UPSERT_SQL, rows[start:start + MYSQL_EXECUTEMANY_CHUNK]
                    )
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise
        finally:
            connection.close()
        return len(rows)

    async def purge_expired(self, retention_days: int) -> int:
        """删除超过保留期的行（只存储一个月，过期丢弃）。"""
        cutoff = datetime.now() - timedelta(days=retention_days)
        connection = await aiomysql.connect(**self._connection_kwargs())
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(DDL)
                affected = await cursor.execute(
                    f"DELETE FROM {TABLE} WHERE CollectionTime < %s", (cutoff,)
                )
            await connection.commit()
            return affected
        except Exception:
            await connection.rollback()
            raise
        finally:
            connection.close()


class XuchangTownFiveMinuteFetcher(DataFetcher):
    """乡镇站 5 分钟数据抓取（旧云平台替代源，保留 30 天）。"""

    def __init__(
        self,
        client: TownCloudClient | None = None,
        storage: TownFiveMinuteMySqlStorage | None = None,
        now_factory=lambda: datetime.now(),
    ) -> None:
        super().__init__(
            name="xuchang_town_five_minute_fetcher",
            description="抓取空气质量信息联网系统(旧云平台)许昌乡镇站5分钟数据入库DataCrawler(仅保留30天)",
            schedule="7,37 * * * *",
            version="1.0.0",
        )
        self.client = client or TownCloudClient()
        self.storage = storage or TownFiveMinuteMySqlStorage()
        self.now_factory = now_factory

    def _window(self, now: datetime | None = None) -> tuple[datetime, datetime]:
        now = (now or self.now_factory()).replace(second=0, microsecond=0)
        lookback = settings.town_five_minute_lookback_minutes
        # 平台限制 5 分钟数据单次查询窗口 ≤ 3 天
        lookback = min(lookback, 4320)
        return now - timedelta(minutes=lookback), now

    def station_tsno_map(self) -> dict[str, str]:
        """站点目录 → {站名: tsno} 关联表。"""
        mapping: dict[str, str] = {}
        for station in self.client.fetch_station_directory():
            tsno = str(station.get("tsno") or "").strip()
            key = build_station_key(station.get("name"))
            if tsno and key and key not in mapping:
                mapping[key] = tsno
        return mapping

    async def fetch_and_store(self) -> dict[str, Any]:
        start, end = self._window()
        raw = self.client.fetch_air_data(start, end, time_step=1)
        station_tsno = self.station_tsno_map()
        records: list[dict[str, Any]] = []
        unmatched = 0
        for row in raw:
            record = record_from_row(row, station_tsno)
            if record is None:
                unmatched += 1
                continue
            records.append(record)
        saved = await self.storage.save(records)
        purged = await self.storage.purge_expired(
            settings.town_five_minute_retention_days
        )
        result = {
            "window": f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}",
            "fetched": len(raw),
            "matched": len(records),
            "unmatched": unmatched,
            "saved": saved,
            "purged": purged,
        }
        logger.info("town_five_minute_fetch_completed", **result)
        return result

"""抓取空气质量信息联网系统（旧云平台）许昌乡镇站小时/日数据，回写原表。

TownStationData（乡镇站小时/日值）2026-10-20 21:00 起原始流、10-19 起审核流
由政府侧停更，本抓取器从旧云平台 airData/page（timeStep=2 小时 / 3 日）拉取
数据，回写 DataCrawler.TownStationData 原表（uk 幂等 upsert），恢复下游
view_dat_town_hour/day_app|src 四个视图与 TownHour/TownDay cube。

- 口径：平台 isAudit=0/1 对小时/日数据返回同一套行（同 id 同值，2026-10-29
  实测），即平台发布值本身；每行同值双写 IsAudit=0 与 IsAudit=1，与停更前
  "审核行由旧云平台链路产出"的语义一致，下游官方口径（app 视图）与原始
  口径（src 视图）同时恢复；
- AQI/污染等级/首要污染物用平台值（pollutionLevelStr，如"良"）；
  IAQI 平台不提供，按 TownStationData 历史行实测口径补算——旧 HJ633 浓度
  限值表（PM10/PM2.5 24h 表收严前的 150/75 折点，气态小时用 1h 表、日值用
  24h/8h 表，均经 2026-10-15~17 历史行逐因子核验），四舍五入取整；
- airData 行不带 tsno，每轮先拉 airNetwork 站点目录，按站名关联站码
  （站名均带区县前缀且唯一，关联逻辑与 5 分钟抓取器一致）；
- 调度错峰：小时 11 * * * *（平台小时值整点后 8~13 分钟发布）、日 5 8 * * *，
  与 ssfb 三波（14/20/55、16/22/57、18/24/59，窗口 :13:30-:25:30 与 :54:30
  后）、乡镇 5 分钟（7,37）、transport_analysis（26,31,40,50，单轮 3~4 分钟）
  全部错开，避免并发连接 Crawler MySQL 触发 Packet sequence number wrong；
- 回看窗口仅补迟到/修正数据，2026-10-21 起的断档缺口由
  projects/xuchang/data-ops/backfill_town_hour_day/ 一次性回补。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import aiomysql
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.xuchang_town_five_minute import (
    _number,
    _parse_time,
    build_station_key,
)
from app.integrations.town_cloud_client import TownCloudClient
from config.settings import settings

logger = structlog.get_logger()

TABLE = "TownStationData"

# 旧 HJ633 浓度限值表（μg/m3，co 为 mg/m3），TownStationData 历史 IAQI 实测口径。
# 小时行：气态用 1h 表；日值行：气态用 24h 表、O3 用 8h 表；PM10/PM2.5 两种
# 粒度同为 24h 表（GB 3095—2026 收严前的 150/75 折点，非 aqi.py 的收严表）。
_HOURLY_BREAKPOINTS = {
    "so2": (0, 150, 500, 650, 800, 1600, 2100, 2620),
    "no2": (0, 100, 200, 700, 1200, 2340, 3090, 3840),
    "o3": (0, 160, 200, 300, 400, 800, 1000, 1200),
    "co": (0, 5, 10, 35, 60, 90, 120, 150),
    "pm10": (0, 50, 150, 250, 350, 420, 500, 600),
    "pm25": (0, 35, 75, 115, 150, 250, 350, 500),
}
_DAILY_BREAKPOINTS = {
    "so2": (0, 50, 150, 475, 800, 1600, 2100, 2620),
    "no2": (0, 40, 80, 180, 280, 565, 750, 940),
    "o3": (0, 100, 160, 215, 265, 315, 775, 1005),
    "co": (0, 2, 4, 14, 24, 36, 48, 60),
    "pm10": (0, 50, 150, 250, 350, 420, 500, 600),
    "pm25": (0, 35, 75, 115, 150, 250, 350, 500),
}
_IAQI_LEVELS = (0, 50, 100, 150, 200, 300, 400, 500)

MYSQL_EXECUTEMANY_CHUNK = 200

UPSERT_SQL = f"""
INSERT INTO {TABLE} (
    Tsno, CollectionTime, IsHour, IsAudit,
    Aqi, ChiefPollutant, PollutionLevel,
    SO2, SO2Iaqi, NO2, NO2Iaqi, CO, COIaqi, O3, O3Iaqi, PM10, PM10Iaqi, PM25, PM25Iaqi
) VALUES ({", ".join(["%s"] * 19)})
ON DUPLICATE KEY UPDATE
    Aqi=VALUES(Aqi), ChiefPollutant=VALUES(ChiefPollutant),
    PollutionLevel=VALUES(PollutionLevel),
    SO2=VALUES(SO2), SO2Iaqi=VALUES(SO2Iaqi),
    NO2=VALUES(NO2), NO2Iaqi=VALUES(NO2Iaqi),
    CO=VALUES(CO), COIaqi=VALUES(COIaqi),
    O3=VALUES(O3), O3Iaqi=VALUES(O3Iaqi),
    PM10=VALUES(PM10), PM10Iaqi=VALUES(PM10Iaqi),
    PM25=VALUES(PM25), PM25Iaqi=VALUES(PM25Iaqi)
"""

# 行字段顺序与 UPSERT_SQL 占位符一一对应
RECORD_FIELDS = (
    "tsno", "collection_time", "is_hour", "is_audit",
    "aqi", "chief_pollutant", "pollution_level",
    "so2", "so2_iaqi", "no2", "no2_iaqi", "co", "co_iaqi",
    "o3", "o3_iaqi", "pm10", "pm10_iaqi", "pm25", "pm25_iaqi",
)


def _round_half_up(value: float) -> int:
    return int(value + 0.5)


def iaqi_legacy(
    pollutant: str, concentration: Any, *, daily: bool
) -> int | None:
    """旧 HJ633 折点的单因子 IAQI（四舍五入取整）；无效浓度返回 None。

    与 aqi.py（GB 3095—2026 收严表、实时发布 1h 表）不同：本表按
    TownStationData 历史 IAQI 逐因子核验的旧限值口径。
    """
    value = _number(concentration)
    if value is None:
        return None
    breakpoints = _DAILY_BREAKPOINTS if daily else _HOURLY_BREAKPOINTS
    table = breakpoints[pollutant]
    if value > table[-1]:
        return 500
    for index in range(1, len(_IAQI_LEVELS)):
        bp_low, bp_high = table[index - 1], table[index]
        if value <= bp_high:
            iaqi_low, iaqi_high = _IAQI_LEVELS[index - 1], _IAQI_LEVELS[index]
            score = (iaqi_high - iaqi_low) / (bp_high - bp_low) * (value - bp_low) + iaqi_low
            return _round_half_up(score)
    return None


def record_from_row(
    row: dict[str, Any],
    station_tsno: dict[str, str],
    *,
    is_hour: bool,
    is_audit: int,
) -> dict[str, Any] | None:
    """平台 airData/page 行 → TownStationData 行；缺站码/时间戳的行丢弃。

    airData 行不带 tsno，站码由站点目录按站名关联得到。
    """
    collection_time = _parse_time(row.get("collectionTime"))
    key = build_station_key(row.get("name"))
    tsno = station_tsno.get(key, "")
    if not tsno or collection_time is None:
        return None
    daily = not is_hour
    return {
        "tsno": tsno,
        "collection_time": collection_time,
        "is_hour": 1 if is_hour else 0,
        "is_audit": is_audit,
        "aqi": _number(row.get("aqi")),
        "chief_pollutant": str(row.get("chiefPollutant") or "").strip() or None,
        "pollution_level": str(row.get("pollutionLevelStr") or "").strip() or None,
        "so2": _number(row.get("so2")),
        "so2_iaqi": iaqi_legacy("so2", row.get("so2"), daily=daily),
        "no2": _number(row.get("no2")),
        "no2_iaqi": iaqi_legacy("no2", row.get("no2"), daily=daily),
        "co": _number(row.get("co")),
        "co_iaqi": iaqi_legacy("co", row.get("co"), daily=daily),
        "o3": _number(row.get("o3")),
        "o3_iaqi": iaqi_legacy("o3", row.get("o3"), daily=daily),
        "pm10": _number(row.get("pm10")),
        "pm10_iaqi": iaqi_legacy("pm10", row.get("pm10"), daily=daily),
        "pm25": _number(row.get("pm25")),
        "pm25_iaqi": iaqi_legacy("pm25", row.get("pm25"), daily=daily),
    }


def records_from_rows(
    rows: list[dict[str, Any]],
    station_tsno: dict[str, str],
    *,
    is_hour: bool,
) -> tuple[list[dict[str, Any]], int]:
    """平台行 → 落库记录（原始+审核同值双写）；返回 (记录列表, 未命中行数)。"""
    records: list[dict[str, Any]] = []
    unmatched = 0
    for row in rows:
        record = record_from_row(row, station_tsno, is_hour=is_hour, is_audit=0)
        if record is None:
            unmatched += 1
            continue
        audit_record = dict(record)
        audit_record["is_audit"] = 1
        records.append(record)
        records.append(audit_record)
    return records, unmatched


class TownStationDataMySqlStorage:
    """TownStationData 原表的幂等 upsert（不建表、不清数据）。"""

    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.crawler_mysql_url

    def _connection_kwargs(self) -> dict[str, Any]:
        # 与 TownFiveMinuteMySqlStorage 相同：解析 SQLAlchemy aiomysql URL。
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


class XuchangTownAirDataFetcher(DataFetcher):
    """乡镇站小时/日数据抓取（旧云平台替代源，回写 TownStationData 原表）。

    data_kind="hour"：airData timeStep=2，调度 11 * * * *；
    data_kind="day"：airData timeStep=3，调度 5 8 * * *。
    """

    def __init__(
        self,
        data_kind: str = "hour",
        client: TownCloudClient | None = None,
        storage: TownStationDataMySqlStorage | None = None,
        now_factory=lambda: datetime.now(),
    ) -> None:
        if data_kind not in ("hour", "day"):
            raise ValueError(f"未知 data_kind: {data_kind}")
        self.data_kind = data_kind
        is_hour = data_kind == "hour"
        super().__init__(
            name=f"xuchang_town_{data_kind}_fetcher",
            description=(
                "抓取空气质量信息联网系统(旧云平台)许昌乡镇站小时数据回写TownStationData原表(原始+审核同值双写)"
                if is_hour else
                "抓取空气质量信息联网系统(旧云平台)许昌乡镇站日数据回写TownStationData原表(原始+审核同值双写)"
            ),
            schedule="11 * * * *" if is_hour else "5 8 * * *",
            version="1.0.0",
        )
        self.client = client or TownCloudClient()
        self.storage = storage or TownStationDataMySqlStorage()
        self.now_factory = now_factory

    def _window(self, now: datetime | None = None) -> tuple[datetime, datetime]:
        now = (now or self.now_factory()).replace(second=0, microsecond=0)
        if self.data_kind == "hour":
            return now - timedelta(hours=settings.town_hour_lookback_hours), now
        return now - timedelta(days=settings.town_day_lookback_days), now

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
        time_step = 2 if self.data_kind == "hour" else 3
        raw = self.client.fetch_air_data(start, end, time_step=time_step)
        station_tsno = self.station_tsno_map()
        records, unmatched = records_from_rows(
            raw, station_tsno, is_hour=self.data_kind == "hour"
        )
        saved = await self.storage.save(records)
        result = {
            "kind": self.data_kind,
            "window": f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}",
            "fetched": len(raw),
            "matched": len(raw) - unmatched,
            "unmatched": unmatched,
            "saved": saved,
        }
        logger.info("town_air_data_fetch_completed", **result)
        return result

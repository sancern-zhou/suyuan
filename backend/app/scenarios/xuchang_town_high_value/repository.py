"""乡镇/办事处/省控小时读取，并从站点目录补齐权威辖区与站点类型。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import aiomysql
from sqlalchemy.engine import make_url

from config.settings import settings

QUERY = """
SELECT t.Tsno, v.name AS StationName, t.CollectionTime, t.PM25, t.PM10
FROM TownStationData t
LEFT JOIN view_dat_town_hour_app v
  ON v.code=t.Tsno AND v.timepoint=t.CollectionTime
WHERE t.IsHour=1 AND t.IsAudit=1 AND t.CollectionTime >= %s AND t.CollectionTime < %s
ORDER BY t.CollectionTime DESC, t.Tsno
"""


class TownHourRepository:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or settings.crawler_mysql_url

    @staticmethod
    def _catalog_metadata() -> dict[str, dict[str, str]]:
        """以站点目录为主补齐辖区；不从站名临时切割推断。"""
        from app.tools.xuchang.station_catalog.catalog import (
            load_catalog,
            load_office_coordinates,
            load_shengkong_coordinates,
        )
        from app.tools.xuchang.station_catalog.coordinates import normalize_station_name

        metadata: dict[str, dict[str, str]] = {}
        for item in load_catalog().get("townships") or []:
            info = {
                "station_name": item["station_name"], "county_name": item["district"],
                "station_type": item["station_type"],
            }
            metadata[normalize_station_name(item["station_name"])] = info
            if item.get("platform_station_code"):
                metadata[str(item["platform_station_code"])] = info
        for loader, station_type in (
            (load_office_coordinates, "office"),
            (load_shengkong_coordinates, "shengkong"),
        ):
            for name, record in loader().items():
                metadata[normalize_station_name(name)] = {
                    "county_name": str(record.get("district") or "").strip(),
                    "station_type": station_type,
                }
        return metadata

    @staticmethod
    async def _shengkong_hour_rows(
        cursor: Any, now: datetime, lookback_hours: int
    ) -> list[dict[str, Any]]:
        await cursor.execute(
            "SELECT Tsno, StationName, CollectionTime, PM25, PM10 "
            "FROM ShengkongStationHour "
            "WHERE CollectionTime >= %s AND CollectionTime < %s "
            "ORDER BY CollectionTime DESC, Tsno",
            (now - timedelta(hours=lookback_hours), now),
        )
        return list(await cursor.fetchall())

    async def _office_hour_rows(
        self, cursor: Any, now: datetime, lookback_hours: int
    ) -> list[dict[str, Any]]:
        await cursor.execute(
            "SELECT Tsno, StationName, CollectionTime, PM25, PM10 "
            "FROM OfficeStationFiveMinute "
            "WHERE IsHour=1 AND IsAudit=0 AND CollectionTime >= %s AND CollectionTime < %s "
            "ORDER BY CollectionTime DESC, Tsno",
            (now - timedelta(hours=lookback_hours), now),
        )
        return list(await cursor.fetchall())

    async def station_series(
        self, *, station_name: str, metric: str, now: datetime, station_type: str
    ) -> list[dict[str, Any]]:
        column = {"pm25": "PM25", "pm10": "PM10"}.get(metric)
        if not column:
            return []
        parsed = make_url(self.url)
        connection = await aiomysql.connect(
            host=parsed.host or "127.0.0.1", port=parsed.port or 3306,
            user=parsed.username or "", password=parsed.password or "",
            db=parsed.database or "DataCrawler", autocommit=True,
        )
        table = "OfficeStationFiveMinute" if station_type == "office" else "ShengkongStationHour"
        extra = " AND IsHour=1 AND IsAudit=0" if station_type == "office" else ""
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"SELECT CollectionTime, {column} FROM {table} "
                    f"WHERE StationName=%s{extra}"
                    " AND CollectionTime >= %s ORDER BY CollectionTime",
                    (station_name, now - timedelta(hours=6)),
                )
                return [
                    {"time": timestamp.isoformat(), "value": value}
                    for timestamp, value in await cursor.fetchall() if value is not None
                ]
        finally:
            connection.close()

    async def _office_hour_rows_for_map(self, now: datetime) -> list[dict[str, Any]]:
        """只返回两类站点最近共同最新小时的办事处行，避免地图混入不同时刻。"""
        parsed = make_url(self.url)
        connection = await aiomysql.connect(
            host=parsed.host or "127.0.0.1", port=parsed.port or 3306,
            user=parsed.username or "", password=parsed.password or "",
            db=parsed.database or "DataCrawler", autocommit=True,
        )
        try:
            async with connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(
                    "SELECT MAX(CollectionTime) FROM TownStationData "
                    "WHERE IsHour=1 AND IsAudit=1 AND CollectionTime < %s", (now,)
                )
                town_hour = (await cursor.fetchone()).get("MAX(CollectionTime)")
                if town_hour is None:
                    return []
                await cursor.execute(
                    "SELECT Tsno, StationName, CollectionTime, PM25, PM10 "
                    "FROM OfficeStationFiveMinute WHERE IsHour=1 AND IsAudit=0 "
                    "AND CollectionTime=%s ORDER BY Tsno", (town_hour,),
                )
                return list(await cursor.fetchall())
        finally:
            connection.close()

    @staticmethod
    async def _station_names(cursor: Any) -> dict[str, str]:
        """许昌市空气质量管控平台数字站码与中台 10xxB 编码不同，按实际入库站码取名。"""
        await cursor.execute(
            "SELECT Tsno, StationName FROM TownStationFiveMinute "
            "WHERE StationName IS NOT NULL AND StationName <> '' "
            "GROUP BY Tsno, StationName"
        )
        return {str(code).strip(): str(name).strip() for code, name in await cursor.fetchall()}

    async def latest_rows(self, *, now: datetime, lookback_hours: int = 6) -> list[dict[str, Any]]:
        parsed = make_url(self.url)
        connection = await aiomysql.connect(
            host=parsed.host or "127.0.0.1",
            port=parsed.port or 3306,
            user=parsed.username or "",
            password=parsed.password or "",
            db=parsed.database or "DataCrawler",
            autocommit=True,
        )
        try:
            async with connection.cursor() as cursor:
                names = await self._station_names(cursor)
            async with connection.cursor(aiomysql.DictCursor) as cursor:
                office_rows = await self._office_hour_rows(cursor, now, lookback_hours)
                shengkong_rows = await self._shengkong_hour_rows(cursor, now, lookback_hours)
                await cursor.execute(QUERY, (now - timedelta(hours=lookback_hours), now))
                rows = list(await cursor.fetchall())
        finally:
            connection.close()
        all_rows = rows + office_rows + shengkong_rows
        metadata = self._catalog_metadata()
        from app.tools.xuchang.station_catalog.coordinates import normalize_station_name
        code_metadata = {
            normalize_station_name(name): info
            for name, info in metadata.items() if str(name).startswith("4110")
        }
        for row in all_rows:
            code = str(row.get("Tsno") or "").strip()
            info = metadata.get(code) or metadata.get(normalize_station_name(row.get("StationName"))) or code_metadata.get(code, {})
            if not row.get("StationName") and info.get("station_name"):
                row["StationName"] = info["station_name"]
            if not row.get("StationName") and names.get(code):
                row["StationName"] = names[code]
            row["CountyName"] = str(info.get("county_name") or row.get("CountyName") or "").strip() or None
            row["StationType"] = info.get("station_type") or "township"
        return all_rows

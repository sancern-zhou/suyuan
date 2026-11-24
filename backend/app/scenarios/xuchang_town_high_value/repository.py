"""DataCrawler.TownStationData 审核小时值读取（最新完整小时由检测器选取）。"""

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
    async def _station_names(cursor: Any) -> dict[str, str]:
        """旧云平台数字站码与中台 10xxB 编码不同，按实际入库站码取名。"""
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
                await cursor.execute(QUERY, (now - timedelta(hours=lookback_hours), now))
                rows = list(await cursor.fetchall())
        finally:
            connection.close()
        for row in rows:
            code = str(row.get("Tsno") or "").strip()
            if not row.get("StationName") and names.get(code):
                row["StationName"] = names[code]
        return rows

"""许昌国控站经纬度补全

中台 `station` 表对许昌站点未登记经纬度，导致国控站在站点目录里
`longitude/latitude` 为 null。本模块从 XcAiDb 的站点镜像表
（`dat_station_hour` / `dat_station_day`）按站点名匹配读取经纬度，
供目录构建时补全国控站坐标。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger()

CITY_AREA_CODE = "411000"
DEFAULT_DATABASE = "XcAiDb"
STATION_COORDINATE_TABLES = ("dat_station_hour", "dat_station_day")

_PARENTHETICAL = re.compile(r"[（(][^（）()]*[）)]")


def normalize_station_name(value: Any) -> str:
    """归一化站点名用于跨源匹配：去括号后缀、空白，统一“台”字。"""
    text = str(value or "").strip()
    text = _PARENTHETICAL.sub("", text)
    return "".join(text.split()).replace("臺", "台")


def _connection_string(database: str) -> str:
    from config.settings import Settings

    conn_str = Settings().sqlserver_connection_string
    return re.sub(r"DATABASE=\w+", f"DATABASE={database}", conn_str, flags=re.IGNORECASE)


def _query_table(table: str, database: str) -> list[dict[str, Any]]:
    import pyodbc

    sql = (
        f"SELECT station_id, name, MAX(lon) AS lon, MAX(lat) AS lat "
        f"FROM dbo.{table} "
        f"WHERE city_area_code = ? AND lon IS NOT NULL AND lat IS NOT NULL "
        f"GROUP BY station_id, name"
    )
    conn = pyodbc.connect(_connection_string(database), timeout=30)
    try:
        cursor = conn.cursor()
        cursor.execute(sql, CITY_AREA_CODE)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]
    finally:
        conn.close()


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_station_coordinates(
    loader: Callable[[str, str], list[dict[str, Any]]] | None = None,
    *,
    database: str = DEFAULT_DATABASE,
) -> dict[str, dict[str, Any]]:
    """返回 {归一化站点名: {station_id, name, longitude, latitude}}。

    任一张表查询失败只记警告，不影响目录其他部分。
    """
    query = loader or _query_table
    coordinates: dict[str, dict[str, Any]] = {}
    for table in STATION_COORDINATE_TABLES:
        try:
            rows = query(table, database)
        except Exception as exc:  # 数据源不可用不应中断目录构建
            logger.warning(
                "xuchang_station_coordinates_query_failed",
                table=table,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            continue
        for row in rows:
            name = normalize_station_name(row.get("name"))
            longitude = _to_float(row.get("lon"))
            latitude = _to_float(row.get("lat"))
            if not name or longitude is None or latitude is None:
                continue
            coordinates.setdefault(
                name,
                {
                    "station_id": str(row.get("station_id") or "").strip(),
                    "name": str(row.get("name") or "").strip(),
                    "longitude": longitude,
                    "latitude": latitude,
                    "source": f"sqlserver:{table}",
                },
            )
    return coordinates

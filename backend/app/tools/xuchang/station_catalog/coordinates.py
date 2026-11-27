"""许昌国控站经纬度补全

中台 `station` 表对许昌站点未登记经纬度。历史上从 XcAiDb 站点镜像表
读取坐标；`dat_station_hour`/`dat_station_day` 已随 CNEMC 直发链路下线
（2026-10），国控站为固定台站，坐标固化为共享常量
`NATIONAL_STATION_META`，按站点名归一化匹配补全。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import structlog

from app.scenarios.xuchang_city_exceedance.station_catalog import NATIONAL_STATION_META

logger = structlog.get_logger()

COORDINATE_SOURCE = "builtin:national_station_meta"

_PARENTHETICAL = re.compile(r"[（(][^（）()]*[）)]")


def normalize_station_name(value: Any) -> str:
    """归一化站点名用于跨源匹配：去括号后缀、空白，统一“台”字。"""
    text = str(value or "").strip()
    text = _PARENTHETICAL.sub("", text)
    return "".join(text.split()).replace("臺", "台")


def _builtin_rows() -> list[dict[str, Any]]:
    return [
        {"station_id": code, "name": meta["name"], "lon": meta["lon"], "lat": meta["lat"]}
        for code, meta in NATIONAL_STATION_META.items()
    ]


def load_station_coordinates(
    loader: Callable[[str, str], list[dict[str, Any]]] | None = None,
    **_: Any,
) -> dict[str, dict[str, Any]]:
    """返回 {归一化站点名: {station_id, name, longitude, latitude}}。

    保留 loader 参数兼容历史测试注入；默认使用内置常量。
    """
    rows = loader("dat_station_hour", "XcAiDb") if loader else _builtin_rows()
    coordinates: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = normalize_station_name(row.get("name"))
        try:
            longitude = float(row.get("lon"))
            latitude = float(row.get("lat"))
        except (TypeError, ValueError):
            continue
        if not name:
            continue
        coordinates.setdefault(
            name,
            {
                "station_id": str(row.get("station_id") or "").strip(),
                "name": str(row.get("name") or "").strip(),
                "longitude": longitude,
                "latitude": latitude,
                "source": COORDINATE_SOURCE,
            },
        )
    return coordinates

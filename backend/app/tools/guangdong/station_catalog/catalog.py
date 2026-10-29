"""广东站点目录构建与解析（数据源：运维 mart 站点维度）。

数据源：
- guangdong_mart.dim_station：站点目录一致性维度（432 站 = 主网 332 + 组分网 100，每日刷新），
  含城市归属、站点类型中文名、运维单位、部门、经纬度与地址；
- guangdong_mart.dim_station_user：站点→运维人员名册（sys_userstation 桥表，全主网覆盖）。

缓存：共享 StationDirectoryCache（data registry 下 station_directory/guangdong_station_catalog/）
落盘 + 进程内二级缓存；dim_station 每日刷新，TTL 24 小时，工具 refresh 参数可强制重建。

已知缺口：组分站（100 个）源系统未提供经纬度/地址/运维单位/运维人员，目录如实保留缺口，
不做推断填充。

站点屏蔽：停用/废弃站（dim_station.status=0）在目录构建时剔除，不进入工具返回与共享
provider 契约；屏蔽计数写入目录快照 masked_inactive_count 供口径核对。
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import structlog

from app.services.station_directory import (
    StationDirectoryCache,
    normalize_station_type,
)

logger = structlog.get_logger()

MART_SCHEMA = "guangdong_mart"
DSN_ENV = "OPS_MART_DATABASE_URL"

CACHE_NAMESPACE = "guangdong_station_catalog"
CACHE_TTL_SECONDS = 24 * 3600.0

_COMPONENT_LABEL = "组分站"
_TOWNSHIP_LABELS = frozenset({"乡镇站", "省乡镇站"})

# 停用/废弃站点屏蔽规则：dim_station.status=0 视为停用并从目录剔除；
# status 为空或取值未知时保留（宁多勿漏，避免误屏蔽在用站）。
# mart 的 dim_station 仍保留全部站点（历史工单关联需要），屏蔽只在目录工具层生效。
INACTIVE_STATUS_VALUES: frozenset[int] = frozenset({0})

# dim_station.station_type_name（DDStationType 字典中文名）→ 共享契约规范类型
_CANONICAL_TYPE_BY_LABEL = {
    "国控站": "国控",
    "省控站": "省控",
    "市控站": "市控",
    "区域站": "区域站",
    "乡镇站": "乡镇控",
    "省乡镇站": "乡镇控",
    "省建站": "其他",
    "VOC站": "其他",
    _COMPONENT_LABEL: "其他",
}

_ALL_TYPE_TOKENS = frozenset({"全部", "所有", "all", "*", "any"})

_STATION_SQL = f"""
    select station_id, station_code, station_name, city_code, city_name,
           station_type_name, operation_unit_id, operation_unit_name,
           department_name, manager_name, longitude, latitude, address,
           status, unique_code, operation_type, refreshed_at
    from {MART_SCHEMA}.dim_station
    order by city_code, station_id
"""

_MANAGER_SQL = f"""
    select station_id, user_id, user_name, user_status
    from {MART_SCHEMA}.dim_station_user
"""

_DISK_CACHE = StationDirectoryCache(
    CACHE_NAMESPACE, ttl_seconds=CACHE_TTL_SECONDS
)

_cache_lock = asyncio.Lock()
_memory_cache: dict[str, Any] | None = None


class StationCatalogError(RuntimeError):
    """站点目录构建或解析失败"""


def _mart_dsn() -> str:
    dsn = os.getenv(DSN_ENV, "")
    if not dsn:
        raise StationCatalogError(
            "OPS_MART_DATABASE_URL 未配置（广东 mart 站点目录连接）"
        )
    return dsn


def _clean(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    cleaned: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> str:
    return str(value or "").strip()


def _is_active_user(status: Any) -> bool:
    """按源系统原文过滤在岗账号；状态为空时保留（宁多勿漏）。dim_user 契约实测在岗值为 Enabled。"""
    text = _to_str(status).lower()
    return not text or text.startswith("enable")


def _is_active_station(status: Any) -> bool:
    """status=0（含文本形态）视为停用站；空值/未知值保留。"""

    if status is None or status == "":
        return True
    try:
        return int(float(status)) not in INACTIVE_STATUS_VALUES
    except (TypeError, ValueError):
        return True


def build_catalog(
    station_rows: list[dict[str, Any]],
    manager_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """由 dim_station 行与 dim_station_user 行构建目录快照（纯函数，可测）。"""

    managers: dict[str, list[str]] = {}
    for row in manager_rows:
        station_id = _to_str(row.get("station_id"))
        name = _to_str(row.get("user_name"))
        if not station_id or not name or not _is_active_user(row.get("user_status")):
            continue
        bucket = managers.setdefault(station_id, [])
        if name not in bucket:
            bucket.append(name)

    stations: list[dict[str, Any]] = []
    masked_inactive_count = 0
    for row in station_rows:
        if not _is_active_station(row.get("status")):
            masked_inactive_count += 1
            continue
        station_name = _to_str(row.get("station_name"))
        if not station_name:
            continue
        type_label = _to_str(row.get("station_type_name"))
        canonical_type = _CANONICAL_TYPE_BY_LABEL.get(type_label)
        if canonical_type is None:
            canonical_type = normalize_station_type(type_label) or ""
        station_id = _to_str(row.get("station_id"))
        stations.append(
            {
                "station_id": station_id,
                "station_code": _to_str(row.get("station_code")),
                "station_name": station_name,
                "unique_code": _to_str(row.get("unique_code")),
                "city_code": _to_str(row.get("city_code")),
                "city_name": _to_str(row.get("city_name")),
                "station_type_name": type_label,
                "station_type": canonical_type,
                "station_category": (
                    "component"
                    if type_label == _COMPONENT_LABEL
                    else "township"
                    if type_label in _TOWNSHIP_LABELS
                    else "regular"
                ),
                "operation_unit_id": _to_str(row.get("operation_unit_id")),
                "operation_unit_name": _to_str(row.get("operation_unit_name")),
                "department_name": _to_str(row.get("department_name")),
                "manager_name": _to_str(row.get("manager_name")),
                "managers": list(managers.get(station_id, ())),
                "longitude": _to_float(row.get("longitude")),
                "latitude": _to_float(row.get("latitude")),
                "address": _to_str(row.get("address")),
                "status": row.get("status"),
                "operation_type": _to_str(row.get("operation_type")),
                "data_source": f"{MART_SCHEMA}.dim_station",
            }
        )

    component_count = sum(
        1 for item in stations if item["station_category"] == "component"
    )
    return {
        "generated_at": time.time(),
        "stations": stations,
        "station_count": len(stations),
        "main_net_count": len(stations) - component_count,
        "component_count": component_count,
        "masked_inactive_count": masked_inactive_count,
    }


async def _fetch_catalog() -> dict[str, Any]:
    import asyncpg

    conn = await asyncpg.connect(
        _mart_dsn(),
        server_settings={"search_path": f"{MART_SCHEMA},public"},
    )
    try:
        station_rows = [dict(row) for row in await conn.fetch(_STATION_SQL)]
        try:
            manager_rows = [dict(row) for row in await conn.fetch(_MANAGER_SQL)]
        except asyncpg.UndefinedTableError:
            manager_rows = []
            logger.warning(
                "guangdong_station_catalog_bridge_missing",
                hint="dim_station_user 未建表，先在部署机执行同步与 dbt run -s dim_station_user",
            )
    finally:
        await conn.close()
    return build_catalog(station_rows, manager_rows)


async def load_catalog(refresh: bool = False) -> dict[str, Any]:
    """加载站点目录：进程内缓存 → 落盘缓存（TTL 24h）→ mart 重建。"""

    global _memory_cache
    async with _cache_lock:
        if not refresh:
            if (
                _memory_cache
                and time.time() - float(_memory_cache.get("generated_at") or 0)
                < CACHE_TTL_SECONDS
            ):
                return {**_memory_cache, "from_cache": True}
            cached = _DISK_CACHE.load()
            if cached and isinstance(cached.get("stations"), list):
                _memory_cache = cached
                return cached
        fresh = await _fetch_catalog()
        _memory_cache = fresh
        _DISK_CACHE.save(fresh)
        return {**fresh, "from_cache": False}


def iter_stations(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    return list(catalog.get("stations") or ())


def _code_hit(station: dict[str, Any], wanted: list[str]) -> bool:
    codes = {
        text.upper()
        for text in (
            station.get("station_code"),
            station.get("unique_code"),
            station.get("station_id"),
        )
        if _to_str(text)
    }
    return any(code.upper() in codes for code in wanted)


def _name_hit(station: dict[str, Any], wanted: list[str]) -> bool:
    name = station.get("station_name") or ""
    return any(
        item == name or item in name or name.endswith(item) for item in wanted
    )


def _city_hit(station: dict[str, Any], wanted: list[str]) -> bool:
    city = station.get("city_name") or ""
    if not city:
        return False
    return any(
        city == item or city.startswith(item) or item.startswith(city)
        for item in wanted
    )


def _type_hit(station: dict[str, Any], wanted: list[str]) -> bool:
    label = station.get("station_type_name") or ""
    canonical = station.get("station_type") or ""
    for item in wanted:
        if item in _ALL_TYPE_TOKENS:
            return True
        if item == label or item == canonical or label.startswith(item):
            return True
        normalized = normalize_station_type(item)
        if normalized and normalized == canonical:
            return True
    return False


def _unit_hit(station: dict[str, Any], wanted: list[str]) -> bool:
    unit = station.get("operation_unit_name") or ""
    if not unit:
        return False
    return any(item in unit or unit in item for item in wanted)


def _manager_names(station: dict[str, Any]) -> list[str]:
    names = list(station.get("managers") or ())
    if station.get("manager_name"):
        names.append(station["manager_name"])
    return names


def _manager_hit(station: dict[str, Any], wanted: list[str]) -> bool:
    names = _manager_names(station)
    if not names:
        return False
    return any(
        item == name or item in name or name in item
        for item in wanted
        for name in names
    )


def _keyword_hit(station: dict[str, Any], keyword: str) -> bool:
    blob = " ".join(
        filter(
            None,
            (
                station.get("station_name"),
                station.get("station_code"),
                station.get("unique_code"),
                station.get("station_id"),
                station.get("city_name"),
                station.get("address"),
                station.get("operation_unit_name"),
                station.get("station_type_name"),
                *_manager_names(station),
            ),
        )
    )
    return keyword in blob


def resolve_stations(
    catalog: dict[str, Any],
    *,
    station_names: Any = None,
    station_codes: Any = None,
    cities: Any = None,
    station_types: Any = None,
    operation_units: Any = None,
    managers: Any = None,
    keyword: Any = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """按工具契约解析站点：各过滤条件 AND 组合，无条件时返回全量。"""

    names = _clean(station_names)
    codes = _clean(station_codes)
    city_filters = _clean(cities)
    type_filters = [
        item
        for item in _clean(station_types)
        if item not in _ALL_TYPE_TOKENS
    ]
    unit_filters = _clean(operation_units)
    manager_filters = _clean(managers)
    keyword_text = _to_str(keyword)

    results: list[dict[str, Any]] = []
    for station in iter_stations(catalog):
        if codes and not _code_hit(station, codes):
            continue
        if names and not _name_hit(station, names):
            continue
        if city_filters and not _city_hit(station, city_filters):
            continue
        if type_filters and not _type_hit(station, type_filters):
            continue
        if unit_filters and not _unit_hit(station, unit_filters):
            continue
        if manager_filters and not _manager_hit(station, manager_filters):
            continue
        if keyword_text and not _keyword_hit(station, keyword_text):
            continue
        results.append(station)
        if limit is not None and limit > 0 and len(results) >= limit:
            break
    return results


def available_cities(catalog: dict[str, Any]) -> list[str]:
    cities: list[str] = []
    for station in iter_stations(catalog):
        city = station.get("city_name") or ""
        if city and city not in cities:
            cities.append(city)
    return cities

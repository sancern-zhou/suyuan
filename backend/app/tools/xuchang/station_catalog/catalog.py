"""
许昌空气监测站点目录

数据源为大气环境监测数据接口中台：
- 乡镇站：v_t_d_src 视图 distinct（站点编码为自定义编码，归属区县从站点名称前缀解析）
- 常规站（国控等）：station 表 areacode=411000
- 区县：region 表 4110 前缀 level>=3

目录构建结果缓存到 data registry，TTL 默认 7 天。
"""
from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from app.tools.xuchang.airdata_platform.client import (
    DATA_VIEW_QUERY_FIELDS,
    get_airdata_platform_client,
)
from app.utils.path_config import get_data_registry

from .coordinates import load_station_coordinates, normalize_station_name

logger = structlog.get_logger()

CITY_NAME = "许昌市"
CITY_CODE = "411000"
CITY_AREA_PREFIX = "4110"

TOWNSHIP_SOURCE_VIEW = "v_t_d_src"

STATION_TYPE_NAME_MAP = {1: "国控", 2: "省控", 3: "市控", 4: "区县控", 5: "乡镇控"}

ZONE_NAME_ALIASES = ("示范区",)

CACHE_DIR_NAME = "xuchang_station_catalog"
CACHE_FILE_NAME = "catalog_cache.json"
CACHE_TTL_HOURS = 168.0
TOWNSHIP_COORDINATES_FILE = Path(__file__).with_name("township_coordinates.tsv")


class StationCatalogError(RuntimeError):
    """站点目录构建或解析失败"""


def split_township_name(
    station_name: str, district_names: list[str]
) -> tuple[str, str]:
    """从乡镇站名称中拆出（归属区县, 乡镇名），按最长前缀匹配"""
    candidates = sorted(set(district_names) | set(ZONE_NAME_ALIASES), key=len, reverse=True)
    for district in candidates:
        district = str(district or "").strip()
        if district and station_name.startswith(district):
            return district, station_name[len(district):].strip()
    return "", station_name


def cache_path():
    return get_data_registry() / CACHE_DIR_NAME / CACHE_FILE_NAME


def _normalize_station_name(value: Any) -> str:
    """Normalize names shared by the platform view and the coordinate table."""
    return "".join(str(value or "").split()).replace("臺", "台")


@lru_cache(maxsize=1)
def load_township_coordinates() -> dict[str, dict[str, Any]]:
    """Load the supplied township coordinate table shipped with the tool."""
    coordinates: dict[str, dict[str, Any]] = {}
    try:
        lines = TOWNSHIP_COORDINATES_FILE.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("xuchang_township_coordinates_read_failed", error=str(exc))
        return coordinates

    for line in lines:
        if not line or line.startswith("#"):
            continue
        # The checked-in asset is TSV; tolerate the escaped separator used by
        # older generated copies as well.
        fields = line.split("\t") if "\t" in line else line.split(r"\t")
        if len(fields) != 4:
            continue
        name, address, longitude, latitude = (item.strip() for item in fields)
        try:
            lon = float(longitude)
            lat = float(latitude)
        except ValueError:
            continue
        record = {"address": address, "longitude": lon, "latitude": lat}
        coordinates[_normalize_station_name(name)] = record
        # Platform deployments have used both full administrative prefixes
        # and the shorter town name in the township view.
        for prefix in ("许昌市", "禹州市", "长葛市", "鄢陵县", "襄城县", "建安区", "示范区"):
            if name.startswith(prefix):
                coordinates.setdefault(_normalize_station_name(name[len(prefix):]), record)
                break
    return coordinates


def normalize_districts(region_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    districts: list[dict[str, Any]] = []
    for row in region_rows:
        areacode = str(row.get("areacode") or "").strip()
        areaname = str(row.get("areaname") or "").strip()
        try:
            level = int(row.get("level") or 0)
        except (TypeError, ValueError):
            level = 0
        if not areacode.startswith(CITY_AREA_PREFIX) or level < 3 or not areaname:
            continue
        districts.append({"areacode": areacode, "name": areaname})
    return sorted(districts, key=lambda item: item["areacode"])


def normalize_townships(
    rows: list[dict[str, Any]],
    district_names: list[str],
    coordinate_rows: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    townships: dict[str, dict[str, Any]] = {}
    coordinate_rows = coordinate_rows or {}
    for row in rows:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()
        if not code or not name or code in townships:
            continue
        district, town = split_township_name(name, district_names)
        coordinate = coordinate_rows.get(_normalize_station_name(name)) or coordinate_rows.get(
            _normalize_station_name(town)
        ) or {}
        townships[code] = {
            "station_code": code,
            "station_name": name,
            "district": district,
            "city": CITY_NAME,
            "station_type": "township",
            "type_name": "乡镇站",
            "longitude": coordinate.get("longitude"),
            "latitude": coordinate.get("latitude"),
            "address": coordinate.get("address", ""),
            "coordinate_source": "township_coordinates.xlsx" if coordinate else None,
            "data_source": f"airdata_platform:{TOWNSHIP_SOURCE_VIEW}",
        }
    return sorted(
        townships.values(), key=lambda item: (item["district"], item["station_name"])
    )


def normalize_regular_stations(
    rows: list[dict[str, Any]],
    districts: list[dict[str, Any]],
    station_coordinates: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    districts_by_code = {item["areacode"]: item["name"] for item in districts}
    station_coordinates = station_coordinates or {}
    stations: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("stationcode") or "").strip()
        if not code:
            continue
        try:
            type_id = int(row.get("stationtypeid") or 0)
        except (TypeError, ValueError):
            type_id = 0
        name = str(row.get("positionname") or "").strip() or code
        longitude = row.get("longitude")
        latitude = row.get("latitude")
        coordinate_source = None
        if longitude is None or latitude is None:
            fallback = station_coordinates.get(normalize_station_name(name)) or {}
            if fallback:
                longitude = fallback.get("longitude")
                latitude = fallback.get("latitude")
                coordinate_source = fallback.get("source")
        stations[code] = {
            "station_code": code,
            "unique_code": str(row.get("uniquecode") or "").strip(),
            "station_name": name,
            "district": districts_by_code.get(str(row.get("areacode") or "").strip(), ""),
            "city": CITY_NAME,
            "station_type": "regular",
            "type_name": STATION_TYPE_NAME_MAP.get(type_id, "常规站"),
            "longitude": longitude,
            "latitude": latitude,
            "address": str(row.get("address") or "").strip(),
            "coordinate_source": coordinate_source,
            "data_source": "airdata_platform:station",
        }
    return sorted(
        stations.values(), key=lambda item: (item["district"], item["station_name"])
    )


def build_catalog() -> dict[str, Any]:
    """从中台拉取并构建站点目录（不读缓存）"""
    client = get_airdata_platform_client()

    region_rows = client.query_page("region", size=1000)["rows"]
    districts = normalize_districts(region_rows)
    district_names = [item["name"] for item in districts]

    town_rows = client.query_all(
        TOWNSHIP_SOURCE_VIEW,
        selected_fields=list(DATA_VIEW_QUERY_FIELDS),
        max_rows=5000,
    )["rows"]
    coordinate_rows = load_township_coordinates()
    station_coordinates = load_station_coordinates()
    station_rows = client.query_page(
        "station",
        filters=[{"field": "areacode", "operator": "eq", "value": CITY_CODE}],
        size=1000,
    )["rows"]

    return {
        "generated_at": time.time(),
        "city": {"name": CITY_NAME, "areacode": CITY_CODE},
        "districts": districts,
        "townships": normalize_townships(town_rows, district_names, coordinate_rows),
        "regular_stations": normalize_regular_stations(
            station_rows, districts, station_coordinates
        ),
    }


def load_catalog(force_refresh: bool = False) -> dict[str, Any]:
    """加载站点目录：缓存未过期直接返回，否则重建并写缓存"""
    path = cache_path()
    if not force_refresh:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            generated_at = float(payload.get("generated_at") or 0)
            has_stations = payload.get("townships") or payload.get("regular_stations")
            if has_stations and time.time() - generated_at < CACHE_TTL_HOURS * 3600:
                payload["from_cache"] = True
                return payload
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("xuchang_station_catalog_cache_read_failed", error=str(exc))

    catalog = build_catalog()
    catalog["from_cache"] = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("xuchang_station_catalog_cache_write_failed", error=str(exc))
    return catalog


def iter_stations(catalog: dict[str, Any], station_type: str = "all") -> list[dict[str, Any]]:
    stations: list[dict[str, Any]] = []
    if station_type in ("all", "township"):
        stations.extend(catalog.get("townships") or [])
    if station_type in ("all", "regular"):
        stations.extend(catalog.get("regular_stations") or [])
    return stations


def resolve_stations(
    catalog: dict[str, Any],
    station_names: list[str] | None = None,
    station_codes: list[str] | None = None,
    districts: list[str] | None = None,
    station_type: str = "all",
) -> list[dict[str, Any]]:
    """按名称（模糊）/编码/区县解析站点，编码支持站点编码与唯一编码"""
    pool = iter_stations(catalog, station_type)

    wanted_names = [str(item or "").strip() for item in (station_names or []) if str(item or "").strip()]
    wanted_codes = {str(item or "").strip() for item in (station_codes or []) if str(item or "").strip()}
    wanted_districts = [str(item or "").strip() for item in (districts or []) if str(item or "").strip()]

    def _district_match(payload: dict[str, Any]) -> bool:
        if not wanted_districts:
            return True
        district = str(payload.get("district") or "")
        return any(
            district == want
            or district.startswith(want)
            or want.startswith(district)
            for want in wanted_districts
            if district
        )

    def _name_match(payload: dict[str, Any]) -> bool:
        if not wanted_names:
            return False
        name = str(payload.get("station_name") or "")
        return any(want == name or want in name or name.endswith(want) for want in wanted_names)

    matched: list[dict[str, Any]] = []
    seen: set = set()
    has_name_or_code_filter = bool(wanted_names or wanted_codes)
    for payload in pool:
        if has_name_or_code_filter:
            code_hit = bool(wanted_codes) and (
                str(payload.get("station_code") or "") in wanted_codes
                or str(payload.get("unique_code") or "") in wanted_codes
            )
            if not (code_hit or _name_match(payload)):
                continue
        if not _district_match(payload):
            continue
        key = str(payload.get("station_code"))
        if key in seen:
            continue
        seen.add(key)
        matched.append(payload)
    return matched

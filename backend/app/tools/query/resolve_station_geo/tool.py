from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.query_gd_suncere.tool import GeoMappingResolver


TYPE_NAME_MAP = {
    1.0: "国控",
    2.0: "省控",
    3.0: "市控",
    4.0: "区县控",
    5.0: "乡镇控",
    6.0: "其他",
    7.0: "背景站",
    8.0: "区域站",
    9.0: "交通站",
    15.0: "专项站",
}


def _clean_list(values: list[str] | str | None) -> list[str]:
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


def _type_name(type_id: Any) -> str:
    try:
        key = float(type_id)
    except (TypeError, ValueError):
        return "未知"
    return TYPE_NAME_MAP.get(key, f"类型{key:g}")


def _station_payload(station_code: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "station_name": meta.get("name") or station_code,
        "station_code": station_code,
        "city": meta.get("city") or "",
        "district": meta.get("district") or "",
        "longitude": _to_float(meta.get("lng") or meta.get("longitude") or meta.get("经度")),
        "latitude": _to_float(meta.get("lat") or meta.get("latitude") or meta.get("纬度")),
        "address": meta.get("address") or "",
        "admin_code": meta.get("admin_code") or "",
        "type_id": meta.get("type_id"),
        "type_name": _type_name(meta.get("type_id")),
        "station_category": meta.get("station_category") or "regular",
        "data_domains": meta.get("data_domains") or ["常规六参数"],
    }


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "backend").exists() and (parent / "frontend").exists():
            return parent
    return current.parents[5]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class ComponentStationCatalog:
    """File-backed directory for PM2.5 component and VOCs stations."""

    def __init__(self) -> None:
        root = _repo_root()
        self._station_to_code = self._load_station_codes(root)
        self._station_meta = self._load_station_metadata(root)
        self._city_to_pm25 = self._load_city_mapping(
            root / "backend" / "app" / "config" / "particulate_city_multi_station_mapping.json"
        )
        self._city_to_vocs = self._load_city_mapping(
            root / "backend" / "app" / "config" / "vocs_city_station_mapping.json"
        )

    def resolve(
        self,
        *,
        station_names: list[str],
        station_codes: list[str],
        cities: list[str],
    ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        requested_names = list(station_names)
        requested_codes = list(station_codes)
        for city in cities:
            for name in self._stations_for_city(city):
                if name not in requested_names:
                    requested_names.append(name)

        unresolved_names: list[str] = []
        resolved_codes: list[str] = []
        seen_codes: set[str] = set()

        for code in requested_codes:
            if code in self._station_to_code.values():
                if code not in seen_codes:
                    resolved_codes.append(code)
                    seen_codes.add(code)
            else:
                unresolved_names.append(code)

        for name in requested_names:
            code = self._station_to_code.get(name)
            if not code:
                unresolved_names.append(name)
                continue
            if code not in seen_codes:
                resolved_codes.append(code)
                seen_codes.add(code)

        stations = [self._payload_for_code(code) for code in resolved_codes]
        return stations, unresolved_names, []

    def _stations_for_city(self, city: str) -> list[str]:
        city_key = city.strip().removesuffix("市")
        names: list[str] = []
        for mapping in (self._city_to_pm25, self._city_to_vocs):
            for name in mapping.get(city_key, []):
                if name not in names:
                    names.append(name)
        return names

    def _payload_for_code(self, code: str) -> dict[str, Any]:
        meta = self._station_meta.get(code, {})
        station_name = meta.get("name") or self._name_for_code(code) or code
        domains = self._domains_for_station(station_name)
        return _station_payload(
            code,
            {
                **meta,
                "name": station_name,
                "station_category": "component",
                "data_domains": domains,
            },
        )

    def _domains_for_station(self, station_name: str) -> list[str]:
        domains: list[str] = []
        if any(station_name in stations for stations in self._city_to_pm25.values()):
            domains.append("PM2.5组分")
        if any(station_name in stations for stations in self._city_to_vocs.values()):
            domains.append("VOCs")
        return domains or ["PM2.5组分", "VOCs"]

    def _name_for_code(self, code: str) -> str | None:
        for name, station_code in self._station_to_code.items():
            if station_code == code:
                return name
        return None

    @staticmethod
    def _load_station_codes(root: Path) -> dict[str, str]:
        geo = _read_json(root / "backend" / "config" / "geo_mappings.json")
        return {
            str(name).strip(): str(code).strip()
            for name, code in geo.get("stations", {}).items()
            if str(name).strip() and str(code).strip()
        }

    @staticmethod
    def _load_city_mapping(path: Path) -> dict[str, list[str]]:
        payload = _read_json(path)
        result: dict[str, list[str]] = {}
        for city, stations in payload.get("mappings", {}).items():
            city_key = str(city).strip().removesuffix("市")
            if isinstance(stations, str):
                stations = [stations]
            result[city_key] = [str(item).strip() for item in stations or [] if str(item).strip()]
        return result

    @staticmethod
    def _load_station_metadata(root: Path) -> dict[str, dict[str, Any]]:
        metadata: dict[str, dict[str, Any]] = {}
        for relative in (
            "backend/config/station_district_results_with_type_id.json",
            "backend/config/station_district_results_with_type_id.before_final_fix",
            "backend/config/station_district_results_with_type_id.json.before_final_fix",
            "backend/config/station_district_results_with_type_id.json.before_city_fix",
        ):
            payload = _read_json(root / relative)
            records = payload.get("data", []) if isinstance(payload, dict) else []
            for item in records:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("唯一编码") or "").strip()
                name = str(item.get("站点名称") or "").strip()
                if not code or not name or code in metadata:
                    continue
                city = str(item.get("城市名称") or item.get("城市") or "").strip().removesuffix("市")
                district_raw = item.get("区县")
                district = district_raw.strip() if isinstance(district_raw, str) else ""
                metadata[code] = {
                    "name": name,
                    "city": city,
                    "district": district,
                    "lng": item.get("经度"),
                    "lat": item.get("纬度"),
                    "address": item.get("详细地址", ""),
                    "admin_code": item.get("行政区划代码", ""),
                    "type_id": item.get("站点类型ID"),
                }
        return metadata


def get_component_station_catalog() -> ComponentStationCatalog:
    return ComponentStationCatalog()


class ResolveStationGeoTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="resolve_station_geo",
            description="Resolve Guangdong regular and component monitoring station directory attributes.",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "resolve_station_geo",
                "description": "广东省站点目录解析工具。支持常规站点和组分站点，按站点、站点编码、城市或区县返回站点编码、经纬度、城市、区县、地址、站点类型和数据域；站点上图、定位、城市/区县下辖站点发现、组分工具参数准备前应调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "stations": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "站点名称列表，支持精确或模糊匹配。",
                        },
                        "station_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "站点唯一编码列表。",
                        },
                        "cities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "城市名称列表。常规站点返回该城市下辖站点；组分站点返回该城市配置的 PM2.5/VOCs 组分站点。",
                        },
                        "districts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "区县名称列表，仅用于常规站点目录展开。",
                        },
                        "station_type": {
                            "type": "string",
                            "description": "常规站点类型过滤，如 国控、省控、市控、1.0、2.0。",
                        },
                        "station_category": {
                            "type": "string",
                            "enum": ["regular", "component", "all"],
                            "description": "站点类别：regular=常规站点，component=组分站点，all=同时查询两类；默认 regular。",
                            "default": "regular",
                        },
                    },
                },
            },
            version="0.1.0",
            requires_context=False,
        )

    async def execute(
        self,
        stations: list[str] | str | None = None,
        station_codes: list[str] | str | None = None,
        cities: list[str] | str | None = None,
        districts: list[str] | str | None = None,
        station_type: str | None = None,
        station_category: str = "regular",
        **_: Any,
    ) -> dict[str, Any]:
        requested_names = _clean_list(stations)
        requested_codes = _clean_list(station_codes)
        requested_cities = _clean_list(cities)
        requested_districts = _clean_list(districts)
        categories = {"regular", "component"} if station_category == "all" else {station_category or "regular"}

        station_payloads: list[dict[str, Any]] = []
        unresolved: list[str] = []
        unresolved_codes: list[str] = []
        seen_payload_codes: set[tuple[str, str]] = set()

        if "regular" in categories:
            resolved_codes = list(requested_codes)
            regular_unresolved = list(requested_names)
            name_codes: list[str] = []
            if requested_names:
                name_codes = GeoMappingResolver.resolve_station_codes(requested_names)
                for code in name_codes:
                    if code not in resolved_codes:
                        resolved_codes.append(code)
                for name in requested_names:
                    if GeoMappingResolver.resolve_station_codes([name]):
                        regular_unresolved = [item for item in regular_unresolved if item != name]
            if requested_cities:
                if station_type:
                    city_codes, _metadata = GeoMappingResolver.resolve_station_codes_by_type(
                        station_type, requested_cities
                    )
                else:
                    city_codes = GeoMappingResolver.resolve_station_codes_by_city(requested_cities)
                for code in city_codes:
                    if code not in resolved_codes:
                        resolved_codes.append(code)
            if requested_districts:
                for code in GeoMappingResolver.resolve_station_codes_by_district(requested_districts):
                    if code not in resolved_codes:
                        resolved_codes.append(code)

            for code in resolved_codes:
                meta = GeoMappingResolver.get_station_meta(code)
                if not meta:
                    unresolved_codes.append(code)
                    continue
                payload = _station_payload(code, {**meta, "station_category": "regular"})
                key = (payload["station_category"], payload["station_code"])
                if key not in seen_payload_codes:
                    seen_payload_codes.add(key)
                    station_payloads.append(payload)
            unresolved.extend(regular_unresolved)

        if "component" in categories:
            component_payloads, component_unresolved, component_unresolved_codes = (
                get_component_station_catalog().resolve(
                    station_names=requested_names,
                    station_codes=requested_codes,
                    cities=requested_cities,
                )
            )
            for payload in component_payloads:
                key = (payload["station_category"], payload["station_code"])
                if key not in seen_payload_codes:
                    seen_payload_codes.add(key)
                    station_payloads.append(payload)
            unresolved.extend(component_unresolved)
            unresolved_codes.extend(component_unresolved_codes)

        success = bool(station_payloads) and not unresolved and not unresolved_codes
        status = "success" if success else "failed"
        summary = (
            f"解析到 {len(station_payloads)} 个站点地理属性。"
            if station_payloads
            else "未解析到可用站点地理属性。"
        )
        return {
            "status": status,
            "success": success,
            "summary": summary,
            "data": {
                "stations": station_payloads,
                "unresolved_stations": unresolved,
                "unresolved_station_codes": unresolved_codes,
            },
            "metadata": {
                "tool_name": "resolve_station_geo",
                "generator": "resolve_station_geo",
                "unresolved_stations": unresolved,
                "unresolved_station_codes": unresolved_codes,
                "station_count": len(station_payloads),
                "query_scope": {"cities": requested_cities, "districts": requested_districts},
                "station_category": station_category,
            },
        }


async def resolve_station_geo(context=None, **kwargs: Any) -> dict[str, Any]:
    return await ResolveStationGeoTool().execute(**kwargs)

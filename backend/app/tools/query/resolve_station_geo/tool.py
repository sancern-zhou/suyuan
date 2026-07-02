from __future__ import annotations

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
    }


class ResolveStationGeoTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="resolve_station_geo",
            description="Resolve Guangdong monitoring station names or codes to station geographic attributes and coordinates.",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "resolve_station_geo",
                "description": "广东省监测站点地理属性解析工具。按站点名称或站点编码返回站点经纬度、城市、区县、地址和站点类型；站点上图或定位前应调用。",
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
        **_: Any,
    ) -> dict[str, Any]:
        requested_names = _clean_list(stations)
        requested_codes = _clean_list(station_codes)
        resolved_codes = list(requested_codes)
        unresolved = list(requested_names)

        if requested_names:
            name_codes = GeoMappingResolver.resolve_station_codes(requested_names)
            for code in name_codes:
                if code not in resolved_codes:
                    resolved_codes.append(code)
            for name in requested_names:
                if GeoMappingResolver.resolve_station_codes([name]):
                    unresolved = [item for item in unresolved if item != name]

        station_payloads: list[dict[str, Any]] = []
        unresolved_codes: list[str] = []
        for code in resolved_codes:
            meta = GeoMappingResolver.get_station_meta(code)
            if not meta:
                unresolved_codes.append(code)
                continue
            payload = _station_payload(code, meta)
            if payload["longitude"] is None or payload["latitude"] is None:
                unresolved_codes.append(code)
                continue
            station_payloads.append(payload)

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
            },
        }


async def resolve_station_geo(context=None, **kwargs: Any) -> dict[str, Any]:
    return await ResolveStationGeoTool().execute(**kwargs)

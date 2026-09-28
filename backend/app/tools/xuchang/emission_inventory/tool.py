"""Query the registered Xuchang enterprise emission inventory asset."""

from __future__ import annotations

import math
from typing import Any

import structlog

from app.services.data_registry import DataRegistryService, data_registry
from app.tools.analysis.xuchang_upwind_permit_sources.inventory_asset import (
    EMISSION_FIELD_MAPPING,
    XUCHANG_INVENTORY_DATA_ID,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()

TOOL_NAME = "query_xuchang_emission_inventory"

POLLUTANT_LABELS = {
    "emission_so2": "SO2",
    "emission_nox": "NOx",
    "emission_co": "CO",
    "emission_vocs": "VOCs",
    "emission_nh3": "NH3",
    "emission_tsp": "TSP",
    "emission_pm10": "PM10",
    "emission_pm25": "PM2.5",
    "emission_bc": "BC",
    "emission_oc": "OC",
    "emission_co2": "CO2",
    "emission_ch4": "CH4",
    "emission_n2o": "N2O",
    "emission_hfcs": "HFCs",
}
DEFAULT_EMISSION_KEYS = (
    "emission_so2",
    "emission_nox",
    "emission_co",
    "emission_vocs",
    "emission_nh3",
    "emission_tsp",
    "emission_pm10",
    "emission_pm25",
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def _compact_emissions(emissions: dict[str, Any] | None) -> dict[str, float]:
    source = emissions or {}
    return {
        key: round(float(value), 6)
        for key, value in source.items()
        if key in POLLUTANT_LABELS and value
    }


class XuchangEmissionInventoryTool(LLMTool):
    """Query Xuchang enterprise emission inventory (source list) records."""

    def __init__(
        self,
        registry: DataRegistryService | None = None,
        inventory_data_id: str = XUCHANG_INVENTORY_DATA_ID,
    ) -> None:
        self._registry = registry or data_registry
        self._inventory_data_id = inventory_data_id
        self._records: list[dict[str, Any]] | None = None
        pollutant_enum = [
            key for key in EMISSION_FIELD_MAPPING.values() if key in POLLUTANT_LABELS
        ]
        super().__init__(
            name=TOOL_NAME,
            description=(
                "查询许昌市企业排放源清单（源清单，约2300家有坐标企业，覆盖堆场、工业涂装、"
                "有色冶炼、铸造、工业锅炉等34个排放扇区）。支持按企业名称模糊匹配、统一社会信用代码、"
                "区县、排放扇区、坐标周边半径筛选，并可按污染物年排放量排序/阈值过滤，"
                "返回企业坐标、行业、扇区与SO2/NOx/VOCs/PM2.5等年度排放量（吨）。"
                "排污许可证详情（许可编号、许可污染物、有效期）用 execute_postgres_sql_query 查询 permit_licenses；"
                "站点上风向企业筛查用 analyze_xuchang_upwind_permit_sources；"
                "本工具用于直接查询清单企业及其排放量。"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False,
            function_schema={
                "name": TOOL_NAME,
                "description": (
                    "查询许昌市企业排放源清单：按企业名称/信用代码/区县/排放扇区/周边半径筛选企业，"
                    "返回坐标、行业与年度排放量（吨），可按污染物排序。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "enterprise_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "企业名称关键词列表（模糊包含匹配，如 天源生物）",
                        },
                        "unified_social_credit_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "统一社会信用代码列表（精确匹配）",
                        },
                        "districts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "区县关键词列表（如 建安、禹州、长葛）",
                        },
                        "sectors": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "排放扇区名称列表（sheet 名，如 堆场、工业涂装、有色冶炼、铸造、工业锅炉、汽修）；"
                                "先用 list_sectors=true 查看可选值"
                            ),
                        },
                        "lat": {"type": "number", "description": "中心点纬度（与 radius_km 配合做周边筛选）"},
                        "lon": {"type": "number", "description": "中心点经度"},
                        "radius_km": {
                            "type": "number",
                            "minimum": 0.5,
                            "maximum": 100,
                            "description": "周边筛选半径（公里），默认 5，仅提供 lat/lon 时生效",
                        },
                        "pollutant": {
                            "type": "string",
                            "enum": pollutant_enum,
                            "description": (
                                "按该污染物年排放量排序/过滤，如 emission_pm25、emission_vocs、emission_nox；"
                                "缺省按给定污染物合计排序"
                            ),
                        },
                        "min_emission_tonnes": {
                            "type": "number",
                            "minimum": 0,
                            "description": "所选污染物的年排放量下限（吨）",
                        },
                        "top_n": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "description": "返回条数上限，默认 20",
                        },
                        "list_sectors": {
                            "type": "boolean",
                            "description": "仅返回清单扇区与企业数量统计（用于发现可选 sectors 值）",
                        },
                    },
                },
            },
        )

    async def execute(
        self,
        enterprise_names: list[str] | None = None,
        unified_social_credit_codes: list[str] | None = None,
        districts: list[str] | None = None,
        sectors: list[str] | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: float = 5.0,
        pollutant: str | None = None,
        min_emission_tonnes: float | None = None,
        top_n: int = 20,
        list_sectors: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        records, status = self._load_records()
        if records is None:
            return self._payload(
                status="unavailable",
                data=[],
                summary=f"源清单资产不可用：{status.get('reason', '未注册')}",
                metadata={"inventory": status},
            )
        asset_summary = {
            "data_id": self._inventory_data_id,
            "enterprise_count": len(records),
            "inventory_period": status.get("inventory_period"),
        }
        if list_sectors:
            sector_counts: dict[str, int] = {}
            district_counts: dict[str, int] = {}
            for record in records:
                for name in record.get("inventory_sectors") or []:
                    sector_counts[name] = sector_counts.get(name, 0) + 1
                if district := record.get("district"):
                    district_counts[district] = district_counts.get(district, 0) + 1
            sectors_data = dict(sorted(sector_counts.items(), key=lambda item: -item[1]))
            return self._payload(
                status="success",
                data={"sectors": sectors_data, "districts": district_counts, **asset_summary},
                summary=(
                    f"清单共 {len(records)} 家有坐标企业，覆盖 {len(sectors_data)} 个排放扇区；"
                    "sectors 参数请使用扇区名称（如 堆场、工业涂装）。"
                ),
                metadata={"tool_name": self.name, "inventory": asset_summary},
            )

        pollutant = pollutant if pollutant in POLLUTANT_LABELS else None
        top_n = max(1, min(int(top_n or 20), 100))
        matched = []
        for record in records:
            if not self._matches(record, enterprise_names, unified_social_credit_codes, districts, sectors):
                continue
            if lat is not None and lon is not None:
                distance = _haversine_km(
                    float(lat), float(lon), float(record["latitude"]), float(record["longitude"])
                )
                if distance > (radius_km or 5.0):
                    continue
                record_distance = round(distance, 3)
            else:
                record_distance = None
            matched.append((record, record_distance))

        def emission_value(record: dict[str, Any]) -> float:
            emissions = record.get("inventory_emissions") or {}
            if pollutant:
                return float(emissions.get(pollutant) or 0.0)
            return sum(float(emissions.get(key) or 0.0) for key in DEFAULT_EMISSION_KEYS)

        if min_emission_tonnes is not None:
            matched = [item for item in matched if emission_value(item[0]) >= float(min_emission_tonnes)]
        matched.sort(key=lambda item: emission_value(item[0]), reverse=True)
        total_matched = len(matched)
        matched = matched[:top_n]

        data = [self._enterprise_payload(record, distance) for record, distance in matched]
        filter_desc = self._describe_filters(
            enterprise_names, unified_social_credit_codes, districts, sectors, lat, lon, radius_km,
            pollutant, min_emission_tonnes,
        )
        summary = (
            f"匹配 {total_matched} 家清单企业"
            + (f"，按{POLLUTANT_LABELS[pollutant]}年排放量降序" if pollutant else "，按主要污染物年排放量合计降序")
            + (f"，返回前 {len(data)} 家" if total_matched > len(data) else "")
            + (f"（{filter_desc}）" if filter_desc else "")
            + "。排放量为清单年度值（吨），许可证信息可用 execute_postgres_sql_query 查 permit_licenses 复核。"
        )
        return self._payload(
            status="success" if data else "empty",
            data=data,
            summary=summary,
            metadata={
                "tool_name": self.name,
                "matched_count": total_matched,
                "returned_count": len(data),
                "pollutant": pollutant,
                "filters": filter_desc or None,
                "inventory": asset_summary,
            },
        )

    def _matches(
        self,
        record: dict[str, Any],
        enterprise_names: list[str] | None,
        credit_codes: list[str] | None,
        districts: list[str] | None,
        sectors: list[str] | None,
    ) -> bool:
        if credit_codes:
            code = str(record.get("unified_social_credit_code") or "").upper()
            wanted = {str(item).strip().upper() for item in credit_codes if str(item).strip()}
            if code not in wanted:
                return False
        if enterprise_names:
            name = str(record.get("enterprise_name") or "")
            if not any(keyword and keyword in name for keyword in enterprise_names):
                return False
        if districts:
            district = str(record.get("district") or "")
            if not any(keyword and keyword in district for keyword in districts):
                return False
        if sectors:
            record_sectors = set(record.get("inventory_sectors") or [])
            if not any(sector in record_sectors for sector in sectors):
                return False
        return True

    @staticmethod
    def _describe_filters(
        enterprise_names: list[str] | None,
        credit_codes: list[str] | None,
        districts: list[str] | None,
        sectors: list[str] | None,
        lat: float | None,
        lon: float | None,
        radius_km: float,
        pollutant: str | None,
        min_emission_tonnes: float | None,
    ) -> str:
        parts: list[str] = []
        if enterprise_names:
            parts.append(f"企业名称含 {'、'.join(enterprise_names)}")
        if credit_codes:
            parts.append(f"信用代码 {'、'.join(credit_codes)}")
        if districts:
            parts.append(f"区县含 {'、'.join(districts)}")
        if sectors:
            parts.append(f"扇区 {'、'.join(sectors)}")
        if lat is not None and lon is not None:
            parts.append(f"周边 {radius_km}km")
        if min_emission_tonnes is not None:
            label = POLLUTANT_LABELS.get(pollutant or "", "主要污染物合计")
            parts.append(f"{label}年排放≥{min_emission_tonnes}吨")
        return "，".join(parts)

    @staticmethod
    def _enterprise_payload(record: dict[str, Any], distance_km: float | None) -> dict[str, Any]:
        payload = {
            "enterprise_name": record.get("enterprise_name"),
            "unified_social_credit_code": record.get("unified_social_credit_code"),
            "district": record.get("district"),
            "production_site_address": record.get("production_site_address"),
            "longitude": record.get("longitude"),
            "latitude": record.get("latitude"),
            "coordinate_quality": record.get("coordinate_quality"),
            "industry_category": record.get("industry_category"),
            "inventory_sectors": record.get("inventory_sectors"),
            "inventory_period": record.get("inventory_period"),
            "annual_emissions_tonnes": _compact_emissions(record.get("inventory_emissions")),
            "data_sources": record.get("data_sources"),
        }
        if distance_km is not None:
            payload["distance_km"] = distance_km
        return payload

    def _load_records(self) -> tuple[list[dict[str, Any]] | None, dict[str, Any]]:
        if self._records is not None:
            return self._records, {
                "status": "available",
                "data_id": self._inventory_data_id,
                "record_count": len(self._records),
            }
        try:
            payload = self._registry.load_dataset(self._inventory_data_id)
            entry = self._registry.get_metadata(self._inventory_data_id)
        except (KeyError, OSError, ValueError) as exc:
            return None, {
                "status": "unavailable",
                "data_id": self._inventory_data_id,
                "reason": str(exc),
            }
        self._records = [
            record
            for record in payload
            if isinstance(record, dict)
            and record.get("longitude") is not None
            and record.get("latitude") is not None
        ]
        status = {
            "status": "available",
            "data_id": self._inventory_data_id,
            "record_count": len(self._records),
            "inventory_period": (entry.metadata or {}).get("inventory_period") if entry else None,
        }
        return self._records, status

    @staticmethod
    def _payload(
        *,
        status: str,
        data: Any,
        summary: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": status,
            "success": status in {"success", "empty"},
            "data": data,
            "metadata": metadata,
            "summary": summary,
        }

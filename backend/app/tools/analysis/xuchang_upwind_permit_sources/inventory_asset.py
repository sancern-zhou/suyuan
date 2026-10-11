"""Register the Xuchang enterprise emission inventory for spatial screening."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.data_registry import DataRegistryEntry, DataRegistryService, data_registry
from app.utils.path_config import format_agent_path, resolve_agent_path

XUCHANG_INVENTORY_DATA_ID = "pollution_source_asset:v1:xuchang_emission_inventory_enterprises"
EMISSION_FIELD_MAPPING = {
    "final_emis_so2": "emission_so2",
    "final_emis_nox": "emission_nox",
    "final_emis_co": "emission_co",
    "final_emis_voc": "emission_vocs",
    "final_emis_nh3": "emission_nh3",
    "final_emis_tsp": "emission_tsp",
    "final_emis_pm10": "emission_pm10",
    "final_emis_pm25": "emission_pm25",
    "final_emis_bc": "emission_bc",
    "final_emis_oc": "emission_oc",
    "final_emis_co2": "emission_co2",
    "final_emis_ch4": "emission_ch4",
    "final_emis_n2o": "emission_n2o",
    "final_emis_hfcs": "emission_hfcs",
}


@dataclass(frozen=True)
class XuchangInventoryRegistrationResult:
    data_id: str
    source_record_count: int
    enterprise_count: int
    geocoded_enterprise_count: int
    unlocated_enterprise_count: int
    entry: DataRegistryEntry


def register_xuchang_emission_inventory(
    excel_path: str | Path,
    *,
    inventory_period: str = "unknown",
    registry: DataRegistryService = data_registry,
    data_id: str = XUCHANG_INVENTORY_DATA_ID,
) -> XuchangInventoryRegistrationResult:
    """Normalize all inventory sheets into one geocoded enterprise asset."""
    path = resolve_agent_path(excel_path)
    sheets = pd.read_excel(path, sheet_name=None, dtype=object)
    enterprises: dict[str, dict[str, Any]] = {}
    source_record_count = 0

    for sheet_name, dataframe in sheets.items():
        required = {"ud_ID", "company_name", "credit_code"}
        if not required.issubset(dataframe.columns):
            continue
        for _, row in dataframe.iterrows():
            source_record_id = _source_record_id(row.get("ud_ID"))
            if source_record_id is None:
                continue
            source_record_count += 1
            credit_code = _text(row.get("credit_code")).upper()
            enterprise_name = _text(row.get("company_name"))
            if not credit_code and not enterprise_name:
                continue
            entity_key = credit_code or f"name:{enterprise_name}"
            enterprise = enterprises.setdefault(
                entity_key,
                _new_enterprise(
                    entity_key=entity_key,
                    credit_code=credit_code,
                    enterprise_name=enterprise_name,
                    inventory_period=inventory_period,
                ),
            )
            enterprise["source_record_count"] += 1
            enterprise["source_record_ids"].append(source_record_id)
            enterprise["inventory_sectors"].add(sheet_name)
            _prefer_text(enterprise, "enterprise_name", enterprise_name)
            _prefer_text(enterprise, "district", _text(row.get("district")))
            _prefer_text(enterprise, "production_site_address", _text(row.get("permit_address")))
            for value in (row.get("label_name"), row.get("big_name")):
                if text := _text(value):
                    enterprise["industry_categories"].add(text)
            for source_field, normalized_field in EMISSION_FIELD_MAPPING.items():
                value = _number(row.get(source_field))
                if value is not None:
                    enterprise["inventory_emissions"][normalized_field] += value
            _select_coordinate(enterprise, row)

    records = []
    for enterprise in enterprises.values():
        if enterprise["longitude"] is None or enterprise["latitude"] is None:
            continue
        enterprise["inventory_sectors"] = sorted(enterprise["inventory_sectors"])
        enterprise["industry_categories"] = sorted(enterprise["industry_categories"])
        enterprise["industry_category"] = "、".join(enterprise["industry_categories"])
        enterprise["source_record_ids"] = sorted(set(enterprise["source_record_ids"]))
        enterprise["inventory_emissions"] = {
            key: round(value, 9)
            for key, value in enterprise["inventory_emissions"].items()
        }
        enterprise.pop("_coordinate_rank", None)
        records.append(enterprise)
    records.sort(key=lambda item: (item["district"], item["enterprise_name"], item["source_id"]))

    entry = registry.register_dataset(
        "pollution_source_asset",
        "v1",
        records,
        data_id=data_id,
        sample_size=50,
        metadata={
            "name": "许昌市企业排放源清单",
            "description": "许昌站点告警上风向企业筛选使用的企业级排放清单空间资产。",
            "source": format_agent_path(path),
            "source_sha256": _sha256(path),
            "inventory_period": inventory_period,
            "sheet_count": len(sheets),
            "source_record_count": source_record_count,
            "enterprise_count": len(enterprises),
            "geocoded_enterprise_count": len(records),
            "unlocated_enterprise_count": len(enterprises) - len(records),
            "asset_profile": "map_layer_source.pollution_sources",
            "asset_type": "map_layer_source",
            "business_entity": "pollution_source_enterprise",
            "domain": "emission_inventory",
            "project_id": "xuchang",
            "environment": "prod",
            "emission_fields": list(EMISSION_FIELD_MAPPING.values()),
            "map_capabilities": {
                "geometry": "point",
                "lon_field": "longitude",
                "lat_field": "latitude",
                "crs": "EPSG:4326",
            },
        },
    )
    return XuchangInventoryRegistrationResult(
        data_id=entry.data_id,
        source_record_count=source_record_count,
        enterprise_count=len(enterprises),
        geocoded_enterprise_count=len(records),
        unlocated_enterprise_count=len(enterprises) - len(records),
        entry=entry,
    )


def _new_enterprise(
    *, entity_key: str, credit_code: str, enterprise_name: str, inventory_period: str
) -> dict[str, Any]:
    return {
        "source_id": f"xuchang_inventory:{entity_key}",
        "unified_social_credit_code": credit_code or None,
        "enterprise_name": enterprise_name,
        "district": "",
        "production_site_address": "",
        "longitude": None,
        "latitude": None,
        "coordinate_source": None,
        "coordinate_crs": "EPSG:4326",
        "source_coordinate_crs": None,
        "coordinate_quality": None,
        "inventory_period": inventory_period,
        "inventory_sectors": set(),
        "industry_categories": set(),
        "inventory_emissions": {
            normalized_field: 0.0 for normalized_field in EMISSION_FIELD_MAPPING.values()
        },
        "source_record_count": 0,
        "source_record_ids": [],
        "data_sources": ["emission_inventory"],
        "_coordinate_rank": 0,
    }


def _select_coordinate(enterprise: dict[str, Any], row: pd.Series) -> None:
    status = _text(row.get("coordinate_match_status"))
    longitude = _number(row.get("longitude"))
    latitude = _number(row.get("latitude"))
    if not status.startswith("已匹配") or not _valid_coordinate(longitude, latitude):
        return

    source = _text(row.get("coordinate_source"))
    if "许可证编号精确匹配" in source:
        rank, quality = 4, "permit_number_exact"
    elif "信用代码唯一匹配" in source:
        rank, quality = 3, "credit_code_unique"
    elif "POI" in source:
        rank, quality = 2, "amap_poi_unique"
    else:
        rank, quality = 1, "amap_geocode_exact"
    if rank <= enterprise["_coordinate_rank"]:
        return

    source_crs = "GCJ-02" if "GCJ-02" in source else "EPSG:4326"
    normalized_lon, normalized_lat = float(longitude), float(latitude)
    if source_crs == "GCJ-02":
        normalized_lon, normalized_lat = gcj02_to_wgs84(normalized_lon, normalized_lat)
    enterprise.update(
        {
            "longitude": round(normalized_lon, 6),
            "latitude": round(normalized_lat, 6),
            "coordinate_source": source,
            "source_coordinate_crs": source_crs,
            "coordinate_quality": quality,
            "_coordinate_rank": rank,
        }
    )


def gcj02_to_wgs84(longitude: float, latitude: float) -> tuple[float, float]:
    """Convert a mainland China GCJ-02 point to an approximate WGS84 point."""
    if not (72.004 <= longitude <= 137.8347 and 0.8293 <= latitude <= 55.8271):
        return longitude, latitude
    delta_lon, delta_lat = _gcj_delta(longitude, latitude)
    return longitude - delta_lon, latitude - delta_lat


def _gcj_delta(longitude: float, latitude: float) -> tuple[float, float]:
    x, y = longitude - 105.0, latitude - 35.0
    lat = (
        -100.0
        + 2.0 * x
        + 3.0 * y
        + 0.2 * y * y
        + 0.1 * x * y
        + 0.2 * math.sqrt(abs(x))
        + (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        + (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
        + (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    )
    lon = (
        300.0
        + x
        + 2.0 * y
        + 0.1 * x * x
        + 0.1 * x * y
        + 0.1 * math.sqrt(abs(x))
        + (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        + (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
        + (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    )
    eccentricity = 0.006693421622965943
    earth_radius = 6378245.0
    rad_lat = latitude / 180.0 * math.pi
    magic = 1 - eccentricity * math.sin(rad_lat) ** 2
    sqrt_magic = math.sqrt(magic)
    delta_lat = lat * 180.0 / ((earth_radius * (1 - eccentricity)) / (magic * sqrt_magic) * math.pi)
    delta_lon = lon * 180.0 / (earth_radius / sqrt_magic * math.cos(rad_lat) * math.pi)
    return delta_lon, delta_lat


def _prefer_text(target: dict[str, Any], field: str, value: str) -> None:
    if value and (not target[field] or len(value) < len(target[field])):
        target[field] = value


def _source_record_id(value: Any) -> str | None:
    number = _number(value)
    if number is None:
        return None
    return str(int(number)) if number.is_integer() else str(number)


def _number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _valid_coordinate(longitude: float | None, latitude: float | None) -> bool:
    return longitude is not None and latitude is not None and -180 <= longitude <= 180 and -90 <= latitude <= 90


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "EMISSION_FIELD_MAPPING",
    "XUCHANG_INVENTORY_DATA_ID",
    "XuchangInventoryRegistrationResult",
    "gcj02_to_wgs84",
    "register_xuchang_emission_inventory",
]

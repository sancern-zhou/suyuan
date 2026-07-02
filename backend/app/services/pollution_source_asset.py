from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.data_registry import DataRegistryEntry, DataRegistryService, data_registry


FIELD_MAPPING = {
    "企业名称": "name",
    "所在地市": "city",
    "所在区县": "district",
    "经度": "longitude",
    "纬度": "latitude",
    "污染源类别": "source_type",
    "行业类别": "industry_type",
    "SO2排放量（吨）": "emission_so2",
    "NOx排放量（吨）": "emission_nox",
    "CO排放量（吨）": "emission_co",
    "VOCs排放量（吨）": "emission_vocs",
    "NH3排放量（吨）": "emission_nh3",
    "PM10排放量（吨）": "emission_pm10",
    "PM2.5排放量（吨）": "emission_pm25",
    "BC排放量（吨）": "emission_bc",
    "OC排放量（吨）": "emission_oc",
}

EMISSION_FIELDS = [
    "emission_so2",
    "emission_nox",
    "emission_co",
    "emission_vocs",
    "emission_nh3",
    "emission_pm10",
    "emission_pm25",
    "emission_bc",
    "emission_oc",
]


@dataclass(frozen=True)
class PollutionSourceRegistrationResult:
    data_id: str
    record_count: int
    invalid_coordinate_count: int
    entry: DataRegistryEntry


def register_pollution_source_excel(
    excel_path: str | Path,
    *,
    registry: DataRegistryService = data_registry,
    sheet_name: str = "Sheet1",
    data_id: str = "pollution_source_asset:v1:guangdong_emission_inventory_29a8f794",
) -> PollutionSourceRegistrationResult:
    path = Path(excel_path)
    dataframe = pd.read_excel(path, sheet_name=sheet_name)
    records, invalid_coordinate_count = _normalize_pollution_source_records(dataframe)
    entry = registry.register_dataset(
        "pollution_source_asset",
        "v1",
        records,
        data_id=data_id,
        sample_size=50,
        metadata={
            "name": "广东省污染源排放清单空间点资产",
            "description": "污染源、企业排放源、站点周边污染源分布空间分析和地图点图层数据。",
            "source": str(path),
            "sheet_name": sheet_name,
            "asset_profile": "map_layer_source.pollution_sources",
            "asset_type": "map_layer_source",
            "business_entity": "pollution_source",
            "domain": "emission_inventory",
            "environment": "prod",
            "original_record_count": int(len(dataframe)),
            "valid_record_count": len(records),
            "invalid_coordinate_count": invalid_coordinate_count,
            "field_mapping": FIELD_MAPPING,
            "emission_fields": EMISSION_FIELDS,
            "map_capabilities": {
                "geometry": "point",
                "lon_field": "longitude",
                "lat_field": "latitude",
            },
        },
    )
    return PollutionSourceRegistrationResult(
        data_id=entry.data_id,
        record_count=len(records),
        invalid_coordinate_count=invalid_coordinate_count,
        entry=entry,
    )


def _normalize_pollution_source_records(dataframe: pd.DataFrame) -> tuple[list[dict[str, Any]], int]:
    normalized_records: list[dict[str, Any]] = []
    invalid_coordinate_count = 0
    for index, row in dataframe.iterrows():
        longitude = _to_float(row.get("经度"))
        latitude = _to_float(row.get("纬度"))
        if longitude is None or latitude is None:
            invalid_coordinate_count += 1
            continue

        record = {
            "source_id": f"pollution_source_{len(normalized_records) + 1}",
            "source_row_number": int(index) + 2,
            "name": _to_text(row.get("企业名称")),
            "city": _to_text(row.get("所在地市")),
            "district": _to_text(row.get("所在区县")),
            "longitude": longitude,
            "latitude": latitude,
            "source_type": _to_text(row.get("污染源类别")),
            "industry_type": _to_text(row.get("行业类别")),
        }
        for original_field, normalized_field in FIELD_MAPPING.items():
            if normalized_field in record or not normalized_field.startswith("emission_"):
                continue
            record[normalized_field] = _to_float(row.get(original_field), default=0.0)
        normalized_records.append(record)
    return normalized_records, invalid_coordinate_count


def _to_float(value: Any, default: float | None = None) -> float | None:
    if value is None or pd.isna(value):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed


def _to_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()

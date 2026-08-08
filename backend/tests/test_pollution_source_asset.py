from pathlib import Path

import pandas as pd

from app.services.data_registry import DataRegistryService
from app.services.pollution_source_asset import register_pollution_source_excel
from app.tools.gisctl import asset_resolver


def test_register_pollution_source_excel_creates_mappable_registry_asset(tmp_path):
    excel_path = tmp_path / "sources.xlsx"
    pd.DataFrame(
        [
            {
                "企业名称": "企业A",
                "所在地市": "广州市",
                "所在区县": "天河区",
                "经度": 113.35,
                "纬度": 23.13,
                "污染源类别": "工业企业",
                "行业类别": "涂料制造",
                "SO2排放量（吨）": 1.2,
                "NOx排放量（吨）": 2.3,
                "VOCs排放量（吨）": 3.4,
                "PM10排放量（吨）": 0.5,
                "PM2.5排放量（吨）": 0.2,
            },
            {
                "企业名称": "无坐标企业",
                "所在地市": "广州市",
                "所在区县": "天河区",
                "经度": None,
                "纬度": 23.13,
                "污染源类别": "工业企业",
                "行业类别": "其他",
            },
        ]
    ).to_excel(excel_path, sheet_name="Sheet1", index=False)

    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    result = register_pollution_source_excel(
        excel_path,
        registry=registry,
        data_id="pollution_source_asset:v1:fixture_sources",
    )

    assert result.data_id == "pollution_source_asset:v1:fixture_sources"
    assert result.record_count == 1

    entry = registry.get_metadata(result.data_id)
    assert entry is not None
    assert entry.metadata["asset_profile"] == "map_layer_source.pollution_sources"
    assert entry.metadata["business_entity"] == "pollution_source"
    assert entry.metadata["map_capabilities"] == {
        "geometry": "point",
        "lon_field": "longitude",
        "lat_field": "latitude",
    }
    assert entry.metadata["field_mapping"]["企业名称"] == "name"

    records = registry.load_dataset(result.data_id)
    assert records == [
        {
            "source_id": "pollution_source_1",
            "source_row_number": 2,
            "name": "企业A",
            "city": "广州市",
            "district": "天河区",
            "longitude": 113.35,
            "latitude": 23.13,
            "source_type": "工业企业",
            "industry_type": "涂料制造",
            "emission_so2": 1.2,
            "emission_nox": 2.3,
            "emission_co": 0.0,
            "emission_vocs": 3.4,
            "emission_nh3": 0.0,
            "emission_pm10": 0.5,
            "emission_pm25": 0.2,
            "emission_bc": 0.0,
            "emission_oc": 0.0,
        }
    ]


def test_resolve_map_data_asset_can_find_pollution_source_profile(tmp_path, monkeypatch):
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    registry.register_dataset(
        "pollution_source_asset",
        "v1",
        [
            {
                "name": "企业A",
                "longitude": 113.35,
                "latitude": 23.13,
                "source_type": "工业企业",
                "emission_vocs": 3.4,
            }
        ],
        data_id="pollution_source_asset:v1:fixture_sources",
        metadata={
            "asset_profile": "map_layer_source.pollution_sources",
            "asset_type": "map_layer_source",
            "business_entity": "pollution_source",
            "domain": "emission_inventory",
            "environment": "prod",
            "map_capabilities": {
                "geometry": "point",
                "lon_field": "longitude",
                "lat_field": "latitude",
            },
        },
    )
    monkeypatch.setattr(asset_resolver, "data_registry", registry)

    result = asset_resolver.resolve_map_data_asset(intent="查询站点周边污染源分布")

    assert result["success"] is True
    assert result["data"]["asset_profile"] == "map_layer_source.pollution_sources"
    assert result["data"]["selected"]["data_id"] == "pollution_source_asset:v1:fixture_sources"
    assert result["data"]["selected"]["longitude_field"] == "longitude"
    assert result["data"]["selected"]["latitude_field"] == "latitude"

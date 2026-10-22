from __future__ import annotations

import pytest

from app.services.data_registry import DataRegistryService
from app.tools.xuchang.emission_inventory.tool import XuchangEmissionInventoryTool


def _register_asset(registry: DataRegistryService) -> None:
    registry.register_dataset(
        "pollution_source_asset",
        "v1",
        [
            {
                "source_id": "xuchang_inventory:A",
                "unified_social_credit_code": "914100000000000001",
                "enterprise_name": "许昌天源生物科技有限公司",
                "district": "禹州市",
                "production_site_address": "禹州市产业集聚区",
                "longitude": 113.53,
                "latitude": 34.15,
                "coordinate_source": "高德地理编码（GCJ-02）",
                "coordinate_crs": "EPSG:4326",
                "coordinate_quality": "amap_geocode_exact",
                "inventory_period": "2024",
                "inventory_sectors": ["医药制造", "泄漏"],
                "industry_categories": ["医药制造业"],
                "industry_category": "医药制造业",
                "inventory_emissions": {
                    "emission_so2": 0.0,
                    "emission_nox": 1.5,
                    "emission_vocs": 10.8,
                    "emission_pm25": 0.0,
                },
                "data_sources": ["emission_inventory"],
            },
            {
                "source_id": "xuchang_inventory:B",
                "unified_social_credit_code": "914100000000000002",
                "enterprise_name": "长葛市恒达热力有限责任公司",
                "district": "长葛市",
                "production_site_address": "长葛市人民路南段2号",
                "longitude": 113.77,
                "latitude": 34.2,
                "coordinate_source": "许昌市排污许可证数据（信用代码唯一匹配）",
                "coordinate_crs": "EPSG:4326",
                "coordinate_quality": "credit_code_unique",
                "inventory_period": "2024",
                "inventory_sectors": ["堆场", "工业锅炉"],
                "industry_categories": ["电力、热力生产和供应业"],
                "industry_category": "电力、热力生产和供应业",
                "inventory_emissions": {
                    "emission_so2": 3.2,
                    "emission_nox": 8.4,
                    "emission_pm25": 1.1,
                },
                "data_sources": ["emission_inventory"],
            },
        ],
        data_id="pollution_source_asset:v1:test_query_inventory",
    )


@pytest.fixture()
def tool(tmp_path) -> XuchangEmissionInventoryTool:
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    _register_asset(registry)
    return XuchangEmissionInventoryTool(
        registry=registry,
        inventory_data_id="pollution_source_asset:v1:test_query_inventory",
    )


async def test_query_by_enterprise_name_keyword(tool):
    result = await tool.execute(enterprise_names=["天源生物"])
    assert result["status"] == "success"
    assert result["metadata"]["matched_count"] == 1
    record = result["data"][0]
    assert record["enterprise_name"] == "许昌天源生物科技有限公司"
    assert record["annual_emissions_tonnes"]["emission_vocs"] == 10.8
    assert record["inventory_sectors"] == ["医药制造", "泄漏"]


async def test_query_by_district_and_sector(tool):
    result = await tool.execute(districts=["长葛"], sectors=["堆场"])
    assert result["metadata"]["matched_count"] == 1
    assert result["data"][0]["enterprise_name"] == "长葛市恒达热力有限责任公司"


async def test_query_sorted_by_pollutant_with_threshold(tool):
    result = await tool.execute(pollutant="emission_nox", min_emission_tonnes=2.0)
    names = [item["enterprise_name"] for item in result["data"]]
    assert names == ["长葛市恒达热力有限责任公司"]
    assert result["metadata"]["pollutant"] == "emission_nox"


async def test_query_nearby_radius_filters_by_distance(tool):
    in_radius = await tool.execute(lat=34.15, lon=113.53, radius_km=5)
    assert in_radius["metadata"]["matched_count"] == 1
    assert in_radius["data"][0]["distance_km"] == 0.0

    far = await tool.execute(lat=34.15, lon=113.53, radius_km=5, districts=["长葛"])
    assert far["status"] == "empty"
    assert far["success"] is True


async def test_list_sectors_returns_statistics(tool):
    result = await tool.execute(list_sectors=True)
    sectors = result["data"]["sectors"]
    assert sectors["堆场"] == 1
    assert sectors["工业锅炉"] == 1
    assert result["data"]["enterprise_count"] == 2


async def test_unavailable_asset_reports_status(tmp_path):
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    tool = XuchangEmissionInventoryTool(
        registry=registry,
        inventory_data_id="pollution_source_asset:v1:missing",
    )
    result = await tool.execute(enterprise_names=[" anything "])
    assert result["status"] == "unavailable"
    assert result["success"] is False
    assert "inventory" in result["metadata"]

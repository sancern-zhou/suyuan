from __future__ import annotations

import pandas as pd

from app.services.data_registry import DataRegistryService
from app.tools.analysis.xuchang_upwind_permit_sources.inventory_asset import (
    XUCHANG_INVENTORY_DATA_ID,
    gcj02_to_wgs84,
    register_xuchang_emission_inventory,
)


def test_registers_all_sheets_and_aggregates_enterprise_emissions(tmp_path):
    source_path = tmp_path / "xuchang-inventory.xlsx"
    shared = {
        "province": "河南省",
        "city": "许昌市",
        "district": "魏都区",
        "company_name": "测试企业",
        "credit_code": "91411000123456789X",
        "big_name": "化学原料和化学制品制造业",
        "label_name": "工业涂装",
        "permit_address": "测试地址",
        "longitude": 113.85,
        "latitude": 34.08,
        "coordinate_source": "高德地理编码（GCJ-02）",
        "coordinate_match_status": "已匹配：高德地理编码",
    }
    with pd.ExcelWriter(source_path) as writer:
        pd.DataFrame([
            {**shared, "ud_ID": 1, "final_emis_voc": 2.5, "final_emis_nox": 1.0},
            {
                **shared,
                "ud_ID": 2,
                "company_name": "无坐标企业",
                "credit_code": "914110009999999999",
                "longitude": None,
                "latitude": None,
                "coordinate_source": "高德地理编码（结果待核验）",
                "coordinate_match_status": "待核验：高德区县精度结果",
                "final_emis_voc": 5.0,
            },
        ]).to_excel(writer, sheet_name="工业涂装", index=False)
        pd.DataFrame([
            {**shared, "ud_ID": 3, "label_name": "工业锅炉", "final_emis_nox": 4.0},
        ]).to_excel(writer, sheet_name="工业锅炉", index=False)

    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    result = register_xuchang_emission_inventory(
        source_path,
        inventory_period="2025",
        registry=registry,
    )

    assert result.data_id == XUCHANG_INVENTORY_DATA_ID
    assert result.source_record_count == 3
    assert result.enterprise_count == 2
    assert result.geocoded_enterprise_count == 1
    assert result.unlocated_enterprise_count == 1
    records = registry.load_dataset(result.data_id)
    assert len(records) == 1
    assert records[0]["source_record_count"] == 2
    assert records[0]["inventory_emissions"]["emission_vocs"] == 2.5
    assert records[0]["inventory_emissions"]["emission_nox"] == 5.0
    assert records[0]["inventory_sectors"] == ["工业涂装", "工业锅炉"]
    assert records[0]["coordinate_crs"] == "EPSG:4326"
    assert records[0]["source_coordinate_crs"] == "GCJ-02"
    assert records[0]["longitude"] != 113.85
    assert result.entry.metadata["inventory_period"] == "2025"


def test_gcj_conversion_leaves_coordinates_outside_china_unchanged():
    assert gcj02_to_wgs84(-0.1276, 51.5072) == (-0.1276, 51.5072)

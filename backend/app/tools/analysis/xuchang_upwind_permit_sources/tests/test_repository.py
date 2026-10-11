from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.fetchers.emission.permit_license_crawler.models import (
    PermitLicense,
    PermitPollutionDetail,
)
from app.tools.analysis.xuchang_upwind_permit_sources import repository as repository_module
from app.tools.analysis.xuchang_upwind_permit_sources.repository import (
    XuchangUpwindPermitRepository,
)


def test_permit_license_maps_geocoding_columns():
    columns = PermitLicense.__table__.columns

    assert columns["longitude"].type.precision == 10
    assert columns["longitude"].type.scale == 6
    assert columns["latitude"].type.precision == 9
    assert columns["latitude"].type.scale == 6
    assert columns["coordinate_source"].type.length == 64
    assert columns["coordinate_crs"].type.length == 32
    assert "coordinate_fetched_at" in columns
    assert "permit_original_path" in columns


@pytest.mark.asyncio
async def test_load_candidates_uses_real_permit_model(tmp_path, monkeypatch):
    database_path = tmp_path / "permits.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    tables = [PermitLicense.__table__, PermitPollutionDetail.__table__]
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: PermitLicense.metadata.create_all(
                sync_connection,
                tables=tables,
            )
        )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            PermitLicense(
                id="permit-1",
                source_data_id="source-1",
                province_name="河南省",
                city_name="许昌市",
                permit_number="permit-1",
                unified_social_credit_code="91411000123456789X",
                enterprise_name="测试企业",
                production_site_address="测试地址",
                longitude=113.85,
                latitude=34.08,
                coordinate_source="permit_platform_detail_html",
                coordinate_fetched_at=datetime(2026, 8, 1),
                coordinate_crs="EPSG:4326",
                industry_category="化工",
                current_status="valid",
                detail_url="https://example.test/permit-1",
                list_page_no=1,
            )
        )
        session.add(
            PermitPollutionDetail(
                license_id="permit-1",
                main_pollutant_categories="大气污染物",
                air_pollutant_types="颗粒物",
                source_html_sha256="a" * 64,
            )
        )
        await session.commit()

    monkeypatch.setattr(repository_module, "async_session", factory)
    candidates = await XuchangUpwindPermitRepository().load_candidates(
        receptor_lat=34.08,
        receptor_lon=113.85,
        radius_km=10,
    )

    assert candidates == [
        {
            "license_id": "permit-1",
            "permit_number": "permit-1",
            "permit_numbers": ["permit-1"],
            "unified_social_credit_code": "91411000123456789X",
            "enterprise_name": "测试企业",
            "industry_category": "化工",
            "production_site_address": "测试地址",
            "latitude": 34.08,
            "longitude": 113.85,
            "coordinate_source": "permit_platform_detail_html",
            "coordinate_crs": "EPSG:4326",
            "permit_status": "valid",
            "permit_pollutants": "颗粒物",
            "main_pollutant_categories": "大气污染物",
            "inventory_emissions": None,
            "inventory_period": None,
            "inventory_sectors": [],
            "data_sources": ["permit_license"],
        }
    ]
    await engine.dispose()


@pytest.mark.asyncio
async def test_load_candidates_merges_registered_inventory_by_credit_code(tmp_path, monkeypatch):
    from app.services.data_registry import DataRegistryService
    from app.tools.analysis.xuchang_upwind_permit_sources.inventory_asset import (
        XUCHANG_INVENTORY_DATA_ID,
    )

    database_path = tmp_path / "permits.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    tables = [PermitLicense.__table__, PermitPollutionDetail.__table__]
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: PermitLicense.metadata.create_all(
                sync_connection,
                tables=tables,
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            PermitLicense(
                id="permit-merged",
                source_data_id="source-merged",
                province_name="河南省",
                city_name="许昌市",
                permit_number="permit-merged",
                unified_social_credit_code="91411000123456789X",
                enterprise_name="许可证企业名称",
                production_site_address="许可证地址",
                longitude=113.85,
                latitude=34.08,
                coordinate_crs="EPSG:4326",
                industry_category="化工",
                current_status="valid",
                detail_url="https://example.test/permit-merged",
                list_page_no=1,
            )
        )
        await session.commit()

    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    registry.register_dataset(
        "pollution_source_asset",
        "v1",
        [{
            "source_id": "inventory-1",
            "unified_social_credit_code": "91411000123456789X",
            "enterprise_name": "清单企业名称",
            "industry_category": "工业涂装",
            "production_site_address": "清单地址",
            "longitude": 113.851,
            "latitude": 34.081,
            "coordinate_crs": "EPSG:4326",
            "inventory_period": "2025",
            "inventory_sectors": ["工业涂装"],
            "inventory_emissions": {"emission_vocs": 12.5, "emission_nox": 2.0},
        }],
        data_id=XUCHANG_INVENTORY_DATA_ID,
        metadata={"inventory_period": "2025"},
    )
    monkeypatch.setattr(repository_module, "async_session", factory)
    repository = XuchangUpwindPermitRepository(registry=registry)

    candidates = await repository.load_candidates(
        receptor_lat=34.08,
        receptor_lon=113.85,
        radius_km=10,
        include_emission_inventory=True,
    )

    assert len(candidates) == 1
    assert candidates[0]["enterprise_name"] == "许可证企业名称"
    assert candidates[0]["data_sources"] == ["emission_inventory", "permit_license"]
    assert candidates[0]["inventory_emissions"]["emission_vocs"] == 12.5
    assert candidates[0]["inventory_period"] == "2025"
    assert repository.inventory_status()["status"] == "available"
    await engine.dispose()

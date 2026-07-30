from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.fetchers.emission.permit_license_crawler.detail_parser import PermitVersion
from app.fetchers.emission.permit_license_crawler.list_parser import PermitListRecord
from app.fetchers.emission.permit_license_crawler.models import (
    PermitCrawlFailure,
    PermitCrawlRun,
    PermitDocument,
    PermitLicense,
    PermitLicenseVersion,
    PermitPollutionDetail,
)
from app.fetchers.emission.permit_license_crawler.repository import PermitRepository


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        PermitCrawlRun.__table__,
        PermitLicense.__table__,
        PermitLicenseVersion.__table__,
        PermitPollutionDetail.__table__,
        PermitDocument.__table__,
        PermitCrawlFailure.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: PermitLicense.metadata.create_all(sync, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


def _record(name: str = "企业甲") -> PermitListRecord:
    return PermitListRecord(
        source_data_id="data-1",
        province_name="河南省",
        city_name="许昌市",
        permit_number="914110000000000001001Q",
        enterprise_name=name,
        industry_category="黑色金属铸造",
        valid_from=date(2026, 1, 1),
        valid_to=date(2030, 12, 31),
        issue_date=date(2026, 1, 1),
        management_category="重点管理",
        detail_url="https://permit.mee.gov.cn/detail?dataid=data-1",
    )


@pytest.mark.asyncio
async def test_upsert_list_record_is_idempotent(session):
    repository = PermitRepository(session)

    first = await repository.upsert_list_record(_record(), list_page_no=1)
    second = await repository.upsert_list_record(_record("企业甲（更新）"), list_page_no=2)
    await session.commit()

    count = await session.scalar(select(func.count()).select_from(PermitLicense))
    assert count == 1
    assert first.id == second.id
    assert second.enterprise_name == "企业甲（更新）"
    assert second.list_page_no == 2


@pytest.mark.asyncio
async def test_detail_save_replaces_versions_and_preserves_field_semantics(session):
    repository = PermitRepository(session)
    license_row = await repository.upsert_list_record(_record(), list_page_no=1)
    versions = [
        PermitVersion(
            permit_number="914110000000000001001Q",
            business_type="重新申请",
            version_no=3,
            completion_date=date(2026, 1, 1),
            valid_from=date(2026, 1, 1),
            valid_to=date(2030, 12, 31),
            source_order=1,
        )
    ]
    pollution = {
        "main_pollutant_categories": "",
        "air_pollutant_types": "颗粒物",
        "air_emission_pattern": None,
        "air_emission_standard": "标准甲",
        "water_pollutant_types": "",
        "water_emission_pattern": "",
        "water_emission_standard": "",
        "emission_rights_info": "/",
    }

    await repository.save_detail(
        license_row,
        versions=versions,
        pollution=pollution,
        current_status="valid",
        latest_business_type="重新申请",
        source_html_sha256="a" * 64,
    )
    await repository.save_detail(
        license_row,
        versions=versions,
        pollution=pollution,
        current_status="valid",
        latest_business_type="重新申请",
        source_html_sha256="b" * 64,
    )
    await session.commit()

    version_count = await session.scalar(select(func.count()).select_from(PermitLicenseVersion))
    detail = await session.scalar(select(PermitPollutionDetail))
    assert version_count == 1
    assert detail.main_pollutant_categories == ""
    assert detail.air_emission_pattern is None
    assert detail.emission_rights_info == "/"
    assert detail.source_html_sha256 == "b" * 64
    assert license_row.detail_status == "complete"


@pytest.mark.asyncio
async def test_pending_claim_skips_completed_license(session):
    repository = PermitRepository(session)
    completed = await repository.upsert_list_record(_record(), list_page_no=1)
    completed.detail_status = "complete"
    completed.documents_status = "complete"
    await repository.upsert_list_record(
        PermitListRecord(**{**_record().__dict__, "source_data_id": "data-2"}),
        list_page_no=1,
    )
    await session.commit()

    pending = await repository.list_pending_licenses(limit=5, resume=True)

    assert [row.source_data_id for row in pending] == ["data-2"]

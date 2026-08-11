import pytest

from app.scenarios.xuchang_transport_escalation.spatial_analysis import (
    TrajectoryEnterpriseScreener,
    identify_transport_corridors,
    identify_transport_corridors_by_height,
)


def _low_path():
    return [
        {
            "batch_index": 0,
            "trajectory_id": 1,
            "age_hours": -age,
            "lat": 34.03,
            "lon": 113.85 - age * 0.01,
            "height": 100,
        }
        for age in range(13)
    ]


class FakePermitRepository:
    async def load_candidates_in_bounds(self, **kwargs):
        assert kwargs["min_lon"] < 113.8 < kwargs["max_lon"]
        return [
            {
                "license_id": "permit-1",
                "permit_number": "P1",
                "enterprise_name": "覆盖企业",
                "industry_category": "工业",
                "production_site_address": "测试地址",
                "latitude": 34.03,
                "longitude": 113.80,
                "coordinate_source": "test",
                "coordinate_crs": "WGS84",
                "permit_status": "valid",
                "permit_pollutants": "氮氧化物",
                "main_pollutant_categories": None,
            }
        ]


class MixedPermitRepository:
    async def load_candidates_in_bounds(self, **kwargs):
        base = (await FakePermitRepository().load_candidates_in_bounds(**kwargs))[0]
        return [
            base,
            {
                **base,
                "license_id": "permit-main-category",
                "enterprise_name": "主类别匹配企业",
                "permit_pollutants": None,
                "main_pollutant_categories": "氮氧化物",
                "longitude": 113.79,
            },
            {
                **base,
                "license_id": "permit-mismatch",
                "enterprise_name": "污染物不匹配企业",
                "permit_pollutants": "二氧化硫",
                "main_pollutant_categories": None,
                "longitude": 113.81,
            },
        ]


def test_corridor_identifies_western_origin():
    corridors = identify_transport_corridors(
        _low_path(),
        receptor_lat=34.03,
        receptor_lon=113.85,
    )

    assert corridors[0]["sector"] == "W"
    assert corridors[0]["trajectory_share"] == 1.0


def test_corridors_keep_start_heights_separate():
    high_path = [
        {**endpoint, "trajectory_id": 2, "height": 500, "lat": 34.03 + index * 0.01}
        for index, endpoint in enumerate(_low_path())
    ]

    result = identify_transport_corridors_by_height(
        _low_path() + high_path,
        heights_m_agl=[100, 500],
        receptor_lat=34.03,
        receptor_lon=113.85,
    )

    assert result["100"][0]["start_height_m_agl"] == 100
    assert result["500"][0]["start_height_m_agl"] == 500


@pytest.mark.asyncio
async def test_nox_enterprise_screening_uses_low_short_path_only():
    screener = TrajectoryEnterpriseScreener(repository=FakePermitRepository())

    result = await screener.screen(_low_path(), pollutant="NOX")

    assert result["coverage"]["max_height_m"] == 300.0
    assert result["coverage"]["max_age_hours"] == 12.0
    assert result["enterprises"][0]["pollutant_relevance"] == "exact_match"
    assert result["enterprises"][0]["screening_label"] == "trajectory_coverage_candidate"


@pytest.mark.asyncio
async def test_enterprise_screening_excludes_permit_pollutant_mismatch():
    screener = TrajectoryEnterpriseScreener(repository=MixedPermitRepository())

    result = await screener.screen(_low_path(), pollutant="NOX")

    assert {item["enterprise_name"] for item in result["enterprises"]} == {
        "覆盖企业",
        "主类别匹配企业",
    }
    assert result["coverage"]["pollutant_mismatch_excluded_count"] == 1
    assert result["coverage"]["pollutant_filter"] == "exclude_permit_pollutant_mismatch"

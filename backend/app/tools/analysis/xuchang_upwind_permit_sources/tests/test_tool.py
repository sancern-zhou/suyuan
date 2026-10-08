from datetime import datetime

import pytest

from app.agent.tool_adapter import _standardize_tool_result
from app.tools.analysis.xuchang_upwind_permit_sources.tool import (
    AnalyzeXuchangUpwindPermitSourcesTool,
)


class FakeRepository:
    async def load_weather(self, **_kwargs):
        class Row:
            def __init__(self, station_id, time, direction):
                self.station_id = station_id
                self.time = time
                self.wind_direction_10m = direction
                self.wind_speed_10m = 2.0
                self.data_quality = "good"

        rows = []
        for hour in range(8, 11):
            time = datetime(2026, 8, 5, hour)
            rows.extend((Row("ZzMTA", time, 315), Row("HFqwM", time, 320), Row("sHlBF", time, 310)))
        return rows, []

    async def load_candidates(self, **_kwargs):
        return [
            {
                "license_id": "permit-1",
                "permit_number": "permit-1",
                "enterprise_name": "Northwest source",
                "industry_category": "化工",
                "production_site_address": "address",
                "latitude": 34.17,
                "longitude": 113.82,
                "coordinate_source": "permit_platform_detail_html",
                "coordinate_crs": "EPSG:4326",
                "permit_status": "valid",
                "permit_pollutants": "颗粒物,非甲烷总烃",
                "main_pollutant_categories": "大气污染物",
            }
        ]


class MissingValidatorRepository(FakeRepository):
    async def load_weather(self, **_kwargs):
        class Row:
            station_id = "ZzMTA"
            time = datetime(2026, 8, 5, 8)
            wind_direction_10m = 315
            wind_speed_10m = 2.0
            data_quality = "good"

        return [Row()], []


@pytest.mark.asyncio
async def test_tool_returns_candidates_only_after_three_strict_hours():
    tool = AnalyzeXuchangUpwindPermitSourcesTool(repository=FakeRepository())

    result = await tool.execute(
        station_name="许昌受体",
        lat=34.07,
        lon=113.92,
        pollutant="PM2.5",
        start_time="2026-08-05 08:00:00",
        end_time="2026-08-05 10:00:00",
        candidate_radius_km=20,
    )

    assert result["success"] is True
    assert result["metadata"]["schema_version"] == "v1.0"
    assert result["data"]["method"]["fallbacks"] == "disabled"
    assert result["data"]["analysis_quality"]["valid_hours"] == 3
    assert result["data"]["candidates"][0]["upwind_matched_hours"] == 3
    assert result["data"]["candidates"][0]["emission_pmf"] is None
    assert result["data"]["scenario_1_output"]["analysis"]["confidence_cap_reason"] == "annual_emission_inventory_unavailable"

    standardized = _standardize_tool_result(
        "analyze_xuchang_upwind_permit_sources",
        result,
        execution_time=0.1,
    )
    assert standardized["data"]["candidates"][0]["enterprise_name"] == "Northwest source"
    assert standardized["data"]["scenario_1_output"]["analysis"]["top_n"][0]["name"] == "Northwest source"


@pytest.mark.asyncio
async def test_tool_produces_a_rapid_output_for_one_valid_hour():
    tool = AnalyzeXuchangUpwindPermitSourcesTool(repository=FakeRepository())

    result = await tool.execute(
        station_name="许昌受体",
        lat=34.07,
        lon=113.92,
        pollutant="PM2.5",
        start_time="2026-08-05 08:00:00",
        end_time="2026-08-05 08:00:00",
    )

    assert result["success"] is True
    assert result["data"]["analysis_quality"]["valid_hours"] == 1
    assert result["data"]["scenario_1_output"]["scenario"] == 1
    assert result["data"]["scenario_1_output"]["meteorology"]["fan_radius_km"] == 5.0


@pytest.mark.asyncio
async def test_tool_reports_missing_validator_observations_instead_of_wind_mismatch():
    tool = AnalyzeXuchangUpwindPermitSourcesTool(
        repository=MissingValidatorRepository()
    )

    result = await tool.execute(
        station_name="许昌受体",
        lat=34.07,
        lon=113.92,
        pollutant="PM2.5",
        start_time="2026-08-05 08:00:00",
        end_time="2026-08-05 08:00:00",
    )

    assert result["status"] == "insufficient_meteorology"
    assert result["summary"] == (
        "事件时段缺少可用的校验气象站风向风速观测，无法完成多站风场一致性校验，"
        "未生成企业候选排序。"
    )
    assert result["data"]["hourly_meteorology"][0]["reason"] == (
        "no_validating_station_wind_available"
    )


def test_pollutant_match_outweighs_a_nearer_unrelated_permit():
    usable_hours = [{
        "time": "2026-08-05T08:00:00+08:00",
        "wind_from_deg": 320,
        "wind_speed_ms": 2.0,
        "sector_half_angle_deg": 30.0,
        "stability": {"stability_class": "D"},
    }]
    candidates = [
        {
            "enterprise_name": "Near unrelated source",
            "industry_category": "其他",
            "latitude": 34.075,
            "longitude": 113.915,
            "permit_pollutants": "废水污染物",
            "main_pollutant_categories": "水污染物",
        },
        {
            "enterprise_name": "Farther particulate source",
            "industry_category": "其他",
            "latitude": 34.08,
            "longitude": 113.91,
            "permit_pollutants": "颗粒物",
            "main_pollutant_categories": "大气污染物",
        },
    ]

    results = AnalyzeXuchangUpwindPermitSourcesTool._score_candidates(
        candidates=candidates,
        usable_hours=usable_hours,
        receptor_lat=34.07,
        receptor_lon=113.92,
        pollutant="PM2.5",
        radius_km=5,
        historical_wind_speed_ms=2,
    )
    results.sort(key=lambda item: item["final_score"], reverse=True)

    assert results[0]["enterprise_name"] == "Farther particulate source"
    assert results[0]["pollutant_relevance_factor"] == 1.0
    assert results[1]["pollutant_relevance_factor"] == 0.1


def test_inventory_emission_evidence_affects_candidate_ranking():
    usable_hours = [{
        "time": "2026-08-05T08:00:00+08:00",
        "wind_from_deg": 320,
        "wind_speed_ms": 2.0,
        "sector_half_angle_deg": 45.0,
        "stability": {"stability_class": "D"},
    }]
    candidates = [
        {
            "enterprise_name": "Low emission",
            "industry_category": "其他",
            "latitude": 34.08,
            "longitude": 113.91,
            "permit_pollutants": "颗粒物",
            "main_pollutant_categories": "大气污染物",
            "inventory_emissions": {"emission_pm25": 0.1},
            "data_sources": ["permit_license", "emission_inventory"],
        },
        {
            "enterprise_name": "High emission",
            "industry_category": "其他",
            "latitude": 34.08,
            "longitude": 113.91,
            "permit_pollutants": None,
            "main_pollutant_categories": None,
            "inventory_emissions": {"emission_pm25": 20.0},
            "data_sources": ["emission_inventory"],
        },
    ]

    results = AnalyzeXuchangUpwindPermitSourcesTool._score_candidates(
        candidates=candidates,
        usable_hours=usable_hours,
        receptor_lat=34.07,
        receptor_lon=113.92,
        pollutant="PM2.5",
        radius_km=5,
        historical_wind_speed_ms=2,
    )
    results.sort(key=lambda item: item["final_score"], reverse=True)

    assert results[0]["enterprise_name"] == "High emission"
    assert results[0]["emission_value_tonnes"] == 20.0
    assert results[0]["emission_norm"] == 1.0
    assert results[0]["inventory_pollutant_relevance"] == "exact_match"


@pytest.mark.asyncio
async def test_tool_rejects_pollutants_outside_the_three_categories():
    tool = AnalyzeXuchangUpwindPermitSourcesTool(repository=FakeRepository())

    result = await tool.execute(
        station_name="许昌受体",
        lat=34.07,
        lon=113.92,
        pollutant="NO2",
        start_time="2026-08-05 08:00:00",
        end_time="2026-08-05 08:00:00",
    )

    assert result["success"] is False
    assert result["error"] == "unsupported_pollutant"

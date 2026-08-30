from datetime import datetime, timedelta
from math import sin
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.scenarios.xuchang_transport_escalation.service import (
    XuchangTransportEscalationService,
    assess_trajectory_quality,
)
from app.tools.analysis.trajectory_source_analysis.trajectory_runner import TrajectoryRunner

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _alert(hour: int, *, event_id: str | None = None, pollutant: str = "PM2.5") -> dict:
    occurred_at = datetime(2026, 8, 5, hour, tzinfo=TZ_SHANGHAI)
    return {
        "event_id": event_id or f"scenario-1-{hour}",
        "occurred_at": occurred_at.isoformat(),
        "city": "许昌市",
        "station_id": "XC001",
        "station_name": "测试站",
        "lat": 34.03,
        "lon": 113.85,
        "target_pollutant": pollutant,
        "observed_indicator": "NO2" if pollutant == "NOX" else pollutant,
        "station_value": 90.0,
        "peer_baseline": 50.0,
        "absolute_delta": 40.0,
        "deviation_ratio": 0.8,
        "data_rate": 1.0,
        "source_screening_status": "success",
    }


def _daily_event(*, pollutant: str = "PM2.5") -> dict:
    return {
        "event_id": f"daily-XC001-{pollutant}",
        "status": "confirmed",
        "occurred_at": "2026-08-06T00:00:00+08:00",
        "target_date": "2026-08-05",
        "city": "许昌市",
        "station_id": "XC001",
        "station_name": "测试站",
        "lat": 34.03,
        "lon": 113.85,
        "target_pollutant": pollutant,
        "observed_indicator": pollutant,
        "daily_value": 91.5,
        "limit": 75.0,
        "source_granularity": "station_day",
        "source_table": "dbo.dat_station_day",
    }


def _trajectory_endpoints(backtrack_hours: int = 48, batch_count: int = 2) -> list[dict]:
    endpoints = []
    for batch_index in range(batch_count):
        for trajectory_id, height in ((1, 100), (2, 500), (3, 1000)):
            for age in range(0, backtrack_hours + 1, 3):
                layer_offset = (trajectory_id - 2) * 0.025
                endpoints.append(
                    {
                        "batch_index": batch_index,
                        "trajectory_id": trajectory_id,
                        "age_hours": -age,
                        "lat": 34.03 + age * 0.004 + 0.08 * sin(age / 8 + layer_offset),
                        "lon": 113.85 - age * 0.012 + 0.07 * sin(age / 6 + trajectory_id),
                        "height": height,
                    }
                )
    return endpoints


class FakeTrajectoryRunner:
    def __init__(self):
        self.calls = []

    async def run_event_trajectories(self, **kwargs):
        hours = [value.hour for value in kwargs["event_times"]]
        self.calls.append(hours)
        endpoints = _trajectory_endpoints(batch_count=len(hours))
        return {
            "success": True,
            "endpoints": endpoints,
            "successful_jobs": [{"job_id": f"noaa-{hour}"} for hour in hours],
            "failed_jobs": [],
        }


class FakeEnterpriseScreener:
    async def screen(self, endpoints, *, pollutant, receptor_lat=None, receptor_lon=None):
        assert endpoints
        assert pollutant == "PM2.5"
        return {
            "enterprises": [
                {
                    "license_id": "permit-1",
                    "permit_number": "permit-number-1",
                    "enterprise_name": "测试企业",
                    "industry_category": "工业",
                    "latitude": 34.08,
                    "longitude": 113.78,
                    "pollutant_relevance": "exact_match",
                    "minimum_path_distance_km": 1.2,
                    "matched_trajectory_count": 2,
                }
            ],
            "coverage": {"status": "available", "matched_count": 1},
        }


class FakeCWTConcentrationLoader:
    def load(self, *, station_id, pollutant, event_hours):
        assert station_id == "XC001"
        assert pollutant == "PM2.5"
        return {hour: 50.0 + index for index, hour in enumerate(event_hours)}


def test_hourly_scenario_1_alert_never_creates_scenario_3_job(tmp_path):
    service = XuchangTransportEscalationService(output_root=tmp_path)

    result = service.ingest_scenario_1_alert(_alert(10))

    assert result == {
        "status": "ignored",
        "reason": "scenario_3_requires_confirmed_station_daily_exceedance",
        "job": None,
    }
    assert service._load_state()["jobs"] == {}


def test_daily_exceedance_creates_one_idempotent_analysis_job(tmp_path):
    service = XuchangTransportEscalationService(output_root=tmp_path)

    first = service.ingest_daily_exceedance(_daily_event())
    duplicate = service.ingest_daily_exceedance(_daily_event())

    assert first["status"] == "requested"
    assert first["job"]["event_type"] == "xuchang.station_daily_source_analysis.requested"
    assert first["job"]["target_date"] == "2026-08-05"
    assert first["job"]["event_hours"] == [
        f"2026-08-05T{hour:02d}:00:00+08:00" for hour in range(24)
    ]
    assert first["job"]["station_hourly"] == []
    assert duplicate["status"] == "duplicate"
    assert duplicate["job"] is None
    assert len(service._load_state()["jobs"]) == 1


def test_event_config_uses_exact_event_hour_and_pollutant_profile():
    runner = TrajectoryRunner.__new__(TrajectoryRunner)
    event_time = datetime(2026, 8, 5, 10, 35, tzinfo=TZ_SHANGHAI)

    pm25 = runner.generate_event_trajectory_configs(
        lat=34.03,
        lon=113.85,
        event_times=[event_time],
        pollutant="PM2.5",
    )[0]
    nox = runner.generate_event_trajectory_configs(
        lat=34.03,
        lon=113.85,
        event_times=[event_time],
        pollutant="NOX",
    )[0]

    assert pm25["start_time"].isoformat() == "2026-08-05T02:00:00+00:00"
    assert pm25["hours"] == 48
    assert pm25["heights"] == [100, 500, 1000]
    assert pm25["generate_plot"] is False
    assert nox["hours"] == 24
    assert nox["heights"] == [100, 300, 500]


def test_quality_gate_requires_complete_trajectory_series():
    endpoints = _trajectory_endpoints()
    result = assess_trajectory_quality(
        {"endpoints": endpoints},
        expected_trajectories=6,
        backtrack_hours=48,
    )

    assert result["status"] == "sufficient"
    assert result["valid_trajectories"] == 6
    assert result["success_rate"] == 1.0


@pytest.mark.asyncio
async def test_pending_job_outputs_diagnosis_enterprises_and_two_maps(tmp_path):
    runner = FakeTrajectoryRunner()
    service = XuchangTransportEscalationService(
        output_root=tmp_path,
        trajectory_runner=runner,
        enterprise_screener=FakeEnterpriseScreener(),
    )
    service.ingest_daily_exceedance(_daily_event())

    results = await service.run_pending()

    assert len(results) == 1
    output = results[0]
    assert output["status"] == "completed"
    assert runner.calls == [list(range(24)), [18, 19, 20, 21, 22, 23]]
    assert output["trajectory_request"]["event_hours"] == [
        f"2026-08-05T{hour:02d}:00:00+08:00" for hour in range(24)
    ]
    assert len(output["trajectory_request"]["control_event_hours"]) == 6
    assert output["primary_corridor_height_m_agl"] == 100
    assert set(output["transport_corridors_by_height"]) == {"100", "500", "1000"}
    assert all(item["start_height_m_agl"] == 100 for item in output["transport_corridors"])
    assert output["trajectory_clustering_readiness"]["status"] == "minimum_sample_reached"
    assert output["cwt"]["status"] == "accumulating_samples"
    assert output["cwt"]["archive_sample_count"] == 30
    assert output["cwt"]["sample_groups"] == {"pollution": 24, "control": 6}
    assert Path(output["cwt"]["archive_path"]).exists()
    assert output["transport_corridors"]
    assert output["enterprise_screening"]["enterprises"][0]["enterprise_name"] == "测试企业"
    assert {item["role"] for item in output["visualizations"]} == {
        "regional_trajectory_corridor_map",
        "local_enterprise_coverage_map",
        "regional_interactive_map",
        "enterprise_interactive_map",
    }
    assert all(Path(item["path"]).exists() for item in output["visualizations"])
    assert output["map_program"]["renderer"] == "amap-compatible"
    assert set(output["map_programs"]) == {"regional", "enterprise"}
    regional_layers = output["map_programs"]["regional"]["state"]["layers"]
    trajectory_layer = next(layer for layer in regional_layers if "trajectory" in layer["id"])
    coordinates = trajectory_layer["data"]["features"][0]["geometry"]["coordinates"]
    assert len(coordinates) > 2
    start, middle, end = coordinates[0], coordinates[len(coordinates) // 2], coordinates[-1]
    cross_product = (middle[0] - start[0]) * (end[1] - start[1]) - (middle[1] - start[1]) * (
        end[0] - start[0]
    )
    assert abs(cross_product) > 1e-5
    assert output["map_programs"]["regional"]["lineage"]["analysis_crs"] == "WGS84"
    assert Path(output["output_path"]).exists()


@pytest.mark.asyncio
async def test_duplicate_daily_event_does_not_run_an_incremental_job(tmp_path):
    runner = FakeTrajectoryRunner()
    service = XuchangTransportEscalationService(
        output_root=tmp_path,
        trajectory_runner=runner,
        enterprise_screener=FakeEnterpriseScreener(),
    )
    service.ingest_daily_exceedance(_daily_event())
    initial = (await service.run_pending())[0]

    duplicate = service.ingest_daily_exceedance(_daily_event())
    incremental = await service.run_pending()

    assert duplicate["status"] == "duplicate"
    assert incremental == []
    assert len(initial["trajectory_request"]["event_hours"]) == 24


@pytest.mark.asyncio
async def test_cwt_archive_calculates_after_thirty_concentration_pairs(tmp_path):
    service = XuchangTransportEscalationService(
        output_root=tmp_path,
        cwt_concentration_loader=FakeCWTConcentrationLoader(),
    )
    start = datetime(2026, 8, 1, tzinfo=TZ_SHANGHAI)
    event_hours = [(start + timedelta(hours=index)).isoformat() for index in range(30)]
    endpoints = _trajectory_endpoints(batch_count=30)
    for endpoint in endpoints:
        endpoint["arrival_time"] = event_hours[endpoint["batch_index"]]
    trajectory_cache = {
        "pollution": {
            "event_hours": event_hours,
            "endpoints": endpoints,
            "concentrations": {},
        },
        "control": {"event_hours": [], "endpoints": [], "concentrations": {}},
    }
    job = {
        "station_id": "XC001",
        "station_name": "测试站",
        "target_pollutant": "PM2.5",
        "heights_m_agl": [100, 500, 1000],
        "backtrack_hours": 48,
    }

    result = await service._update_and_calculate_cwt(job, trajectory_cache)

    assert result["status"] == "completed"
    assert result["concentration_coverage"] == 1.0
    assert result["archive_sample_count"] == 30
    assert set(result["heights"]) == {"100", "500", "1000"}
    assert all(height["cells"] for height in result["heights"].values())

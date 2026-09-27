"""Process boundaries, report contracts, and safe source-screening guards."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.scenarios.xuchang_city_exceedance.candidate_screening import screen_inventory_candidates
from app.scenarios.xuchang_city_exceedance.process import detect_processes
from app.scenarios.xuchang_city_exceedance.qmd_report import write_qmd_report_from_evidence
from app.scenarios.xuchang_transport_escalation.service import XuchangTransportEscalationService
from app.fetchers.xuchang_city_exceedance import XuchangCityExceedanceFetcher
from app.fetchers.xuchang_city_exceedance import _temperature
from app.fetchers.xuchang_transport_analysis import XuchangTransportAnalysisFetcher

TZ = ZoneInfo("Asia/Shanghai")


def _row(station: str, hour: datetime, *, aqi: float = 50, pm25: float = 20,
         pollutant: str | None = "PM2.5", kind: str = "national") -> dict:
    return {"station_id": station, "name": station, "data_time": hour,
            "aqi": aqi, "pm25": pm25, "pm10": 30, "o3": 50,
            "pollutant": pollutant, "lat": 34.0, "lon": 113.8,
            "station_type": kind}


def test_two_hour_aqi_crosses_midnight_without_duplicate_aqi_process():
    first = datetime(2026, 9, 26, 23, tzinfo=TZ)
    rows = [_row("1003A", first, aqi=105, pm25=80),
            _row("1003A", first + timedelta(hours=1), aqi=110, pm25=85)]
    result = detect_processes(rows, [])
    assert len(result) == 1
    assert result[0]["target_pollutant"] == "PM2.5"
    assert result[0]["start_time"] == first.isoformat()
    assert result[0]["end_time"] == (first + timedelta(hours=1)).isoformat()
    assert {item["rule"] for item in result[0]["triggers"]} == {
        "published_hourly_aqi", "pm25_business_high",
    }


def test_missing_primary_preserves_aqi_process_without_inventing_pollutant():
    first = datetime(2026, 9, 26, 23, tzinfo=TZ)
    rows = [_row("1003A", first, aqi=105, pollutant=None),
            _row("1003A", first + timedelta(hours=1), aqi=108, pollutant=None)]
    result = detect_processes(rows, [])
    assert [item["target_pollutant"] for item in result] == ["AQI"]


def test_township_deviation_uses_township_peers_and_requires_coordinates():
    hour = datetime(2026, 9, 27, 8, tzinfo=TZ)
    rows = [_row("town-high", hour, pm25=90, kind="township")]
    rows.extend(_row(f"town-{index}", hour, pm25=20, kind="township") for index in range(3))
    result = detect_processes([], rows)
    assert len(result) == 1
    assert result[0]["station_id"] == "town-high"
    assert result[0]["triggers"][0]["peer_count"] == 3
    rows[0]["lat"] = None
    assert detect_processes([], rows) == []


def test_process_ingestion_is_idempotent_and_uses_only_trigger_hours(tmp_path):
    service = XuchangTransportEscalationService(output_root=tmp_path)
    hours = [datetime(2026, 9, 27, hour, tzinfo=TZ).isoformat() for hour in (7, 8)]
    event = {
        "event_id": "xuchang-city-2026092707-national-1003A-pm25",
        "status": "confirmed", "station_id": "1003A", "station_name": "甲站",
        "station_type": "national", "target_pollutant": "PM2.5",
        "lat": 34.0, "lon": 113.8, "valid_hours": 2,
        "process_window": {"start": hours[0], "last_trigger_hour": hours[-1]},
        "trigger": {"hours": hours},
        "hourly_rows": [{"time": hour, "concentration": 80} for hour in hours],
    }
    first = service.ingest_process_exceedance(event)
    assert first["status"] == "requested"
    assert first["job"]["event_hours"] == hours
    assert first["job"]["event_concentrations"] == dict.fromkeys(hours, 80.0)
    assert first["job"]["completed_event_type"] == "xuchang.city_source_analysis.completed"
    assert service.ingest_process_exceedance(event)["status"] == "duplicate"
    assert len(service._load_state()["jobs"]) == 1


def test_enterprise_candidates_are_only_upwind_field_checks():
    hours = ["2026-09-27T07:00:00+08:00", "2026-09-27T08:00:00+08:00"]
    meteo = [{"time": hour, "wind_direction_10m": 90, "wind_speed_10m_ms": 2}
             for hour in hours]
    records = [{"enterprise_name": "上风向企业", "latitude": 34.0, "longitude": 113.81,
                "industry_category": "建材", "inventory_period": "2024"},
               {"enterprise_name": "下风向企业", "latitude": 34.0, "longitude": 113.79}]
    result = screen_inventory_candidates(
        receptor_lat=34.0, receptor_lon=113.8, pollutant="PM2.5",
        meteorology_rows=meteo, trigger_hours=hours, records=records)
    assert result["candidate_count"] == 1
    assert result["enterprises"][0]["enterprise_name"] == "上风向企业"
    assert "contribution_percent" not in result["enterprises"][0]
    assert screen_inventory_candidates(
        receptor_lat=34.0, receptor_lon=113.8, pollutant="AQI",
        meteorology_rows=meteo, trigger_hours=hours, records=records)["status"] == "not_run"


def test_qmd_report_uses_frozen_brief_and_does_not_list_unscreened_enterprises(tmp_path):
    evidence = {"schema_version": "xuchang_city_source_analysis/v1",
                "analysis_id": "analysis-1", "target_date": "2026-09-27",
                "station_name": "甲站", "target_pollutant": "PM2.5",
                "process_window": {"start": "2026-09-27T07:00:00+08:00"},
                "enterprise_screening": {"status": "not_run", "enterprises": [
                    {"enterprise_name": "不应出现企业"}]}}
    path = tmp_path / "brief.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "report.qmd"
    result = write_qmd_report_from_evidence(str(path), {"conclusion": "需现场核查。"}, str(output))
    report = output.read_text(encoding="utf-8")
    assert result["report_id"] == "analysis-1-report"
    assert "## 六、结论与建议" in report
    assert "不应出现企业" not in report
    assert "需现场核查。" in report


def test_negative_temperature_is_valid_meteorological_evidence():
    assert _temperature(-4.5) == -4.5


@pytest.mark.asyncio
async def test_process_job_writes_brief_map_asset_and_publishes_completed_event(monkeypatch, tmp_path):
    class Runner:
        async def run_event_trajectories(self, **kwargs):
            endpoints = [
                {"batch_index": batch, "trajectory_id": track, "age_hours": -age,
                 "lat": 34 + age * 0.004 + track * 0.001,
                 "lon": 113.8 - age * 0.01 - track * 0.002,
                 "height": height}
                for batch in range(len(kwargs["event_times"]))
                for track, height in ((1, 100), (2, 500), (3, 1000))
                for age in range(0, 49, 3)
            ]
            return {"success": True, "endpoints": endpoints,
                    "successful_jobs": [], "failed_jobs": []}

    class EventSink:
        def __init__(self):
            self.events = []

        async def publish_event(self, event):
            self.events.append(event)

    sink = EventSink()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: sink)
    service = XuchangTransportEscalationService(output_root=tmp_path, trajectory_runner=Runner())
    hours = [datetime(2026, 9, 27, hour, tzinfo=TZ).isoformat() for hour in (7, 8)]
    event = {"event_id": "process-7", "status": "confirmed", "station_id": "1003A",
             "station_name": "甲站", "station_type": "national", "target_pollutant": "AQI",
             "lat": 34.0, "lon": 113.8, "valid_hours": 2,
             "process_window": {"start": hours[0], "last_trigger_hour": hours[1]},
             "trigger": {"hours": hours},
             "station_hourly": [{"data_time": h, "aqi": v} for h, v in zip(hours, (104, 109))],
             "hourly_rows": [{"time": h, "concentration": v} for h, v in zip(hours, (104, 109))]}
    assert service.ingest_process_exceedance(event)["status"] == "requested"
    result = await XuchangTransportAnalysisFetcher(service=service).fetch_and_store()
    assert result["job_count"] == 1
    output = result["jobs"][0]
    assert output["event_type"] == "xuchang.city_source_analysis.completed"
    assert output["status"] == "completed"
    assert output["enterprise_screening"]["status"] == "not_run"
    assert len(sink.events) == 1
    assert sink.events[0].payload["evidence_package_path"] == output["evidence_package_path"]
    from app.utils.path_config import resolve_agent_path
    brief = json.loads(resolve_agent_path(output["evidence_package_path"]).read_text(encoding="utf-8"))
    assert brief["schema_version"] == "xuchang_city_source_analysis/v1"
    assert brief["process_window"]["start"] == hours[0]
    assert any(item["role"] == "regional_trajectory_corridor_map" for item in brief["visualizations"])
    qmd = tmp_path / "report.qmd"
    package = write_qmd_report_from_evidence(output["evidence_package_path"], {}, str(qmd))
    assert len(package["assets"]) == 1
    assert "峰值" in qmd.read_text(encoding="utf-8")
    assert "assets/charts/" in qmd.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_fetcher_queues_hourly_process_without_daily_evaluation(monkeypatch, tmp_path):
    class EventSink:
        def __init__(self):
            self.events = []

        async def publish_event(self, event):
            self.events.append(event)

    sink = EventSink()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: sink)
    service = XuchangTransportEscalationService(output_root=tmp_path)
    now = datetime(2026, 9, 27, 12, 20, tzinfo=TZ)
    fetcher = XuchangCityExceedanceFetcher(
        analysis_service=service, now_factory=lambda: now,
        township_loader=lambda start, end: {"status": "available", "rows": []},
    )
    rows = [_row("1003A", datetime(2026, 9, 27, hour), aqi=108, pm25=80)
            for hour in (10, 11)]
    fetcher.load_national = lambda start, end: rows
    fetcher.load_regional = lambda start, end: []

    async def no_weather(start, end):
        return {"status": "not_available", "rows": [], "source_coverage": {}}

    fetcher.load_meteorology = no_weather
    result = await fetcher.fetch_and_store()
    assert len(result["requested_analyses"]) == 1
    assert [item.event_type for item in sink.events] == [
        "xuchang.city_pollution_episode.confirmed",
        "xuchang.city_source_analysis.requested",
    ]
    job = next(iter(service._load_state()["jobs"].values()))
    assert job["window_policy"] == "last_six_trigger_hours_with_six_preprocess_controls"
    assert "daily_value" not in job

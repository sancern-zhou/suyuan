import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services.pollution_event_monitor import MonitorConfig, PollutionEventMonitorService, TZ_SHANGHAI


class StubEnhancer:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def enhance(self, **kwargs):
        return {
            "schema_version": "pollution_event_auto_analysis/v1",
            "main_pollutant_branch": "pm",
            "target_station": {"station_name": "高值站"},
            "trajectory": {"status": "success", "file": "trajectory_analysis.json"},
            "upwind_enterprises": {"status": "success", "file": "upwind_enterprises.json"},
            "component_analysis": {"status": "success", "branch": "pm", "outputs": []},
            "analysis_errors": [],
        }


@pytest.mark.asyncio
async def test_collect_event_evidence_embeds_auto_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.pollution_event_monitor.PollutionEventEvidenceEnhancer",
        StubEnhancer,
        raising=False,
    )
    service = PollutionEventMonitorService(
        MonitorConfig(cities=["广州"], output_root=tmp_path, auto_enhance_evidence=True)
    )
    run_dir = tmp_path / "广州" / "run"
    run_dir.mkdir(parents=True)
    event = {
        "event_id": "evt_pm",
        "city": "广州",
        "main_pollutant": "PM2_5",
        "time_range": {"start": "2026-07-04 09:00:00", "end": "2026-07-04 10:00:00"},
        "event_type": "sustained_pollution_process",
    }

    monkeypatch.setattr(service, "_fetch_station_hour_data", lambda city, start, end: {"records": [], "source_result": {}})

    async def fake_components(*args, **kwargs):
        return {"files": {}, "data_refs": {"pm25_components_data_id": "pm-components"}}

    service._fetch_component_data = fake_components

    result = await service._collect_event_evidence(
        city="广州",
        event=event,
        run_dir=run_dir,
        city_records=[],
        quality_report={"status": "usable", "issues": []},
        full_start=datetime(2026, 7, 4, 8, tzinfo=TZ_SHANGHAI),
        full_end=datetime(2026, 7, 4, 12, tzinfo=TZ_SHANGHAI),
    )

    assert result["auto_analysis"]["main_pollutant_branch"] == "pm"
    assert Path(result["evidence_pack"]).exists()
    evidence = json.loads(Path(result["evidence_pack"]).read_text(encoding="utf-8"))
    assert evidence["auto_analysis"]["schema_version"] == "pollution_event_auto_analysis/v1"
    assert "auto_analysis" in evidence["schema_features"]
    assert evidence["selection_hint"]["recommendation"] == "recommended"
    assert "active_pollution_event" in evidence["selection_hint"]["reason_codes"]
    assert "auto_analysis_success" in evidence["selection_hint"]["reason_codes"]


def test_build_analysis_selection_prefers_current_non_routine_evidence(tmp_path):
    service = PollutionEventMonitorService(
        MonitorConfig(cities=["广州"], output_root=tmp_path, auto_enhance_evidence=True)
    )

    selection = service._build_run_analysis_selection(
        [
            {
                "event_id": "evt_routine",
                "evidence_pack": "/tmp/routine/evidence_pack.json",
                "selection_hint": {
                    "recommendation": "not_recommended",
                    "priority_score": 0,
                    "reason_codes": ["routine_baseline"],
                },
            },
            {
                "event_id": "evt_ended",
                "evidence_pack": "/tmp/ended/evidence_pack.json",
                "selection_hint": {
                    "recommendation": "recommended",
                    "priority_score": 80,
                    "reason_codes": ["ended_pollution_event", "auto_analysis_success"],
                },
            },
            {
                "event_id": "evt_ongoing",
                "evidence_pack": "/tmp/ongoing/evidence_pack.json",
                "selection_hint": {
                    "recommendation": "recommended",
                    "priority_score": 120,
                    "reason_codes": ["active_pollution_event", "auto_analysis_success"],
                },
            },
        ]
    )

    assert selection["default_evidence_pack"] == "/tmp/ongoing/evidence_pack.json"
    assert [item["event_id"] for item in selection["recommended_evidence_packs"]] == [
        "evt_ongoing",
        "evt_ended",
    ]
    assert selection["skipped_evidence_packs"][0]["event_id"] == "evt_routine"


def test_analysis_request_requires_qmd_report_not_reasoning_markdown(tmp_path):
    service = PollutionEventMonitorService(MonitorConfig(cities=["广州"], output_root=tmp_path))

    request = service._build_analysis_request({
        "city": "广州",
        "event": {
            "event_id": "evt_o3",
            "event_type": "ozone_photochemical_or_transport_process",
            "main_pollutant": "O3_8h",
            "time_range": {"start": "2026-07-05 16:00:00", "end": "2026-07-05 21:00:00"},
            "event_lifecycle": {"status": "updated"},
        },
        "quality_gate": {"status": "caution"},
        "data_files": {"event": "/tmp/event.json"},
        "analysis_contract": {"skill_file": "/tmp/city_pollution_process_analysis.md"},
    })

    assert "report.qmd" in request
    assert "正式溯源分析报告" in request
    assert "reasoning_analysis.md" not in request
    assert "管控" not in request


def test_analysis_request_uses_formal_report_language_without_it_terms(tmp_path):
    service = PollutionEventMonitorService(MonitorConfig(cities=["佛山"], output_root=tmp_path))

    request = service._build_analysis_request({
        "city": "佛山",
        "event": {
            "event_id": "evt_no2",
            "event_type": "significant_pollutant_change",
            "main_pollutant": "NO2",
            "time_range": {"start": "2026-07-06 07:00:00", "end": "2026-07-06 09:00:00"},
            "event_lifecycle": {"status": "updated"},
        },
        "quality_gate": {"status": "caution"},
        "data_files": {"event": "/tmp/event.json"},
        "analysis_contract": {"skill_file": "/tmp/city_pollution_process_analysis.md"},
    })

    forbidden_terms = [
        "质量门禁",
        "quality_gate",
        "selection_hint",
        "auto_analysis",
        "robust_outlier",
    ]
    for term in forbidden_terms:
        assert term not in request
    assert "不要在报告正文输出系统字段名" in request


def test_low_level_rounded_so2_co_constant_streaks_are_low_severity(tmp_path):
    service = PollutionEventMonitorService(MonitorConfig(cities=["广州"], output_root=tmp_path))
    start = datetime(2026, 7, 4, 22, tzinfo=TZ_SHANGHAI)
    so2_values = [6, 6, 6, 6, 6, 7, 6, 6] + [5] * 15 + [9]
    co_values = [0.5, 0.5, 0.5, 0.5, 0.5, 0.6] + [0.5] * 17 + [0.7]
    records = []
    for index in range(24):
        records.append({
            "time": (start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
            "AQI": 80,
            "PM2_5": 30,
            "PM10": 55,
            "O3_8h": 120,
            "NO2": 22,
            "SO2": so2_values[index],
            "CO": co_values[index],
        })

    report = service._quality_report(
        "广州",
        records,
        start,
        start + timedelta(hours=23),
    )

    constant_issues = {
        issue["pollutant"]: issue
        for issue in report["issues"]
        if issue.get("issue_type") == "long_constant_value"
    }
    assert constant_issues["SO2"]["severity"] == "low"
    assert constant_issues["CO"]["severity"] == "low"
    assert constant_issues["SO2"]["impact"] == "Low-level rounded data; use as a variability caution, not confirmed stale instrument data."
    assert constant_issues["CO"]["impact"] == "Low-level rounded data; use as a variability caution, not confirmed stale instrument data."


def test_era5_date_window_excludes_current_unavailable_date(tmp_path):
    service = PollutionEventMonitorService(MonitorConfig(cities=["深圳"], output_root=tmp_path))

    start_date, end_date = service._era5_date_window(
        datetime(2026, 7, 5, 1, tzinfo=TZ_SHANGHAI),
        datetime(2026, 7, 6, 0, tzinfo=TZ_SHANGHAI),
        now=datetime(2026, 7, 6, 0, 5, tzinfo=TZ_SHANGHAI),
    )

    assert start_date == "2026-07-05"
    assert end_date == "2026-07-05"

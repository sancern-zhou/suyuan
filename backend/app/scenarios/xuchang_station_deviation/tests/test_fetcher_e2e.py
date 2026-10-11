from datetime import datetime
from pathlib import Path

import pytest

from app.fetchers.xuchang_station_deviation_alert import XuchangStationDeviationAlertFetcher
from app.scenarios.xuchang_station_deviation.episodes import (
    XuchangStationDeviationEpisodeService,
)


class _ScenarioService:
    def __init__(self, output_root: Path):
        self.output_root = output_root

    async def run(self):
        return {
            "target_hour": "2026-08-05T01:00:00+08:00",
            "alerts": [{
                "event_id": "scenario-1-e2e",
                "event_type": "xuchang.station_deviation.alert_created",
                "occurred_at": "2026-08-05T01:00:00+08:00",
                "city": "许昌市",
                "target_pollutant": "PM2.5",
                "station_id": "test-station",
                "station_name": "测试站",
                "lat": 34.07,
                "lon": 113.92,
                "station_value": 100.0,
                "peer_mean": 40.0,
                "deviation_percent": 150.0,
                "threshold": 0.5,
                "available_station_count": 6,
            }],
        }

    def write_scenario_output(self, alert, output):
        path = self.output_root / f"{alert['event_id']}.scenario-1.json"
        path.write_text(str(output), encoding="utf-8")
        return path

    def write_evidence_package(self, alert, evidence):
        path = self.output_root / f"{alert['event_id']}.evidence.json"
        path.write_text(str(evidence), encoding="utf-8")
        return path

    def write_episode_evidence_package(self, *, station_id, occurred_at, alerts):
        timestamp = datetime.fromisoformat(occurred_at)
        path = self.output_root / (
            f"xuchang-station-episode-{timestamp:%Y%m%d%H%M}-{station_id}.evidence.json"
        )
        path.write_text(str(alerts), encoding="utf-8")
        return path


class _AnalysisTool:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "status": "success",
            "scenario_1_output": {"scenario": 1, "analysis": {"confidence": "medium"}},
        }


class _FailedAnalysisTool:
    async def execute(self, **kwargs):
        return {"status": "failed", "error": "permit coordinate mapping missing"}


class _TaskService:
    def __init__(self):
        self.events = []

    async def publish_event(self, event):
        self.events.append(event)


class _EvidenceCollector:
    def __init__(self):
        self.calls = []

    async def collect(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "schema_version": "xuchang_station_deviation_evidence/v3",
            "source_screening": kwargs["source_screening"],
            "air_quality_context": {"status": "success"},
            "observed_meteorology": {"status": "success"},
            "forecast_meteorology": {"status": "success"},
            "computed_indicators": {"calculation_status": "success"},
            "collection": {"status": "complete", "errors": []},
        }


@pytest.mark.asyncio
async def test_trigger_runs_analysis_persists_output_and_publishes_event(tmp_path, monkeypatch):
    task_service = _TaskService()
    analysis_tool = _AnalysisTool()
    evidence_collector = _EvidenceCollector()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: task_service)
    fetcher = XuchangStationDeviationAlertFetcher(
        service=_ScenarioService(tmp_path),
        analysis_tool=analysis_tool,
        episode_service=XuchangStationDeviationEpisodeService(output_root=tmp_path),
        evidence_collector=evidence_collector,
    )

    result = await fetcher.fetch_and_store()

    alert = result["alerts"][0]
    assert not analysis_tool.calls
    assert (tmp_path / "xuchang-station-episode-202608050100-test-station.evidence.json").exists()
    assert alert["scenario_1_episode"]["should_analyze"] is True
    assert evidence_collector.calls[0]["source_screening"]["status"] == "not_run"
    assert len(task_service.events) == 1
    payload = task_service.events[0].payload
    assert payload["station_episode"] is True
    assert payload["evidence_package_path"].endswith("test-station.evidence.json")
    assert payload["station_episode_alerts"][0]["event_id"] == "scenario-1-e2e"
    assert payload["target_pollutant"] == "PM2.5"


@pytest.mark.asyncio
async def test_failed_analysis_does_not_meet_sla_and_still_publishes_alert(tmp_path, monkeypatch):
    task_service = _TaskService()
    evidence_collector = _EvidenceCollector()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: task_service)
    fetcher = XuchangStationDeviationAlertFetcher(
        service=_ScenarioService(tmp_path),
        analysis_tool=_FailedAnalysisTool(),
        episode_service=XuchangStationDeviationEpisodeService(output_root=tmp_path),
        evidence_collector=evidence_collector,
    )

    result = await fetcher.fetch_and_store()

    alert = result["alerts"][0]
    assert "source_screening_status" not in alert
    assert "scenario_1_output" not in alert
    assert len(task_service.events) == 1
    assert task_service.events[0].payload["station_episode"] is True

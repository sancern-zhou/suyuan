import pytest

from app.fetchers.xuchang_transport_analysis import XuchangTransportAnalysisFetcher


class _AnalysisService:
    async def run_pending(self, limit=1):
        return [{
            "event_id": "analysis-1",
            "event_type": "xuchang.station_daily_source_analysis.completed",
            "generated_at": "2026-08-06T02:00:00+08:00",
            "analysis_id": "analysis-1",
            "evidence_package_path": "backend/backend_data_registry/xuchang_transport_analysis/20260805/analysis-1.json",
            "city": "许昌市",
            "target_date": "2026-08-05",
            "target_pollutant": "PM2.5",
            "station_id": "XC001",
            "station_name": "测试站",
            "status": "completed",
            "transport_diagnosis": {"classification": "mixed"},
        }]


class _TaskService:
    def __init__(self):
        self.events = []

    async def publish_event(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_completed_analysis_publishes_compact_evidence_event(monkeypatch):
    task_service = _TaskService()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: task_service)
    fetcher = XuchangTransportAnalysisFetcher(service=_AnalysisService())

    await fetcher.fetch_and_store()

    assert len(task_service.events) == 1
    event = task_service.events[0]
    assert event.event_type == "xuchang.station_daily_source_analysis.completed"
    assert event.payload["evidence_package_path"].endswith("analysis-1.json")
    assert "trajectory_endpoints" not in event.payload

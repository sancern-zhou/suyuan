"""Manual weather report runs build current evidence before event dispatch."""

import asyncio

from app.fetchers import xuchang_weather_situation as weather
from app.lifecycle.scheduled import register_project_workflow_handlers
from app.scenarios.xuchang_weather_report.constants import EVENT_TYPE
from app.scheduled_tasks.event_builders import get_manual_event_builder


def test_manual_weather_builder_creates_fresh_matching_events(monkeypatch):
    requested_dates = []

    def fake_package(start_date):
        requested_dates.append(start_date)
        return {
            "start_date": start_date.isoformat(),
            "manifest_path": "backend/data/weather/manifest.json",
        }

    monkeypatch.setattr(weather, "write_evidence_package", fake_package)

    first = asyncio.run(weather.build_weather_evidence_event())
    second = asyncio.run(weather.build_weather_evidence_event())

    assert len(requested_dates) == 2
    assert all(day == weather.datetime.now(weather.TZ).date() for day in requested_dates)
    assert first.event_type == second.event_type == EVENT_TYPE
    assert first.event_id != second.event_id
    assert first.attributes["city"] == "许昌市"
    assert first.payload["evidence_package_path"] == "backend/data/weather/manifest.json"


def test_xuchang_startup_registers_weather_manual_builder():
    register_project_workflow_handlers("xuchang")
    assert get_manual_event_builder(EVENT_TYPE) is weather.build_weather_evidence_event

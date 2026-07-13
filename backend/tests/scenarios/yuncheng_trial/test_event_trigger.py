import pytest

from app.fetchers.yuncheng_trial import yuncheng_trial_fetcher as fetcher_module
from app.fetchers.yuncheng_trial.yuncheng_trial_fetcher import YunchengTrialFetcher


def _rows(*, alert: bool):
    latest_o3 = 135 if alert else 76
    return [
        {"time": "2026-07-13 13:00:00", "O3": 80, "PM2.5": 20, "PM10": 40, "CO": 0.8, "NO2": 20, "AQI": 40},
        {"time": "2026-07-13 14:00:00", "O3": 82, "PM2.5": 21, "PM10": 41, "CO": 0.8, "NO2": 19, "AQI": 41},
        {"time": "2026-07-13 15:00:00", "O3": 83, "PM2.5": 20, "PM10": 39, "CO": 0.7, "NO2": 18, "AQI": 39},
        {"time": "2026-07-13 16:00:00", "O3": latest_o3, "PM2.5": 19, "PM10": 38, "CO": 0.7, "NO2": 18, "AQI": 65},
    ]


@pytest.mark.asyncio
async def test_no_alert_does_not_publish_event(monkeypatch, tmp_path):
    published = []
    monkeypatch.setattr(
        fetcher_module,
        "fetch_target_city_hourly_rows",
        lambda **kwargs: _rows(alert=False),
    )

    async def capture(event):
        published.append(event)

    monkeypatch.setattr(fetcher_module, "publish_task_event", capture, raising=False)

    result = await YunchengTrialFetcher(registry_root=tmp_path).fetch_and_store()

    assert result["has_alert"] is False
    assert published == []


@pytest.mark.asyncio
async def test_ready_alert_publishes_one_event(monkeypatch, tmp_path):
    published = []
    manifest = tmp_path / "tracing_context_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        fetcher_module,
        "fetch_target_city_hourly_rows",
        lambda **kwargs: _rows(alert=True),
    )

    async def fake_collect(**kwargs):
        return manifest

    async def capture(event):
        published.append(event)

    monkeypatch.setattr(fetcher_module, "collect_from_alert_file", fake_collect)
    monkeypatch.setattr(fetcher_module, "publish_task_event", capture, raising=False)

    result = await YunchengTrialFetcher(registry_root=tmp_path).fetch_and_store()

    assert result["has_alert"] is True
    assert len(published) == 1
    event = published[0]
    assert event.event_type == "yuncheng.alert.created"
    assert event.event_id.startswith("yuncheng-")
    assert event.attributes["city"] == "运城市"
    assert event.payload["tracing_context_manifest_path"] == str(manifest)
    assert event.payload["alert_json_path"] == result["alert_path"]

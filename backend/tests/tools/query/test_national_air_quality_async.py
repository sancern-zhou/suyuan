import asyncio
import threading

import pytest

from app.tools.query.query_national_air_quality import tool_wrapper


@pytest.mark.asyncio
async def test_city_query_does_not_block_event_loop(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    class FakeClient:
        def query_city_data(self, **_kwargs):
            started.set()
            release.wait(timeout=2)
            return []

    monkeypatch.setattr(
        "app.tools.query.query_national_air_quality.get_national_air_quality_tool",
        lambda: FakeClient(),
    )
    task = asyncio.create_task(
        tool_wrapper.QueryNationalCityAirQualityTool().execute(
            start_date="2026-10-01",
            end_date="2026-10-02",
        )
    )

    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.001)

    assert started.is_set()
    assert not task.done()
    release.set()
    result = await task
    assert result["success"] is True


@pytest.mark.asyncio
async def test_province_query_does_not_block_event_loop(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    class FakeClient:
        def query_province_data(self, **_kwargs):
            started.set()
            release.wait(timeout=2)
            return []

    monkeypatch.setattr(
        "app.tools.query.query_national_air_quality.get_national_air_quality_tool",
        lambda: FakeClient(),
    )
    task = asyncio.create_task(
        tool_wrapper.QueryNationalProvinceAirQualityTool().execute(
            start_date="2026-10-01",
            end_date="2026-10-02",
        )
    )

    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.001)

    assert started.is_set()
    assert not task.done()
    release.set()
    result = await task
    assert result["success"] is True

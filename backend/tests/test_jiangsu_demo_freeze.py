"""演示冻结（JIANGSU_DEMO_FREEZE_DATE）行为测试。"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import jiangsu_smart_event_routes as routes
from app.fetchers.jiangsu_data_audit_review_event import JiangsuDataAuditReviewEventFetcher
from app.fetchers.jiangsu_fault_work_order_review_event import JiangsuFaultWorkOrderReviewEventFetcher
from app.fetchers.jiangsu_fault_work_order_review_rerun import JiangsuFaultWorkOrderReviewRerunFetcher
from app.fetchers.jiangsu_station_fault_event import JiangsuStationFaultEventFetcher
from app.tools.jiangsu.demo_freeze import (
    demo_freeze_active,
    demo_freeze_date,
    demo_freeze_window,
)

FREEZE_ENV = "JIANGSU_DEMO_FREEZE_DATE"
USER = SimpleNamespace(id="u1", username="tester")


# ------------------------------------------------------------------ config


def test_freeze_disabled_by_default(monkeypatch):
    monkeypatch.delenv(FREEZE_ENV, raising=False)
    assert demo_freeze_date() is None
    assert demo_freeze_active() is False


def test_freeze_invalid_date_is_ignored(monkeypatch):
    monkeypatch.setenv(FREEZE_ENV, "2026-13-99")
    assert demo_freeze_date() is None
    assert demo_freeze_active() is False


def test_freeze_valid_date(monkeypatch):
    monkeypatch.setenv(FREEZE_ENV, "2026-09-10")
    assert demo_freeze_date() == date(2026, 9, 10)
    assert demo_freeze_active() is True


def test_freeze_window_covers_full_local_day(monkeypatch):
    monkeypatch.setenv(FREEZE_ENV, "2026-09-10")
    start, end = demo_freeze_window()
    assert start.tzinfo is not None
    assert (start.year, start.month, start.day, start.hour) == (2026, 9, 10, 0)
    assert (end.year, end.month, end.day) == (2026, 9, 10)
    assert end.hour == 23 and end.minute == 59


# ----------------------------------------------------------------- fetchers

ASYNC_GUARD_CASES = [
    JiangsuStationFaultEventFetcher(),
    JiangsuFaultWorkOrderReviewEventFetcher(),
    JiangsuFaultWorkOrderReviewRerunFetcher(),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher", ASYNC_GUARD_CASES, ids=lambda f: f.name)
async def test_fetchers_skip_when_frozen(fetcher, monkeypatch):
    monkeypatch.setenv(FREEZE_ENV, "2026-09-10")
    result = await fetcher.fetch_and_store()
    assert result == {
        "status": "skipped",
        "reason": "demo_freeze_active",
        "fetcher": fetcher.name,
    }


@pytest.mark.asyncio
async def test_data_audit_fetcher_skips_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setenv(FREEZE_ENV, "2026-09-10")
    fetcher = JiangsuDataAuditReviewEventFetcher(registry_root=tmp_path)
    result = await fetcher.fetch_and_store()
    assert result["status"] == "skipped"
    assert not (tmp_path / "poll_state.json").exists()


# --------------------------------------------------------------------- api


def test_api_default_times_frozen(monkeypatch):
    monkeypatch.setenv(FREEZE_ENV, "2026-09-10")
    start, end = routes._default_times()
    assert start.startswith("2026-09-10T00:00")
    assert end.startswith("2026-09-10T23:59")


def test_api_default_times_rolling_when_not_frozen(monkeypatch):
    monkeypatch.delenv(FREEZE_ENV, raising=False)
    start, end = routes._default_times()
    assert datetime.fromisoformat(end) > datetime.fromisoformat(start)


@pytest.mark.asyncio
async def test_demo_window_endpoint_reports_frozen(monkeypatch):
    monkeypatch.setenv(FREEZE_ENV, "2026-09-10")
    payload = await routes.get_smart_event_demo_window(user=USER)
    assert payload["frozen"] is True
    assert payload["freeze_date"] == "2026-09-10"
    assert payload["window"]["start"].startswith("2026-09-10T00:00")


@pytest.mark.asyncio
async def test_demo_window_endpoint_reports_disabled(monkeypatch):
    monkeypatch.delenv(FREEZE_ENV, raising=False)
    payload = await routes.get_smart_event_demo_window(user=USER)
    assert payload == {"frozen": False, "freeze_date": None, "window": None}


@pytest.mark.asyncio
async def test_sync_rejected_when_frozen(monkeypatch):
    monkeypatch.setenv(FREEZE_ENV, "2026-09-10")
    with pytest.raises(HTTPException) as exc:
        await routes.sync_smart_events(user=USER)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "demo_freeze_active"


@pytest.mark.asyncio
async def test_list_forces_refresh_off_and_frozen_window(monkeypatch):
    captured: dict = {}

    class FakeService:
        async def list_events(self, **kwargs):
            captured.update(kwargs)
            return {"events": []}

    monkeypatch.setenv(FREEZE_ENV, "2026-09-10")
    monkeypatch.setattr(routes, "JiangsuSmartEventService", FakeService)
    await routes.list_smart_events(start_time=None, end_time=None, refresh=True, user=USER)
    assert captured["refresh"] is False
    assert captured["start_time"].startswith("2026-09-10T00:00")
    assert captured["end_time"].startswith("2026-09-10T23:59")


@pytest.mark.asyncio
async def test_bulk_evidence_collect_rejected_when_frozen(monkeypatch):
    monkeypatch.setenv(FREEZE_ENV, "2026-09-10")
    with pytest.raises(HTTPException) as exc:
        await routes.collect_all_smart_event_evidence(user=USER)
    assert exc.value.status_code == 409

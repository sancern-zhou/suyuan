from datetime import date, datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from apscheduler.triggers.cron import CronTrigger

from app.fetchers.tenders.monthly_tender_fetcher import MonthlyTenderInformationFetcher, previous_month
from app.fetchers.base.fetcher_interface import FetcherStatus


@pytest.mark.parametrize("today,start,end", [
    (date(2026,10,1),date(2026,9,1),date(2026,9,30)),
    (date(2026,1,1),date(2025,12,1),date(2025,12,31)),
    (date(2024,3,1),date(2024,2,1),date(2024,2,29)),
    (date(2026,3,1),date(2026,2,1),date(2026,2,28)),
])
def test_closed_previous_month(today,start,end):
    assert previous_month(today) == (start,end)


@pytest.mark.asyncio
async def test_monthly_fetch_uses_previous_month_once():
    runner=AsyncMock(return_value={"candidates":100,"audit_passed":True})
    fetcher=MonthlyTenderInformationFetcher(today_factory=lambda:date(2026,10,1),runner=runner)
    fetcher.enabled=True
    result=await fetcher.fetch_and_store()
    runner.assert_awaited_once_with(date(2026,9,1),date(2026,9,30))
    assert result["audit_passed"]


@pytest.mark.asyncio
async def test_retry_and_failure_are_visible(monkeypatch):
    monkeypatch.setattr("app.fetchers.tenders.monthly_tender_fetcher.asyncio.sleep",AsyncMock())
    runner=AsyncMock(side_effect=RuntimeError("failed"))
    fetcher=MonthlyTenderInformationFetcher(today_factory=lambda:date(2026,10,1),runner=runner)
    fetcher.enabled=True
    await fetcher.run()
    assert runner.await_count == 3
    assert fetcher.status == FetcherStatus.ERROR


def test_next_scheduled_run_is_first_of_month_shanghai():
    fetcher=MonthlyTenderInformationFetcher()
    now=datetime(2026,9,21,tzinfo=ZoneInfo("Asia/Shanghai"))
    trigger=CronTrigger.from_crontab(fetcher.schedule,timezone="Asia/Shanghai")
    assert trigger.get_next_fire_time(None,now)==datetime(2026,10,1,3,30,tzinfo=ZoneInfo("Asia/Shanghai"))


def test_project_registers_monthly_instead_of_daily():
    from app.fetchers import create_scheduler
    scheduler=create_scheduler()
    assert isinstance(scheduler.fetchers["tender_information_fetcher"],MonthlyTenderInformationFetcher)
    job=scheduler.scheduler.get_job("tender_information_fetcher")
    assert str(job.trigger.timezone)=="Asia/Shanghai"

"""Poll the durable event AI queue each minute and collect delayed clues hourly."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from app.fetchers.base.fetcher_interface import DataFetcher
from app.tools.jiangsu.demo_freeze import demo_freeze_active, demo_freeze_skip_result

SYNC_CRON = os.getenv("JIANGSU_SMART_EVENT_AUTOMATION_CRON", "* * * * *")
SYNC_OVERLAP_MINUTES = int(os.getenv("JIANGSU_SMART_EVENT_SYNC_OVERLAP_MINUTES", "5"))


def previous_hour_window(
    now: datetime | None = None,
    *,
    overlap_minutes: int = SYNC_OVERLAP_MINUTES,
) -> tuple[datetime, datetime]:
    """Return the query window covering the last completed clock hour."""
    current = (now or datetime.now().astimezone()).astimezone()
    hour_end = current.replace(minute=0, second=0, microsecond=0)
    hour_start = hour_end - timedelta(hours=1) - timedelta(minutes=overlap_minutes)
    return hour_start, hour_end


class JiangsuSmartEventAlarmSyncFetcher(DataFetcher):
    """Check the queue every minute; persisted configuration controls scan frequency."""

    def __init__(self, *, service: Any | None = None) -> None:
        super().__init__(
            name="jiangsu_smart_event_alarm_sync",
            description="江苏智能事件自动研判队列与延迟线索回扫",
            schedule=os.getenv("JIANGSU_SMART_EVENT_AUTOMATION_CRON", SYNC_CRON),
        )
        self._service = service

    async def fetch_and_store(self) -> dict[str, Any]:
        from app.services.jiangsu_smart_event import JiangsuSmartEventService

        if self._service is None:
            self._service = JiangsuSmartEventService()
        from app.services.jiangsu_smart_event_automation import JiangsuSmartEventAutomation

        if demo_freeze_active():
            # 演示冻结暂停抓新数据，但人工反馈/审核退回的增量研判仍须派发，
            # 它只读取已有证据包，不触发外部数据拉取。
            result = await JiangsuSmartEventAutomation(self._service).dispatch_queue(
                now=datetime.now().astimezone(), human_only=True,
            )
            return {**result, "demo_freeze": True, "fetcher": self.name}
        return await JiangsuSmartEventAutomation(self._service).tick()

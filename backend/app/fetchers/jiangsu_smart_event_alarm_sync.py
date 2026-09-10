"""Hourly alarm sync for the Jiangsu smart-event center.

The event-center page only renders the local event store.  This fetcher
keeps that store fresh in the worker process: once per hour it pulls the
previous completed clock hour of province-control alarms and upserts them
into ``jiangsu_smart_events/store.json``.  Existing events are updated in
place, new events are appended, and the deduplication key stays the stable
``event_id``, so the small overlap at the window border is safe.
New or changed event buckets collect evidence immediately after persistence.
Compliance clues also refresh evidence after merging; AI stays manual.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from app.fetchers.base.fetcher_interface import DataFetcher

SYNC_CRON = os.getenv("JIANGSU_SMART_EVENT_SYNC_CRON", "5 * * * *")
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
    """Sync the previous hour of province-control alarms into the event store."""

    def __init__(self, *, service: Any | None = None) -> None:
        super().__init__(
            name="jiangsu_smart_event_alarm_sync",
            description="江苏智能事件中心每小时同步上一小时省控站告警",
            schedule=os.getenv("JIANGSU_SMART_EVENT_SYNC_CRON", SYNC_CRON),
        )
        self._service = service

    async def fetch_and_store(self) -> dict[str, Any]:
        from app.services.jiangsu_smart_event import JiangsuSmartEventService

        if self._service is None:
            self._service = JiangsuSmartEventService()
        start, end = previous_hour_window()
        alarm_result = await self._service.sync_alarm_events(
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            actor={"user_id": "system", "username": "smart-event-sync"},
            dispatch_ai=False,
            fetch_evidence=True,
        )
        compliance_result = await self._service.sync_compliance_clues(
            actor={"user_id": "system", "username": "smart-event-sync"},
        )
        return {"alarm_sync": alarm_result, "compliance_sync": compliance_result}

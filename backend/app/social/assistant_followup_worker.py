"""One clock on the existing worker scheduler; no web-process polling loops."""

import asyncio

import structlog

from app.social.assistant_followups import AssistantFollowupService
from app.social.assistant_reminder_delivery import deliver_reminder

logger = structlog.get_logger(__name__)
JOB_ID = "assistant-personal-reminders"
_worker = None


class AssistantFollowupWorker:
    def __init__(self, project, service=None, adapter=deliver_reminder):
        self.project = project
        self.service = service or AssistantFollowupService()
        self.adapter = adapter
        self.delivery_task = None
        self.stopping = False

    async def tick(self):
        if self.stopping:
            return
        try:
            await self.service.materialize(self.project)
            await self.service.prepare_notifications(self.project)
            if not self.stopping and (self.delivery_task is None or self.delivery_task.done()):
                if self.delivery_task:
                    self.delivery_task.result()
                self.delivery_task = asyncio.create_task(self._deliver_one())
        except Exception:
            logger.exception("assistant_reminder_tick_failed")

    async def _deliver_one(self):
        try:
            claimed = await self.service.claim_notification(self.project)
            if claimed:
                await self.service.deliver(self.project, claimed, self.adapter)
        except Exception:
            logger.exception("assistant_reminder_delivery_failed")

    async def stop(self):
        self.stopping = True
        if self.delivery_task and not self.delivery_task.done():
            self.delivery_task.cancel()
            await asyncio.gather(self.delivery_task, return_exceptions=True)


def start_assistant_followups(scheduler, project):
    global _worker
    if _worker is not None:
        return
    worker = AssistantFollowupWorker(project)
    scheduler.add_job(
        worker.tick,
        "interval",
        seconds=5,
        id=JOB_ID,
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    _worker = worker


async def stop_assistant_followups(scheduler):
    global _worker
    if _worker is None:
        return
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)
    await _worker.stop()
    _worker = None

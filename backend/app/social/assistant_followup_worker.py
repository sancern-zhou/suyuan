"""One clock on the existing worker scheduler; no web-process polling loops."""

import asyncio

import structlog

from app.social.assistant_followups import AssistantFollowupService
from app.social.assistant_reminder_delivery import deliver_reminder

logger = structlog.get_logger(__name__)
JOB_ID = "assistant-personal-reminders"
_worker = None


class AssistantFollowupWorker:
    def __init__(
        self,
        project,
        service=None,
        adapter=deliver_reminder,
        *,
        analysis_queue=None,
        analyzer=None,
        owner_verifier=None,
    ):
        self.project = project
        self.service = service or AssistantFollowupService()
        self.adapter = adapter
        self.delivery_task = None
        self.stopping = False
        self.analysis_queue = analysis_queue
        self.analyzer = analyzer
        self.owner_verifier = owner_verifier
        self.analysis_task = None
        self.analysis_claim = None

    async def tick(self):
        if self.stopping:
            return
        try:
            await self.service.materialize(self.project)
            await self.service.prepare_notifications(self.project)
            from config.settings import settings

            if self.analysis_task and not self.analysis_task.done() and self.analysis_claim:
                if (
                    not settings.assistant_analysis_enabled
                    or not await self.analysis_queue.is_active(self.project, self.analysis_claim)
                ):
                    self.analysis_task.cancel()
                    await asyncio.gather(self.analysis_task, return_exceptions=True)
            if settings.assistant_analysis_enabled and not self.stopping:
                if self.analysis_queue is None:
                    from app.social.assistant_analysis import AssistantAnalysisQueue

                    self.analysis_queue = AssistantAnalysisQueue(self.service.session_factory)
                await self.analysis_queue.recover(self.project)
                if self.analysis_task is None or self.analysis_task.done():
                    self.analysis_task = asyncio.create_task(self._analyze_one())
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
        pending = [
            task for task in (self.delivery_task, self.analysis_task) if task and not task.done()
        ]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def _analyze_one(self):
        from app.social.assistant_analysis_agent import analyze_claim, verify_analysis_owner
        from app.social.assistant_request import begin_assistant_request, end_assistant_request

        claim = None
        token = begin_assistant_request("", "")
        try:
            claim = await self.analysis_queue.claim(self.project)
            self.analysis_claim = claim
            if claim is None:
                return
            async with asyncio.timeout(240):
                await (self.owner_verifier or verify_analysis_owner)(claim)
                if not await self.analysis_queue.is_active(self.project, claim):
                    await self.analysis_queue.finish(self.project, claim, error="superseded")
                    return
                result = await (self.analyzer or analyze_claim)(claim)
                await self.analysis_queue.finish(self.project, claim, result=result)
        except asyncio.CancelledError:
            if claim:
                await self._record_analysis_failure(claim, "interrupted")
            raise
        except Exception as exc:
            logger.exception("assistant_analysis_failed")
            if claim:
                await self._record_analysis_failure(claim, type(exc).__name__)
        finally:
            self.analysis_claim = None
            end_assistant_request(token)

    async def _record_analysis_failure(self, claim, reason):
        try:
            await self.analysis_queue.finish(self.project, claim, error=reason)
        except Exception:
            # Leave the durable lease for recovery if storage itself is unavailable.
            logger.exception("assistant_analysis_failure_record_unavailable")


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

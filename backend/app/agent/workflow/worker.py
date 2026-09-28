"""Durable worker for queued Agent workflows."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import structlog

from .jobs import WorkflowJob, get_workflow_job_store

logger = structlog.get_logger()


async def _run_job(job: WorkflowJob, store: Any) -> None:
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool

    snapshots: asyncio.Queue = asyncio.Queue()

    def emit(snapshot: dict[str, Any]) -> None:
        snapshots.put_nowait(snapshot)

    async def persist_events() -> None:
        while True:
            snapshot = await snapshots.get()
            if snapshot is None:
                snapshots.task_done()
                return
            try:
                await store.publish_snapshot(job.workflow_id, snapshot)
            finally:
                snapshots.task_done()

    event_task = asyncio.create_task(persist_events())
    try:
        result = await RunAgentWorkflowTool().execute(
            context=SimpleNamespace(session_id=job.session_id, workflow_event_sink=emit),
            workflow=job.definition,
            snapshot=job.snapshot,
        )
        final_snapshot = ((result.get("data") or {}).get("snapshot") or {}) if isinstance(result, dict) else {}
        if final_snapshot:
            emit(final_snapshot)
        await snapshots.join()
        await store.finish(
            job.workflow_id,
            status="succeeded" if isinstance(result, dict) and result.get("success") else "failed",
            result=result if isinstance(result, dict) else {"result": str(result)},
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("workflow_job_failed", workflow_id=job.workflow_id, error=str(exc))
        await store.finish(job.workflow_id, status="failed", result={"error": str(exc)})
    finally:
        await snapshots.put(None)
        await event_task


async def workflow_worker_loop(stop_event: asyncio.Event, *, poll_timeout: int = 1) -> None:
    """Claim and execute durable workflow jobs until worker shutdown."""
    store = get_workflow_job_store()
    recovery_tick = 0
    while not stop_event.is_set():
        try:
            recovery_tick += 1
            if recovery_tick >= 10:
                await store.recover_expired()
                recovery_tick = 0
            job = await store.claim(timeout=poll_timeout)
            if job is None:
                continue
            await _run_job(job, store)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("workflow_worker_iteration_failed", error=str(exc))
            await asyncio.sleep(0.5)

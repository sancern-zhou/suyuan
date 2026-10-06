"""Durable worker for queued Agent workflows."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import structlog

from .jobs import WorkflowJob, WorkflowLeaseLost, get_workflow_job_store

logger = structlog.get_logger()


async def _run_job(job: WorkflowJob, store: Any) -> None:
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool

    snapshots: asyncio.Queue = asyncio.Queue()
    lease_lost = asyncio.Event()
    execution_task: asyncio.Task | None = None

    def lose_lease() -> None:
        lease_lost.set()
        if execution_task is not None:
            execution_task.cancel()

    def emit(snapshot: dict[str, Any]) -> None:
        snapshots.put_nowait(snapshot)

    async def persist_events() -> None:
        while True:
            snapshot = await snapshots.get()
            if snapshot is None:
                snapshots.task_done()
                return
            try:
                if not lease_lost.is_set():
                    await store.publish_snapshot(job.workflow_id, snapshot, lease_token=job.lease_token)
            except WorkflowLeaseLost:
                lose_lease()
            except Exception as exc:
                logger.warning("workflow_event_publish_failed", workflow_id=job.workflow_id, error=str(exc))
            finally:
                snapshots.task_done()

    event_task = asyncio.create_task(persist_events())
    async def maintain_lease() -> None:
        while True:
            await asyncio.sleep(max(1, getattr(store, "lease_seconds", 900) / 3))
            try:
                await store.heartbeat(job.workflow_id, lease_token=job.lease_token)
            except WorkflowLeaseLost:
                lose_lease()
                return
            except Exception as exc:
                logger.warning("workflow_heartbeat_failed", workflow_id=job.workflow_id, error=str(exc))

    heartbeat_task = asyncio.create_task(maintain_lease())
    try:
        # Check ownership before starting any child tool or model call.
        await store.heartbeat(job.workflow_id, lease_token=job.lease_token)
        execution_task = asyncio.create_task(RunAgentWorkflowTool().execute(
            context=SimpleNamespace(
                session_id=job.session_id, workflow_event_sink=emit,
                runtime_mode=job.snapshot.get("parent_mode") or None,
            ),
            workflow=job.definition,
            snapshot=job.snapshot,
            max_concurrency=job.snapshot.get("max_concurrency", 4),
        ))
        result = await execution_task
        final_snapshot = ((result.get("data") or {}).get("snapshot") or {}) if isinstance(result, dict) else {}
        if final_snapshot:
            emit(final_snapshot)
        await snapshots.join()
        if lease_lost.is_set():
            return
        await store.finish(
            job.workflow_id,
            lease_token=job.lease_token,
            status=(
                "succeeded" if isinstance(result, dict) and result.get("success")
                else "cancelled" if isinstance(result, dict) and result.get("status") == "cancelled"
                else "failed"
            ),
            result=result if isinstance(result, dict) else {"result": str(result)},
        )
    except asyncio.CancelledError:
        if lease_lost.is_set():
            logger.warning("workflow_lease_lost", workflow_id=job.workflow_id)
            return
        raise
    except WorkflowLeaseLost:
        lose_lease()
        logger.warning("workflow_lease_lost", workflow_id=job.workflow_id)
    except Exception as exc:
        logger.exception("workflow_job_failed", workflow_id=job.workflow_id, error=str(exc))
        # Persistence failures can outlive a lease; never report failure as its new owner.
        try:
            await store.finish(job.workflow_id, lease_token=job.lease_token, status="failed", result={"error": str(exc)})
        except WorkflowLeaseLost:
            lose_lease()
    finally:
        if execution_task is not None and not execution_task.done():
            execution_task.cancel()
            await asyncio.gather(execution_task, return_exceptions=True)
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
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

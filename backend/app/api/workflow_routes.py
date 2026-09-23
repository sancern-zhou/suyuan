"""Session-scoped workflow inspection and cooperative cancellation APIs."""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agent.session import get_session_manager
from app.agent.workflow.registry import active_workflow_registry
from app.agent.workflow.jobs import get_workflow_job_store
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.service import ConversationCatalogService
from app.core.sse import create_sse_response


router = APIRouter(prefix="/api/sessions/{session_id}/workflows", tags=["agent-workflows"])


def _workflow_snapshots(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = metadata.get("workflow_coordinators")
    if isinstance(values, dict):
        return {
            str(key): dict(value)
            for key, value in values.items()
            if isinstance(value, dict) and value.get("workflow_id")
        }
    return {}


def _workflow_events(snapshot: dict[str, Any], after: int = 0) -> list[dict[str, Any]]:
    runtime = snapshot.get("runtime") if isinstance(snapshot, dict) else None
    events = runtime.get("events") if isinstance(runtime, dict) else None
    if not isinstance(events, list):
        return []
    return [
        dict(event)
        for event in events
        if isinstance(event, dict) and int(event.get("sequence") or 0) > after
    ]


def _has_retryable_nodes(snapshot: dict[str, Any]) -> bool:
    runs = ((snapshot.get("runtime") or {}).get("runs") or {})
    for run in runs.values():
        if not isinstance(run, dict) or not run.get("parent_task_id"):
            continue
        if str(run.get("status") or "") != "failed":
            continue
        if int(run.get("attempt") or 0) < int(run.get("max_attempts") or 1):
            return True
    return False


async def _load_session(session_id: str):
    value = get_session_manager().load_session(session_id)
    return await value if inspect.isawaitable(value) else value


@router.get("")
async def list_workflows(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    await catalog.require_read(session_id, user)
    session = await _load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    snapshots = _workflow_snapshots(dict(session.metadata or {}))
    store = get_workflow_job_store()
    active = {
        item.workflow_id
        for item in await active_workflow_registry.list(session_id=session_id)
    }
    workflows = []
    for workflow_id, snapshot in snapshots.items():
        try:
            job = await store.get(workflow_id)
        except Exception:
            job = None
        workflows.append({
            "workflow_id": workflow_id,
            "status": job.status if job is not None else snapshot.get("status"),
            "active": workflow_id in active or job is not None and job.status == "running",
            "snapshot": snapshot,
        })
    return {
        "workflows": workflows,
        "total": len(snapshots),
    }


@router.get("/{workflow_id}")
async def get_workflow(
    session_id: str,
    workflow_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    await catalog.require_read(session_id, user)
    session = await _load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    snapshot = _workflow_snapshots(dict(session.metadata or {})).get(workflow_id)
    active = await active_workflow_registry.get(workflow_id)
    try:
        job = await get_workflow_job_store().get(workflow_id)
    except Exception:
        job = None
    if snapshot is None and active is None and (job is None or job.session_id != session_id):
        raise HTTPException(status_code=404, detail="workflow_not_found")
    if active is not None and active.session_id not in {None, session_id}:
        raise HTTPException(status_code=404, detail="workflow_not_found")
    return {
        "workflow_id": workflow_id,
        "active": active is not None or job is not None and job.status == "running",
        "job_status": job.status if job is not None else None,
        "snapshot": snapshot,
    }


@router.get("/{workflow_id}/events")
async def workflow_events(
    session_id: str,
    workflow_id: str,
    after: int = Query(default=0, ge=0),
    event_id: str = Query(default="0-0"),
    follow: bool = Query(default=False),
    timeout_seconds: float = Query(default=30.0, ge=0.0, le=300.0),
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Read the durable runtime journal, optionally following new events."""
    await catalog.require_read(session_id, user)

    async def load_snapshot() -> dict[str, Any] | None:
        session = await _load_session(session_id)
        if session is None:
            return None
        return _workflow_snapshots(dict(session.metadata or {})).get(workflow_id)

    snapshot = await load_snapshot()
    if snapshot is None:
        active = await active_workflow_registry.get(workflow_id)
        try:
            job = await get_workflow_job_store().get(workflow_id)
        except Exception:
            job = None
        if active is None and (job is None or job.session_id != session_id):
            raise HTTPException(status_code=404, detail="workflow_not_found")
        if active is not None and active.session_id not in {None, session_id}:
            raise HTTPException(status_code=404, detail="workflow_not_found")

    store = get_workflow_job_store()
    if not follow:
        stream_events = []
        try:
            stream_events = await store.read_events(workflow_id, after_id=event_id)
        except Exception:
            stream_events = []
        return {
            "workflow_id": workflow_id,
            "status": (snapshot or {}).get("status"),
            "events": [
                {"event_id": event_key, **payload}
                for event_key, payload in stream_events
            ] or _workflow_events(snapshot or {}, after),
        }

    async def event_generator():
        cursor = after
        stream_cursor = event_id
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            current = await load_snapshot()
            try:
                stream_events = await store.read_events(workflow_id, after_id=stream_cursor, block_ms=250)
            except Exception:
                stream_events = []
            if stream_events:
                for event_key, event in stream_events:
                    stream_cursor = event_key
                    yield f"data: {json.dumps({'event_id': event_key, **event}, ensure_ascii=False, default=str)}\n\n"
            else:
                events = _workflow_events(current or {}, cursor)
                for event in events:
                    cursor = max(cursor, int(event.get("sequence") or cursor))
                    yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            status = str((current or {}).get("status") or "")
            if status in {"succeeded", "failed", "cancelled"}:
                yield f"data: {json.dumps({'type': 'workflow.terminal', 'status': status, 'sequence': cursor}, ensure_ascii=False)}\n\n"
                return
            if asyncio.get_running_loop().time() >= deadline:
                yield f"data: {json.dumps({'type': 'workflow.timeout', 'sequence': cursor}, ensure_ascii=False)}\n\n"
                return
            await asyncio.sleep(0.25)

    return create_sse_response(event_generator())


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(
    session_id: str,
    workflow_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    await catalog.require_write(session_id, user)
    active = await active_workflow_registry.get(workflow_id)
    if active is not None and active.session_id not in {None, session_id}:
        raise HTTPException(status_code=404, detail="workflow_not_found")
    if active is None:
        session = await _load_session(session_id)
        if session is None or workflow_id not in _workflow_snapshots(dict(session.metadata or {})):
            raise HTTPException(status_code=404, detail="workflow_not_found")
    accepted = await active_workflow_registry.cancel(workflow_id, reason="cancelled by API")
    if not accepted:
        raise HTTPException(status_code=409, detail="workflow_not_active")
    return {
        "workflow_id": workflow_id,
        "status": "cancelled" if active is not None else "cancel_requested",
    }


@router.post("/{workflow_id}/resume", status_code=202)
async def resume_workflow(
    session_id: str,
    workflow_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Resume a failed workflow from its durable snapshot in the background."""
    await catalog.require_write(session_id, user)
    session = await _load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    snapshot = _workflow_snapshots(dict(session.metadata or {})).get(workflow_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="workflow_not_found")
    if snapshot.get("status") == "cancelled":
        raise HTTPException(status_code=409, detail="cancelled_workflow_cannot_resume")
    if snapshot.get("status") not in {"failed", "running", "queued"}:
        raise HTTPException(status_code=409, detail="workflow_not_resumable")
    if snapshot.get("status") == "failed" and not _has_retryable_nodes(snapshot):
        raise HTTPException(status_code=409, detail="workflow_retry_budget_exhausted")
    if await active_workflow_registry.get(workflow_id) is not None:
        raise HTTPException(status_code=409, detail="workflow_already_active")

    store = get_workflow_job_store()
    try:
        job = await store.enqueue(
            session_id=session_id,
            workflow_id=workflow_id,
            definition=snapshot.get("definition") or {},
            snapshot=snapshot,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="workflow_queue_unavailable") from exc
    return {"workflow_id": workflow_id, "status": job.status, "queued": True}

"""Session-scoped workflow inspection and cooperative cancellation APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.agent.session import get_session_manager
from app.agent.workflow.registry import active_workflow_registry
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.service import ConversationCatalogService


router = APIRouter(prefix="/api/sessions/{session_id}/workflows", tags=["agent-workflows"])


def _workflow_snapshots(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = metadata.get("workflow_coordinators")
    if isinstance(values, dict):
        return {
            str(key): dict(value)
            for key, value in values.items()
            if isinstance(value, dict)
        }
    # Compatibility with snapshots written before multi-workflow indexing.
    legacy = metadata.get("workflow_coordinator")
    if isinstance(legacy, dict) and legacy.get("workflow_id"):
        return {str(legacy["workflow_id"]): dict(legacy)}
    return {}


@router.get("")
async def list_workflows(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    await catalog.require_read(session_id, user)
    session = get_session_manager().load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    snapshots = _workflow_snapshots(dict(session.metadata or {}))
    active = {
        item.workflow_id
        for item in await active_workflow_registry.list(session_id=session_id)
    }
    return {
        "workflows": [
            {
                "workflow_id": workflow_id,
                "status": snapshot.get("status"),
                "active": workflow_id in active,
                "snapshot": snapshot,
            }
            for workflow_id, snapshot in snapshots.items()
        ],
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
    session = get_session_manager().load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    snapshot = _workflow_snapshots(dict(session.metadata or {})).get(workflow_id)
    active = await active_workflow_registry.get(workflow_id)
    if snapshot is None and active is None:
        raise HTTPException(status_code=404, detail="workflow_not_found")
    if active is not None and active.session_id not in {None, session_id}:
        raise HTTPException(status_code=404, detail="workflow_not_found")
    return {
        "workflow_id": workflow_id,
        "active": active is not None,
        "snapshot": snapshot,
    }


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(
    session_id: str,
    workflow_id: str,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    await catalog.require_write(session_id, user)
    active = await active_workflow_registry.get(workflow_id)
    if active is None or active.session_id not in {None, session_id}:
        raise HTTPException(status_code=409, detail="workflow_not_active")
    await active_workflow_registry.cancel(workflow_id, reason="cancelled by API")
    return {"workflow_id": workflow_id, "status": "cancelled"}

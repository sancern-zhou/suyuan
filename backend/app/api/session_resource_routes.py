"""Authorized catalog and opaque content delivery for session resources."""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.agent.resources.actions import resource_action_links, resource_content_base
from app.agent.resources.resource_service import SessionResourceService, StoredResource
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.service import ConversationCatalogService
from app.utils.path_config import get_data_registry

logger = structlog.get_logger()
router = APIRouter(prefix="/api/sessions", tags=["session-resources"])


def resource_dto(session_id: str, item: StoredResource) -> dict:
    """Project a resource without exposing server locators or tool metadata."""
    base = resource_content_base(session_id, item)
    directory = item.kind == "artifact" and bool(item.metadata.get("entrypoint"))
    actions = resource_action_links(session_id, item)
    return {
        "resource_id": item.resource_id,
        "ref_id": item.resource_id,
        "group_id": item.group_id,
        "parent_resource_id": item.parent_resource_id,
        "resource_key": item.resource_key,
        "relation": item.relation,
        "kind": item.kind,
        "role": item.role,
        "label": item.label,
        "format": item.format,
        "media_type": item.media_type,
        "renderer": item.renderer,
        "capabilities": item.capabilities,
        "actions": actions,
        "version": item.version,
        "status": item.status,
        "content_url": f"{base}/" if directory else base,
        "download_url": actions.get("download"),
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


@router.get("/{session_id}/resources")
async def get_session_resources(
    session_id: str,
    kind: str | None = None,
    role: str | None = None,
    renderer: str | None = None,
    group_id: str | None = None,
    status: str | None = "active",
    limit: int = 100,
    cursor: str | None = None,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    await catalog.require_read(session_id, user)
    try:
        page = await SessionResourceService.database().list_resources(
            session_id,
            kind=kind,
            role=role,
            renderer=renderer,
            group_id=group_id,
            status=status,
            limit=min(max(limit, 1), 200),
            cursor=cursor,
        )
    except Exception as exc:
        logger.error(
            "session_resources_load_failed", session_id=session_id, error=str(exc)
        )
        raise HTTPException(
            status_code=503, detail="resource_catalog_unavailable"
        ) from exc
    resources = [resource_dto(session_id, item) for item in page.resources]
    return {
        "session_id": session_id,
        "resources": resources,
        "total": len(resources),
        "next_cursor": page.next_cursor,
    }


def _require_within(candidate: Path, root: Path) -> Path:
    resolved = candidate.expanduser().resolve()
    if not resolved.is_relative_to(root):
        raise HTTPException(status_code=403, detail="resource_path_forbidden")
    return resolved


def _content_target(
    resource: StoredResource, registry_root: Path, asset_path: str | None
) -> tuple[Path, str]:
    raw_path = (resource.locator or {}).get("path")
    if not raw_path:
        raise HTTPException(status_code=404, detail="resource_content_unavailable")
    registered = _require_within(Path(str(raw_path)), registry_root)

    if resource.kind == "artifact" and resource.metadata.get("entrypoint"):
        if not registered.is_dir():
            raise HTTPException(status_code=404, detail="resource_content_missing")
        relative_target = asset_path
        if relative_target is None or relative_target == "":
            relative_target = str(resource.metadata["entrypoint"])
        candidate = _require_within(registered / relative_target, registered)
        candidate = _require_within(candidate, registry_root)
        media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        return candidate, media_type

    if asset_path is not None:
        raise HTTPException(status_code=404, detail="resource_content_missing")
    media_type = resource.media_type or (
        mimetypes.guess_type(registered.name)[0] or "application/octet-stream"
    )
    return registered, media_type


@router.get("/{session_id}/resources/{resource_id}/content/{asset_path:path}")
@router.get("/{session_id}/resources/{resource_id}/content")
async def get_session_resource_content(
    session_id: str,
    resource_id: str,
    asset_path: str | None = None,
    disposition: Literal["inline", "attachment"] = "inline",
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Serve authorized bytes while keeping the storage locator opaque."""
    await catalog.require_read(session_id, user)
    resource = await SessionResourceService.database().get_resource(
        session_id, resource_id, status="active"
    )
    if resource is None or resource.kind not in {"file", "artifact", "visual"}:
        raise HTTPException(status_code=404, detail="resource_not_found")
    required_capability = "download" if disposition == "attachment" else "preview"
    if required_capability not in resource.capabilities:
        raise HTTPException(status_code=404, detail="resource_content_unavailable")

    registry_root = get_data_registry().expanduser().resolve()
    target, media_type = _content_target(resource, registry_root, asset_path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="resource_content_missing")

    headers = {
        "Cache-Control": "private, max-age=300, immutable",
        "X-Content-Type-Options": "nosniff",
    }
    if media_type == "text/html":
        headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'"
        )
    filename = target.name if asset_path is not None else (resource.label or target.name)
    return FileResponse(
        path=target,
        media_type=media_type,
        filename=filename,
        content_disposition_type=disposition,
        headers=headers,
    )

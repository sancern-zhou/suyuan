"""Shared conversation board (共享对话面板).

Users publish a snapshot of one of their own conversations; every
authenticated user of the deployment (web or App) can browse it without
re-asking the same question. Shares are immutable snapshots: message text
is copied at share time and chart/attachment files are copied into a
per-share directory under DATA_REGISTRY_DIR, so later deletion of the
source session or resource GC never breaks an existing share.

Auth accepts both channels: an App bearer token or the web session
identity (request.state.current_user) — both converge on CurrentUser.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import shutil
import uuid
from pathlib import Path
from urllib.parse import unquote

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth.models import CurrentUser
from app.conversations.dependencies import get_conversation_catalog
from app.db.database import async_session
from app.social.app_identity import resolve_access_token
from app.social.shared_conversation_models import (
    SHARE_STATUS_ACTIVE,
    SHARE_STATUS_REMOVED,
    SHARE_STATUS_WITHDRAWN,
    SocialSharedConversation,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/api/shared-conversations")

# Charts and documents larger than this are not copied into the share; the
# snapshot keeps their (rewritten) URLs and the resource endpoint 404s.
MAX_ATTACHMENT_COPY_BYTES = 10 * 1024 * 1024

# Report-mode conversations carry an HTML report package (directory with
# relative asset references). Copy it wholesale so the board can embed it.
MAX_REPORT_COPY_BYTES = 100 * 1024 * 1024

# Disk/db guardrail: one user cannot flood the board with snapshots.
MAX_ACTIVE_SHARES_PER_USER = 50

_RESOURCE_URL_PREFIX = "/api/social/app/sessions/{session_id}/resources/"
_SHARE_RESOURCE_URL_PREFIX = "/api/shared-conversations/{share_id}/resources/"


class ShareCreateRequest(BaseModel):
    session_id: str


async def require_shared_identity(
    request: Request,
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    """Accept the web session identity or an App bearer token.

    The gateway middleware already resolves the web session token into
    ``request.state.current_user``; check that first so the web Bearer
    token is not mistaken for an App JWT (which would 401 and log the
    user out). App requests carry an App JWT instead and are verified
    here as a fallback.
    """
    user = getattr(request.state, "current_user", None)
    if isinstance(user, CurrentUser):
        return user
    scheme, separator, token = (authorization or "").partition(" ")
    if separator and scheme.lower() == "bearer" and token.strip():
        identity = resolve_access_token(token.strip())
        return identity.as_current_user()
    raise HTTPException(status_code=401, detail="authentication_required")


def _share_dir(share_id: str) -> Path:
    from app.utils.path_config import get_data_registry

    return get_data_registry() / "social" / "shared_conversations" / share_id


def _deep_replace(value, old: str, new: str):
    """Rewrite session-scoped resource URLs throughout the snapshot."""
    if isinstance(value, str):
        return value.replace(old, new) if old in value else value
    if isinstance(value, dict):
        return {key: _deep_replace(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_replace(item, old, new) for item in value]
    return value


def _escaped_like_keyword(keyword: str) -> str:
    """Escape LIKE wildcards so user input matches literally."""
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _iter_attachments(value):
    """Yield every attachment-looking dict in the snapshot."""
    if isinstance(value, dict):
        if "url" in value and ("file_id" in value or "resource_id" in value):
            yield value
        for item in value.values():
            yield from _iter_attachments(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_attachments(item)


def _item_text(item: dict) -> str:
    for key in ("content", "text"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = item.get("data")
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, dict):
            for key in ("content", "text"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def _visible_history(history: list, visible_types: set[str]) -> list[dict]:
    kept = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("type") or item.get("role") or "").lower()
        if role not in visible_types:
            continue
        # Drop oversized tool/thought dumps; the board is for reading.
        if role in {"thought", "thinking"} and len(_item_text(item)) > 4000:
            continue
        kept.append(item)
    return kept


async def _copy_share_attachments(
    session_id: str, history: list[dict], share_id: str
) -> list[dict]:
    """Copy referenced resource files into the share directory.

    Returns the attachment manifest stored on the share row; each entry maps
    the original resource_id to its copied file so the resource endpoint can
    serve bytes without touching the (garbage-collectable) original.
    """
    from app.agent.resources.resource_service import SessionResourceService
    from app.utils.path_config import get_data_registry

    prefix = _RESOURCE_URL_PREFIX.format(session_id=session_id)
    wanted: dict[str, dict] = {}
    for attachment in _iter_attachments(history):
        for key in ("url", "preview_url", "download_url"):
            url = str(attachment.get(key) or "")
            if url.startswith(prefix):
                resource_id = url[len(prefix):].split("?", 1)[0].split("/", 1)[0]
                if resource_id and resource_id not in wanted:
                    wanted[resource_id] = attachment

    if not wanted:
        return []

    service = SessionResourceService.database()
    registry_root = get_data_registry().expanduser().resolve()
    target_dir = _share_dir(share_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    for resource_id, attachment in wanted.items():
        try:
            resource = await service.get_resource(session_id, resource_id, status="active")
        except Exception as exc:
            logger.warning("shared_attachment_lookup_failed", session_id=session_id, resource_id=resource_id, error=str(exc))
            continue
        if resource is None:
            continue
        raw_path = str((resource.locator or {}).get("path") or "").strip()
        if not raw_path:
            continue
        source = Path(raw_path).expanduser().resolve()
        try:
            source.relative_to(registry_root)
        except ValueError:
            continue
        if not source.is_file() or source.stat().st_size > MAX_ATTACHMENT_COPY_BYTES:
            continue
        suffix = source.suffix or ""
        stored_name = f"{resource_id}{suffix}"
        await asyncio.to_thread(shutil.copyfile, source, target_dir / stored_name)
        manifest.append(
            {
                "resource_id": resource_id,
                "stored_name": stored_name,
                "filename": str(attachment.get("filename") or source.name),
                "media_type": str(resource.media_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream"),
            }
        )
    return manifest


async def _copy_share_report(session_id: str, share_id: str) -> dict | None:
    """Copy an HTML report package (artifact with entrypoint) into the share.

    Report-mode conversations keep the actual report in a session artifact
    directory; the message text only says the report was generated. The
    package is copied wholesale (relative asset references must keep working)
    so the board can embed it behind a short-lived view ticket.
    """
    from app.agent.resources.resource_service import SessionResourceService
    from app.utils.path_config import get_data_registry

    service = SessionResourceService.database()
    try:
        page = await service.list_resources(session_id, kind="artifact", status="active", limit=200)
    except Exception as exc:
        logger.warning("shared_report_lookup_failed", session_id=session_id, error=str(exc))
        return None

    registry_root = get_data_registry().expanduser().resolve()
    for resource in page.resources:
        entrypoint = str((resource.metadata or {}).get("entrypoint") or "").strip()
        raw_path = str((resource.locator or {}).get("path") or "").strip()
        if not entrypoint or not raw_path:
            continue
        source = Path(raw_path).expanduser().resolve()
        try:
            source.relative_to(registry_root)
        except ValueError:
            continue
        if not source.is_dir():
            continue
        total = sum(f.stat().st_size for f in source.rglob("*") if f.is_file())
        if total > MAX_REPORT_COPY_BYTES:
            logger.warning("shared_report_too_large", session_id=session_id, bytes=total)
            return None

        target = _share_dir(share_id) / "report"
        target.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copytree, source, target, dirs_exist_ok=True)
        if not (target / entrypoint).is_file():
            logger.warning("shared_report_entry_missing", session_id=session_id, entry=entrypoint)
            return None
        return {
            "kind": "report_package",
            "base": "report/",
            "entry": entrypoint,
            "resource_id": resource.resource_id,
        }
    return None


async def _build_snapshot(user: CurrentUser, session_id: str) -> dict:
    """Restore one owned conversation and capture the share snapshot."""
    from app.api.social_app_routes import (
        _MOBILE_VISIBLE_HISTORY_TYPES,
        _app_resource_descriptors,
    )
    from app.agent.resources.resource_service import SessionResourceService
    from app.conversations.adapters import get_conversation_adapters
    from app.social.inline_charts import attach_reply_resources

    catalog = get_conversation_catalog()
    row = await catalog.repository.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    if row.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="not_session_owner")

    restored = await get_conversation_adapters().get(row.source).restore(
        row, message_limit=100, lazy_artifacts=True
    )
    if not restored:
        raise HTTPException(status_code=400, detail="conversation_empty")
    if row.source.value == "web":
        session = restored.get("session")
        history = list((session.model_dump(mode="json") if session else {}).get("conversation_history") or [])
    else:
        history = list((restored.get("normalized_session") or {}).get("conversation_history") or [])

    visible = _visible_history(history, _MOBILE_VISIBLE_HISTORY_TYPES)
    questions = [text for item in visible if str(item.get("type") or item.get("role") or "").lower() == "user" for text in [_item_text(item)] if text]
    if not questions:
        raise HTTPException(status_code=400, detail="conversation_empty")

    try:
        descriptors = await _app_resource_descriptors(session_id, [])
        attach_reply_resources(visible, descriptors)
    except Exception as exc:
        logger.warning("shared_snapshot_resources_attach_failed", session_id=session_id, error=str(exc))

    return {
        "history": visible,
        "title": (row.title or "").strip() or (questions[0][:120] or "共享对话"),
        "first_question": questions[0][:400],
        "mode": row.mode or "",
        "source_kind": row.source.value,
    }


@router.post("")
async def create_shared_conversation(
    payload: ShareCreateRequest,
    user: CurrentUser = Depends(require_shared_identity),
) -> dict:
    """Publish a snapshot of one of the caller's own conversations."""
    session_id = payload.session_id.strip()
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id_required")

    async with async_session() as db:
        owned = await db.scalar(
            select(func.count())
            .select_from(SocialSharedConversation)
            .where(
                SocialSharedConversation.owner_user_id == user.id,
                SocialSharedConversation.status == SHARE_STATUS_ACTIVE,
            )
        )
    if int(owned or 0) >= MAX_ACTIVE_SHARES_PER_USER:
        raise HTTPException(status_code=429, detail="share_quota_exceeded")

    snapshot = await _build_snapshot(user, session_id)
    share_id = uuid.uuid4().hex
    manifest = await _copy_share_attachments(session_id, snapshot["history"], share_id)
    report_package = await _copy_share_report(session_id, share_id)
    if report_package:
        manifest.append(report_package)

    new_prefix = _SHARE_RESOURCE_URL_PREFIX.format(share_id=share_id)
    history = _deep_replace(
        snapshot["history"],
        _RESOURCE_URL_PREFIX.format(session_id=session_id),
        new_prefix,
    )

    record = SocialSharedConversation(
        share_id=share_id,
        owner_user_id=user.id,
        owner_username=user.username or user.id,
        owner_display_name=user.display_name or user.username or user.id,
        source_session_id=session_id,
        source_kind=snapshot["source_kind"],
        mode=snapshot["mode"],
        title=snapshot["title"][:500],
        first_question=snapshot["first_question"],
        message_count=len(history),
        snapshot=history,
        attachments=manifest,
        status=SHARE_STATUS_ACTIVE,
    )
    async with async_session() as db:
        db.add(record)
        try:
            await db.commit()
        except Exception:
            shutil.rmtree(_share_dir(share_id), ignore_errors=True)
            raise
    logger.info(
        "shared_conversation_created",
        share_id=share_id,
        session_id=session_id,
        owner=user.id,
        messages=record.message_count,
        attachments=len(manifest),
    )
    return _share_summary(record)


@router.get("")
async def list_shared_conversations(
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_shared_identity),
) -> dict:
    statement = select(SocialSharedConversation).where(
        SocialSharedConversation.status == SHARE_STATUS_ACTIVE
    )
    keyword = search.strip()
    if keyword:
        like = _escaped_like_keyword(keyword)
        statement = statement.where(
            SocialSharedConversation.title.ilike(like, escape="\\")
            | SocialSharedConversation.first_question.ilike(like, escape="\\")
        )
    async with async_session() as db:
        total = await db.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        rows = (
            (
                await db.execute(
                    statement.order_by(SocialSharedConversation.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    return {
        "total": int(total or 0),
        "shares": [_share_summary(row) for row in rows],
    }


@router.get("/{share_id}")
async def get_shared_conversation(
    share_id: str,
    user: CurrentUser = Depends(require_shared_identity),
) -> dict:
    row = await _active_share(share_id)
    summary = _share_summary(row)
    summary["messages"] = row.snapshot or []
    return summary


@router.delete("/{share_id}")
async def delete_shared_conversation(
    share_id: str,
    user: CurrentUser = Depends(require_shared_identity),
) -> dict:
    """Owner withdraws; admin removes. The rows (and files) are kept for audit."""
    async with async_session() as db:
        row = await db.get(SocialSharedConversation, share_id)
        if row is None:
            raise HTTPException(status_code=404, detail="share_not_found")
        if row.status == SHARE_STATUS_REMOVED:
            return {"share_id": share_id, "status": row.status}
        if row.owner_user_id == user.id:
            row.status = SHARE_STATUS_WITHDRAWN
        elif user.is_admin:
            row.status = SHARE_STATUS_REMOVED
            row.removed_by = user.username or user.id
        else:
            raise HTTPException(status_code=403, detail="not_share_owner")
        row.updated_at = func.now()
        status = row.status
        await db.commit()
    logger.info("shared_conversation_removed", share_id=share_id, by=user.id, status=status)
    return {"share_id": share_id, "status": status}


@router.get("/{share_id}/resources/{resource_id}")
@router.get("/{share_id}/resources/{resource_id}/content")
async def get_shared_conversation_resource(
    share_id: str,
    resource_id: str,
    user: CurrentUser = Depends(require_shared_identity),
) -> FileResponse:
    """Serve snapshot-copied attachment bytes; immune to source resource GC."""
    row = await _active_share(share_id)
    for item in row.attachments or []:
        if str(item.get("resource_id") or "") == resource_id:
            target = (_share_dir(share_id) / str(item.get("stored_name") or "")).resolve()
            if target.is_file() and _share_dir(share_id).resolve() in target.parents:
                return FileResponse(
                    target,
                    media_type=str(item.get("media_type") or "application/octet-stream"),
                    filename=str(item.get("filename") or target.name),
                )
            break
    raise HTTPException(status_code=404, detail="shared_resource_not_found")


@router.get("/{share_id}/report-view")
async def get_shared_report_view(
    share_id: str,
    user: CurrentUser = Depends(require_shared_identity),
) -> dict:
    """Issue a short-lived view ticket for the embedded report package.

    The board embeds the report in a sandboxed iframe, which cannot send
    Authorization headers; the ticket travels as a path segment so relative
    asset URLs inside the report inherit it (same mechanism as chat).
    """
    row = await _active_share(share_id)
    package = _report_package(row)
    if package is None:
        raise HTTPException(status_code=404, detail="report_not_found")
    from app.auth.share_access import external_api_path, get_share_access_service

    ticket = get_share_access_service().issue("shared-report", share_id)
    entry = str(package.get("entry") or "index.html")
    return {
        "url": external_api_path(
            f"/api/shared-conversations/{share_id}/reports/_t/{ticket}/{entry}"
        ),
        "entry": entry,
    }


@router.get("/{share_id}/reports/_t/{ticket}/{file_path:path}")
async def get_shared_report_file(
    share_id: str,
    ticket: str,
    file_path: str,
) -> FileResponse:
    """Serve report package bytes; the ticket authorizes the sandboxed iframe.

    No user dependency here on purpose: the iframe cannot send Authorization
    headers, the gateway middleware admits ticket-bearing GETs, and the
    ticket is verified again below (defense in depth).
    """
    row = await _active_share(share_id)
    package = _report_package(row)
    if package is None:
        raise HTTPException(status_code=404, detail="report_not_found")
    from app.auth.share_access import get_share_access_service

    if not get_share_access_service().verify(unquote(ticket), "shared-report", share_id):
        raise HTTPException(status_code=401, detail="invalid_report_ticket")

    base = (_share_dir(share_id) / str(package.get("base") or "report/")).resolve()
    if not file_path:
        file_path = str(package.get("entry") or "index.html")
    target = (base / file_path).resolve()
    if base not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="report_file_not_found")
    media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type)


async def _active_share(share_id: str) -> SocialSharedConversation:
    async with async_session() as db:
        row = await db.get(SocialSharedConversation, share_id)
    if row is None or row.status != SHARE_STATUS_ACTIVE:
        raise HTTPException(status_code=404, detail="share_not_found")
    return row


def _report_package(row: SocialSharedConversation) -> dict | None:
    for item in row.attachments or []:
        if isinstance(item, dict) and item.get("kind") == "report_package":
            return item
    return None


def _share_summary(row: SocialSharedConversation) -> dict:
    return {
        "share_id": row.share_id,
        "title": row.title,
        "first_question": row.first_question,
        "message_count": row.message_count,
        "mode": row.mode,
        "has_report": _report_package(row) is not None,
        "owner": {
            "user_id": row.owner_user_id,
            "username": row.owner_username,
            "display_name": row.owner_display_name,
        },
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "status": row.status,
    }

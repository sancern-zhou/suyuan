"""Android App Social Gateway.

This is deliberately separate from QQ/WeChat channel adapters and the worker
internal API. The App account is the social identity used for memory and
conversation ownership.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

import structlog
from aiohttp import WSMsgType
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.dependencies import get_conversation_catalog
from app.conversations.schemas import ConversationSource
from app.db.database import get_db
from app.knowledge_base.models import UploadedFile
from app.agent.resources.resource_service import SessionResourceService
from app.utils.path_config import get_data_registry
from app.social.app_identity import (
    AppIdentity,
    issue_access_token,
    issue_token_pair,
    require_app_identity,
    resolve_access_token,
    resolve_refresh_token,
)
from app.social.session_mapper import SessionMapper
from config.settings import settings

router = APIRouter(prefix="/api/social/app", tags=["android-app"])
logger = structlog.get_logger()
_agent = None
_agent_lock = asyncio.Lock()
_memory_managers: dict[str, object] = {}


class AppLoginRequest(BaseModel):
    account_id: str = Field(..., min_length=1, max_length=128)
    account_secret: str = Field(..., min_length=1, max_length=512)


class AppLoginResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_at: int
    refresh_expires_at: int | None = None
    account_id: str
    display_name: str
    social_user_id: str


class AppChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=20000)
    session_id: str | None = Field(default=None, max_length=128)
    attachments: list[dict] = Field(default_factory=list, max_length=8)


class AppSteerRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class AppRenameSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)


class AppVoiceResponse(BaseModel):
    text: str
    language: str = "zh"


class AppOAuthExchangeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=4096)
    code_verifier: str = Field(..., min_length=43, max_length=128)
    redirect_uri: str | None = Field(default=None, max_length=512)


class AppRefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, max_length=8192)


class AppPushDeviceRequest(BaseModel):
    provider: str = Field(default="getui", min_length=1, max_length=32)
    device_id: str = Field(..., min_length=8, max_length=256)
    platform: str = Field(default="android", min_length=1, max_length=32)
    app_id: str | None = Field(default=None, max_length=128)


def _broadcast_attachment_payload(item: object, *, message_id: str, index: int) -> dict | None:
    """Project internal broadcast attachment metadata to an App-safe shape."""
    if not isinstance(item, dict):
        return None
    name = str(item.get("filename") or item.get("name") or "附件").strip() or "附件"
    mime_type = str(item.get("mime_type") or item.get("mimeType") or "").strip()
    if not mime_type:
        mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    raw_url = str(item.get("url") or "").strip()
    payload = {
        "filename": name,
        "name": name,
        "type": "image" if mime_type.lower().startswith("image/") else "file",
        "mime_type": mime_type,
    }
    # Only forward URLs, never server filesystem paths; local files are served
    # through the owner-scoped broadcast attachment content endpoint.
    if raw_url.startswith("/") or raw_url.startswith("https://") or raw_url.startswith("http://"):
        payload["url"] = raw_url
    elif str(item.get("path") or "").strip():
        base_url = f"/api/social/app/broadcasts/{message_id}/attachments/{index}"
        payload["url"] = f"{base_url}/content"
        payload["download_url"] = f"{base_url}/content"
        # Office 文件 App 端只能通过 PDF rendition 预览，与聊天附件的
        # office preview 管线保持一致。
        if Path(name).suffix.lower() in {
            ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
        }:
            payload["preview_url"] = f"{base_url}/preview"
            payload["preview_mime_type"] = "application/pdf"
    return payload


def _broadcast_payload(item: dict) -> dict:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    raw_attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else []
    message_id = str(item.get("id") or "")
    attachments = []
    for index, raw in enumerate(raw_attachments):
        attachment = _broadcast_attachment_payload(raw, message_id=message_id, index=index)
        if attachment is not None:
            attachments.append(attachment)
    return {
        "message_id": str(item.get("id") or ""),
        "content": str(item.get("content") or ""),
        "timestamp": item.get("timestamp"),
        "read": bool(item.get("read") is True or data.get("read") is True),
        "attachments": attachments,
        "metadata": {
            key: value
            for key, value in data.items()
            if key not in {"attachments", "read", "read_at"}
        },
    }


@router.websocket("/voice/realtime")
async def realtime_voice(websocket: WebSocket) -> None:
    """Proxy PCM audio to Alibaba realtime ASR and relay partial/final text."""
    authorization = websocket.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        await websocket.close(code=4401, reason="authentication_required")
        return
    try:
        resolve_access_token(token)
    except HTTPException:
        await websocket.close(code=4401, reason="invalid_token")
        return

    from aiohttp import ClientSession, ClientTimeout
    from app.services.voice_service import (
        VoiceConfigError,
        build_realtime_finish_task,
        build_realtime_run_task,
        realtime_asr_ws_url,
        realtime_result_text,
    )

    api_key = (settings.voice_realtime_api_key or "").strip()
    if not api_key:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "未配置阿里云实时语音识别 API Key"})
        await websocket.close(code=1011)
        return

    await websocket.accept()
    task_id = str(uuid.uuid4())
    upstream = None
    relay_task = None
    try:
        timeout = ClientTimeout(total=None, connect=20, sock_read=None)
        async with ClientSession(timeout=timeout) as client:
            upstream = await client.ws_connect(
                realtime_asr_ws_url(),
                headers={"Authorization": f"Bearer {api_key}"},
                heartbeat=20,
            )
            await upstream.send_json(build_realtime_run_task(task_id))
            started = asyncio.Event()

            async def send_client(payload: dict) -> None:
                with contextlib.suppress(Exception):
                    await websocket.send_json(payload)

            async def relay_results() -> None:
                async for message in upstream:
                    if message.type == WSMsgType.TEXT:
                        try:
                            payload = json.loads(message.data)
                        except json.JSONDecodeError:
                            continue
                        event = payload.get("header", {}).get("event")
                        if event == "task-started":
                            started.set()
                            await send_client({"type": "ready"})
                        elif event == "task-failed":
                            started.set()
                            await send_client({
                                "type": "error",
                                "message": payload.get("header", {}).get("error_message", "阿里云语音识别失败"),
                            })
                        else:
                            result = realtime_result_text(payload)
                            if result:
                                text, final = result
                                await send_client({"type": "final" if final else "partial", "text": text})
                        if event == "task-finished":
                            await send_client({"type": "finished"})
                            break
                    elif message.type in {WSMsgType.ERROR, WSMsgType.CLOSED, WSMsgType.CLOSE}:
                        started.set()
                        break

            async def wait_started() -> None:
                try:
                    await asyncio.wait_for(started.wait(), timeout=20)
                except asyncio.TimeoutError as exc:
                    raise VoiceConfigError("阿里云实时语音识别启动超时") from exc

            relay_task = asyncio.create_task(relay_results())
            while True:
                incoming = await websocket.receive()
                if incoming.get("type") == "websocket.disconnect":
                    break
                if incoming.get("bytes") is not None:
                    await wait_started()
                    await upstream.send_bytes(incoming["bytes"])
                elif incoming.get("text"):
                    try:
                        command = json.loads(incoming["text"])
                    except json.JSONDecodeError:
                        command = {"type": incoming["text"]}
                    if command.get("type") in {"stop", "finish"}:
                        await wait_started()
                        await upstream.send_json(build_realtime_finish_task(task_id))
                        break
            if relay_task:
                await relay_task
    except WebSocketDisconnect:
        return
    except (ConnectionError, asyncio.CancelledError):
        raise
    except Exception as exc:
        logger.warning("social_app_realtime_voice_failed", error=str(exc))
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": "实时语音识别服务暂不可用"})
    finally:
        if relay_task:
            relay_task.cancel()
        if upstream is not None:
            await upstream.close()


@router.post("/auth/login", response_model=AppLoginResponse)
async def login(request: AppLoginRequest) -> AppLoginResponse:
    token, identity = issue_access_token(request.account_id, request.account_secret)
    access_token, refresh_token, expires_at, refresh_expires_at = issue_token_pair(identity)
    return AppLoginResponse(
        access_token=access_token or token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        refresh_expires_at=refresh_expires_at,
        account_id=identity.account_id,
        display_name=identity.display_name,
        social_user_id=identity.social_user_id,
    )


@router.get("/auth/oidc/config")
async def oidc_config() -> dict:
    from app.social.company_oauth import authorization_config

    return authorization_config()


@router.post("/auth/oidc/exchange", response_model=AppLoginResponse)
async def oidc_exchange(payload: AppOAuthExchangeRequest) -> AppLoginResponse:
    from app.social.company_oauth import exchange_code

    identity = await exchange_code(
        code=payload.code,
        code_verifier=payload.code_verifier,
        redirect_uri=payload.redirect_uri,
    )
    access_token, refresh_token, expires_at, refresh_expires_at = issue_token_pair(identity)
    return AppLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        refresh_expires_at=refresh_expires_at,
        account_id=identity.account_id,
        display_name=identity.display_name,
        social_user_id=identity.social_user_id,
    )


@router.post("/auth/refresh", response_model=AppLoginResponse)
async def refresh_token(payload: AppRefreshRequest) -> AppLoginResponse:
    identity = resolve_refresh_token(payload.refresh_token)
    access_token, refresh_token_value, expires_at, refresh_expires_at = issue_token_pair(identity)
    return AppLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token_value,
        refresh_expires_at=refresh_expires_at,
        expires_at=expires_at,
        account_id=identity.account_id,
        display_name=identity.display_name,
        social_user_id=identity.social_user_id,
    )


@router.get("/me")
async def me(identity: AppIdentity = Depends(require_app_identity)) -> dict:
    return {
        "account_id": identity.account_id,
        "display_name": identity.display_name,
        "social_user_id": identity.social_user_id,
        "expires_at": identity.expires_at,
    }


@router.get("/push/status")
async def app_push_status(identity: AppIdentity = Depends(require_app_identity)) -> dict:
    """Return provider status without exposing provider credentials."""
    del identity
    from app.social.push_service import get_unified_push_service

    return get_unified_push_service().status()


@router.post("/push/devices")
async def register_app_push_device(
    payload: AppPushDeviceRequest,
    identity: AppIdentity = Depends(require_app_identity),
) -> dict:
    """Bind the current App account to a provider-neutral device identifier."""
    provider = payload.provider.strip().lower()
    platform = payload.platform.strip().lower()
    if provider != "getui":
        raise HTTPException(status_code=400, detail="unsupported_push_provider")
    if platform != "android":
        raise HTTPException(status_code=400, detail="unsupported_app_platform")
    from app.social.push_service import PushDeviceStore, get_unified_push_service

    device = await PushDeviceStore().upsert(
        identity.social_user_id,
        provider=provider,
        device_id=payload.device_id.strip(),
        platform=platform,
        app_id=payload.app_id,
    )
    return {"registered": True, "device": device, "push": get_unified_push_service().status()}


@router.delete("/push/devices/{device_id}")
async def unregister_app_push_device(
    device_id: str,
    identity: AppIdentity = Depends(require_app_identity),
) -> dict:
    from app.social.push_service import PushDeviceStore

    removed = await PushDeviceStore().remove(identity.social_user_id, device_id.strip(), provider="getui")
    return {"removed": removed}


@router.post("/voice/transcribe", response_model=AppVoiceResponse)
async def transcribe_voice(
    file: UploadFile = File(...),
    language: str = Form(default="zh"),
    identity: AppIdentity = Depends(require_app_identity),
) -> AppVoiceResponse:
    del identity  # Authentication is enforced by the dependency above.
    from app.services.voice_service import (
        VoiceConfigError,
        ensure_allowed_audio_upload,
        normalize_audio_for_mimo,
        transcribe_with_mimo,
    )

    audio_bytes = await file.read()
    try:
        ensure_allowed_audio_upload(
            filename=file.filename or "voice.m4a",
            content_type=file.content_type or "",
            size=len(audio_bytes),
        )
        normalized_bytes, normalized_mime = await normalize_audio_for_mimo(
            audio_bytes,
            filename=file.filename or "voice.m4a",
            content_type=file.content_type or "",
        )
        text = await transcribe_with_mimo(normalized_bytes, normalized_mime, language=language)
        return AppVoiceResponse(text=text, language=language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VoiceConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    identity: AppIdentity = Depends(require_app_identity),
) -> dict:
    """Upload an attachment through the same safe resource pipeline as Web."""
    from app.api.upload_routes import upload_chat_file
    session_id = await _ensure_session(request, identity, None)
    return await upload_chat_file(
        file=file,
        session_id=session_id,
        mode="social",
        db=db,
        user=identity.as_current_user(),
        catalog=get_conversation_catalog(),
    )


@router.get("/broadcasts")
async def app_broadcasts(identity: AppIdentity = Depends(require_app_identity)) -> dict:
    """Return the authenticated App account's persistent broadcast inbox."""
    from app.social.broadcast_context import load_broadcast_messages

    messages = [
        _broadcast_payload(item)
        for item in await load_broadcast_messages(identity.social_user_id)
    ]
    return {
        "messages": messages,
        "unread_count": sum(1 for item in messages if not item["read"]),
    }


@router.post("/broadcasts/{message_id}/read")
async def app_mark_broadcast_read(
    message_id: str,
    identity: AppIdentity = Depends(require_app_identity),
) -> dict:
    """Mark one broadcast as read; repeated calls are idempotent."""
    from app.social.broadcast_context import mark_broadcast_read
    from app.social.broadcast_context import load_broadcast_messages

    messages = await load_broadcast_messages(identity.social_user_id)
    if not any(str(item.get("id")) == message_id for item in messages):
        raise HTTPException(status_code=404, detail="broadcast_not_found")
    changed = await mark_broadcast_read(identity.social_user_id, message_id)
    return {"message_id": message_id, "read": True, "changed": changed}


@router.post("/broadcasts/read-all")
async def app_mark_all_broadcasts_read(
    identity: AppIdentity = Depends(require_app_identity),
) -> dict:
    """Mark all broadcasts in the inbox as read."""
    from app.social.broadcast_context import mark_broadcast_read

    changed = await mark_broadcast_read(identity.social_user_id)
    return {"read_all": True, "changed": changed}


async def _resolve_broadcast_attachment(
    message_id: str,
    index: int,
    identity: AppIdentity,
) -> Path:
    """Resolve one broadcast attachment of the caller's inbox to a local file."""
    from app.social.broadcast_context import load_broadcast_messages

    messages = await load_broadcast_messages(identity.social_user_id)
    message = next(
        (item for item in messages if isinstance(item, dict) and str(item.get("id")) == message_id),
        None,
    )
    if message is None:
        raise HTTPException(status_code=404, detail="broadcast_not_found")
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else []
    if index < 0 or index >= len(attachments) or not isinstance(attachments[index], dict):
        raise HTTPException(status_code=404, detail="broadcast_attachment_not_found")
    raw_path = str(attachments[index].get("path") or "").strip()
    if not raw_path:
        raise HTTPException(status_code=404, detail="broadcast_attachment_content_unavailable")
    registry_root = get_data_registry().expanduser().resolve()
    target = Path(raw_path).expanduser().resolve()
    try:
        target.relative_to(registry_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="broadcast_attachment_path_forbidden") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="broadcast_attachment_content_missing")
    return target


async def _broadcast_attachment_name(
    message_id: str,
    index: int,
    identity: AppIdentity,
) -> str:
    """Return the stored display name of one broadcast attachment."""
    from app.social.broadcast_context import load_broadcast_messages

    messages = await load_broadcast_messages(identity.social_user_id)
    message = next(
        (item for item in messages if isinstance(item, dict) and str(item.get("id")) == message_id),
        None,
    )
    if message is None:
        raise HTTPException(status_code=404, detail="broadcast_not_found")
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else []
    if index < 0 or index >= len(attachments) or not isinstance(attachments[index], dict):
        raise HTTPException(status_code=404, detail="broadcast_attachment_not_found")
    attachment = attachments[index]
    target_name = Path(str(attachment.get("path") or "attachment")).name
    return str(attachment.get("name") or attachment.get("filename") or target_name)


@router.get("/broadcasts/{message_id}/attachments/{index}/content")
async def app_broadcast_attachment_content(
    message_id: str,
    index: int,
    identity: AppIdentity = Depends(require_app_identity),
) -> FileResponse:
    """Stream one broadcast attachment to its owner.

    The persisted attachment keeps the server filesystem path; this endpoint
    resolves it server-side so the path never reaches the client.
    """
    target = await _resolve_broadcast_attachment(message_id, index, identity)
    filename = await _broadcast_attachment_name(message_id, index, identity)
    media_type = str(mimetypes.guess_type(filename)[0] or "application/octet-stream")
    return FileResponse(target, media_type=media_type, filename=filename)


@router.get("/broadcasts/{message_id}/attachments/{index}/preview")
async def app_broadcast_attachment_preview(
    message_id: str,
    index: int,
    identity: AppIdentity = Depends(require_app_identity),
) -> FileResponse:
    """Serve a cached PDF rendition of one broadcast Office attachment.

    Mirrors the chat-upload preview pipeline (LibreOffice -> <file>.preview.pdf)
    because the Android App renders Office documents via PDF previews only.
    """
    import asyncio

    from app.api.upload_routes import _office_pdf_preview

    target = await _resolve_broadcast_attachment(message_id, index, identity)
    if target.suffix.lower() not in {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}:
        raise HTTPException(status_code=404, detail="broadcast_preview_not_supported")
    cached = target.with_suffix(".preview.pdf")
    if not cached.is_file():
        preview = await asyncio.to_thread(_office_pdf_preview, str(target))
        if preview is None:
            raise HTTPException(status_code=503, detail="broadcast_preview_generation_failed")
        cached = preview
    filename = await _broadcast_attachment_name(message_id, index, identity)
    return FileResponse(cached, media_type="application/pdf", filename=f"{Path(filename).stem}.pdf")


def _session_mapper(request: Request) -> SessionMapper:
    mapper = getattr(request.app.state, "session_mapper", None)
    if mapper is None:
        mapper = SessionMapper()
        request.app.state.session_mapper = mapper
    return mapper


async def _loaded_session_mapper(request: Request) -> SessionMapper:
    mapper = _session_mapper(request)
    if not getattr(request.app.state, "social_app_session_mapper_loaded", False):
        await mapper.load()
        request.app.state.social_app_session_mapper_loaded = True
    return mapper


async def _get_agent():
    from app.agent.react_agent import create_react_agent

    global _agent
    if _agent is None:
        async with _agent_lock:
            if _agent is None:
                _agent = create_react_agent()
    return _agent


async def _get_memory_store(identity: AppIdentity):
    from app.social.memory_store import ImprovedMemoryStore

    store = _memory_managers.get(identity.social_user_id)
    if store is None:
        store = ImprovedMemoryStore(user_id=identity.social_user_id)
        _memory_managers[identity.social_user_id] = store
    return store


def _social_preferences(identity: AppIdentity) -> dict:
    from app.social.user_preferences import UserPreferences

    manager = UserPreferences(identity.social_user_id)
    preferences = manager.get_preferences() or {}
    return {
        "social_user_preferences": preferences,
        "social_soul_file_path": str(manager.soul_file.resolve()) if manager.soul_file else None,
        "social_user_file_path": str(manager.user_file.resolve()) if manager.user_file else None,
        "social_heartbeat_file_path": str(manager.heartbeat_file.resolve()) if manager.heartbeat_file else None,
        "social_soul_context": manager.load_soul_md(),
        "social_user_context": manager.load_user_md(),
    }


async def _ensure_session(
    request: Request,
    identity: AppIdentity,
    requested_session_id: str | None,
) -> str:
    mapper = await _loaded_session_mapper(request)
    if requested_session_id:
        # The mapper intentionally stores only the user's current session.
        # Historical App sessions are authorized by the catalog instead.
        row = await get_conversation_catalog().find(requested_session_id)
        if (
            row is None
            or row.owner_user_id != identity.social_user_id
            or row.source != ConversationSource.SOCIAL
        ):
            raise HTTPException(status_code=404, detail="session_not_found")
        session_id = requested_session_id
    else:
        session_id = await mapper.get_or_create_session(identity.social_user_id, mode="social")

    catalog = get_conversation_catalog()
    await catalog.register_identity(
        session_id=session_id,
        owner_user_id=identity.social_user_id,
        owner_username=identity.account_id,
        owner_display_name=identity.display_name,
        source=ConversationSource.SOCIAL,
        mode="social",
        title=None,
        read_only_on_web=True,
    )
    return session_id


async def _persist_app_turn(
    session_id: str,
    query: str,
    display_history: list[dict],
) -> None:
    """Persist the App-visible transcript for a completed streaming turn."""
    from app.agent.session.models import Session
    from app.agent.session.session_resolver import (
        append_session_transcript_for_mode,
        load_session_for_mode,
    )
    from app.agent.session.conversation_persistence import ConversationPersistenceService

    session = await load_session_for_mode(session_id, mode="social")
    if session is None:
        session = Session(session_id=session_id, query=query)
    elif not session.query:
        session.query = query

    ConversationPersistenceService().append_complete(
        session,
        display_history=display_history,
    )
    saved = await append_session_transcript_for_mode(session, mode="social")
    if not saved:
        raise RuntimeError("app_transcript_save_failed")


async def _sanitize_attachments(
    db: AsyncSession,
    session_id: str,
    attachments: list[dict],
) -> list[dict]:
    if not attachments:
        return []
    file_ids = {
        str(item.get("file_id") or "").strip()
        for item in attachments
        if isinstance(item, dict)
    }
    file_ids.discard("")
    if len(file_ids) != len(attachments):
        raise HTTPException(status_code=400, detail="invalid_attachment")
    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id.in_(file_ids),
            UploadedFile.session_id == session_id,
        )
    )
    rows = {row.id: row for row in result.scalars().all()}
    if set(rows) != file_ids:
        raise HTTPException(status_code=404, detail="attachment_not_found")
    return [
        {
            "file_id": row.id,
            "name": row.filename,
            "filename": row.filename,
            "type": row.file_type,
            "mime_type": row.mime_type,
            "url": f"/api/upload/{row.id}",
        }
        for row in (rows[str(item["file_id"]).strip()] for item in attachments)
    ]


def _app_resource_descriptor(session_id: str, resource, *, preview_resource=None, variants=None) -> dict:
    """Expose only safe, App-readable metadata for an output resource."""
    media_type = str(resource.media_type or "application/octet-stream")
    label = str(resource.label or resource.metadata.get("filename") or "附件")
    file_type = "image" if media_type.lower().startswith("image/") else "document"
    descriptor = {
        "file_id": resource.resource_id,
        "resource_id": resource.resource_id,
        "ref_id": resource.resource_id,
        "filename": label,
        "name": label,
        "file_type": file_type,
        "type": file_type,
        "mime_type": media_type,
        "url": f"/api/social/app/sessions/{session_id}/resources/{resource.resource_id}/content",
        "download_url": f"/api/social/app/sessions/{session_id}/resources/{resource.resource_id}/content",
        "format": resource.format,
    }
    if preview_resource is not None:
        descriptor["preview_url"] = f"/api/social/app/sessions/{session_id}/resources/{preview_resource.resource_id}/content"
        descriptor["preview_mime_type"] = str(preview_resource.media_type or "application/pdf")
    if variants:
        descriptor["variants"] = variants
    return descriptor


def _app_resource_variant(session_id: str, resource) -> dict:
    label = str(resource.label or resource.metadata.get("filename") or "附件")
    return {
        "format": str(resource.format or "file").lower(),
        "filename": label,
        "name": label,
        "mime_type": str(resource.media_type or "application/octet-stream"),
        "url": f"/api/social/app/sessions/{session_id}/resources/{resource.resource_id}/content",
    }


async def _app_resource_descriptors(session_id: str, resource_ids: list[str]) -> list[dict]:
    service = SessionResourceService.database()
    page = await service.list_resources(session_id, status="active", limit=200)
    resources = [
        item for item in page.resources
        if item.role in {"output", "report", "attachment"}
        and item.kind in {"data", "file", "artifact", "visual"}
    ]
    requested = {str(item) for item in resource_ids if str(item).strip()}
    if requested:
        requested |= {
            item.parent_resource_id for item in resources
            if item.resource_id in requested and item.parent_resource_id
        }
        resources = [
            item for item in resources
            if item.resource_id in requested or item.parent_resource_id in requested
        ]
    by_parent = {item.parent_resource_id: item for item in resources if item.relation == "preview" and item.parent_resource_id}
    children_by_parent: dict[str, list] = {}
    for item in resources:
        if item.parent_resource_id and item.relation in {"preview", "rendition"}:
            children_by_parent.setdefault(item.parent_resource_id, []).append(item)

    descriptors = []
    for item in resources:
        if item.relation == "preview":
            continue
        # QMD remains an internal report source. In social mode expose the
        # rendered HTML as the primary card and keep other deliverables as
        # download variants, without returning the .qmd source itself.
        if str(item.format or "").lower() == "qmd":
            children = children_by_parent.get(item.resource_id, [])
            html_preview = next(
                (
                    child
                    for child in children
                    if child.relation == "preview"
                    and (
                        str(child.format or "").lower() in {"html", "htm"}
                        or str(child.media_type or "").lower() == "text/html"
                    )
                ),
                None,
            )
            if html_preview is None:
                continue
            variants = [
                _app_resource_variant(session_id, child)
                for child in children
                if child is not html_preview
                and str(child.format or "").lower() not in {"qmd", "md", "markdown"}
            ]
            descriptor = _app_resource_descriptor(session_id, html_preview, variants=variants)
            descriptor["report_id"] = str(item.metadata.get("report_id") or item.label or item.resource_id)
            descriptors.append(descriptor)
            continue
        descriptors.append(_app_resource_descriptor(session_id, item, preview_resource=by_parent.get(item.resource_id)))

    # A single Agent run can publish the same named deliverable more than once
    # while retrying generation.  The mobile transcript should expose one card
    # per deliverable; prefer the copy that has a usable preview over an older
    # copy without a derivative preview.
    deduplicated: dict[tuple[str, str], dict] = {}
    for descriptor in descriptors:
        key = (
            str(descriptor.get("filename") or descriptor.get("name") or "").strip().lower(),
            str(descriptor.get("mime_type") or descriptor.get("format") or "").strip().lower(),
        )
        if not key[0]:
            continue
        current = deduplicated.get(key)
        if current is None or (descriptor.get("preview_url") and not current.get("preview_url")):
            deduplicated[key] = descriptor
    return list(deduplicated.values())


async def _stream_events(
    identity: AppIdentity,
    session_id: str,
    query: str,
    attachments: list[dict] | None = None,
) -> AsyncIterator[str]:
    from app.agent.runtime.cancellation import cancellation_registry

    agent = await _get_agent()
    memory_store = await _get_memory_store(identity)
    social_context = _social_preferences(identity)
    cancel_event = await cancellation_registry.register(session_id)
    display_history: list[dict] = [{
        "type": "user",
        "role": "user",
        "content": query,
        "attachments": attachments or [],
        "timestamp": datetime.now().isoformat(),
    }]
    streamed_answer = ""
    streamed_resources: list[dict] = []
    persisted = False
    # 与 agent_bridge 处理微信/QQ 入站消息保持一致：为本次 agent 运行设置
    # social 上下文，使 send_notification 等工具能解析当前发送通道。
    from app.social.message_bus_singleton import reset_current_context, set_current_context

    social_user_parts = identity.social_user_id.rsplit(":", 2)
    if len(social_user_parts) == 3:
        context_channel, context_bot_account, context_chat_id = social_user_parts
    else:
        context_channel, context_bot_account, context_chat_id = "app", "android", identity.account_id
    context_tokens = set_current_context(
        channel=context_channel,
        chat_id=context_chat_id,
        bot_account=context_bot_account,
    )
    try:
        await cancellation_registry.arm_run_task(session_id, cancel_event)
        async for event in agent.analyze(
            user_query=query,
            session_id=session_id,
            manual_mode="social",
            session_storage_mode="social",
            user_identifier=identity.social_user_id,
            social_memory_store=memory_store,
            **social_context,
            attachments=attachments or None,
            cancel_event=cancel_event,
        ):
            event_type = event.get("type")
            event_data = event.get("data") if isinstance(event.get("data"), dict) else {}
            if event_type == "streaming_text":
                streamed_answer += str(event_data.get("chunk") or "")
            elif event_type == "resources_changed":
                descriptors = await _app_resource_descriptors(
                    session_id,
                    [str(item) for item in event_data.get("changed_resource_ids") or []],
                )
                if descriptors:
                    streamed_resources.extend(descriptors)
                    event_data["attachments"] = descriptors
            elif event_type == "complete":
                answer = str(event_data.get("answer") or streamed_answer).strip()
                if answer:
                    final_attachments = list(streamed_resources)
                    if final_attachments:
                        event_data["attachments"] = final_attachments
                    display_history.append({
                        "type": "final",
                        "role": "assistant",
                        "content": answer,
                        "attachments": final_attachments,
                        "data": event_data,
                        "timestamp": event_data.get("timestamp") or datetime.now().isoformat(),
                    })
                await _persist_app_turn(session_id, query, display_history)
                persisted = True
            elif event_type in {"incomplete", "interrupted", "fatal_error"}:
                content = (
                    event_data.get("answer")
                    or event_data.get("reason")
                    or event_data.get("error")
                    or event_data.get("message")
                    or "本轮对话未完成"
                )
                display_history.append({
                    "type": event_type,
                    "role": "assistant",
                    "content": str(content),
                    "data": event_data,
                    "timestamp": event_data.get("timestamp") or datetime.now().isoformat(),
                })
                await _persist_app_turn(session_id, query, display_history)
                persisted = True
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        error = {"type": "fatal_error", "data": {"error": str(exc), "code": "app_agent_failed"}}
        yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
    finally:
        reset_current_context(context_tokens)
        # A disconnected client can cancel the stream before a terminal event.
        # Keep the user message so the session remains auditable and does not
        # appear to have been silently dropped.
        if not persisted:
            try:
                await _persist_app_turn(session_id, query, display_history)
            except Exception as exc:
                logger.warning("app_transcript_save_on_disconnect_failed", session_id=session_id, error=str(exc))
        await cancellation_registry.unregister(session_id, cancel_event)


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    payload: AppChatRequest,
    db: AsyncSession = Depends(get_db),
    identity: AppIdentity = Depends(require_app_identity),
) -> StreamingResponse:
    session_id = await _ensure_session(request, identity, payload.session_id)
    attachments = await _sanitize_attachments(db, session_id, payload.attachments)
    response = StreamingResponse(
        _stream_events(identity, session_id, payload.query, attachments),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Session-Id": session_id},
    )
    return response


@router.get("/sessions")
async def sessions(request: Request, identity: AppIdentity = Depends(require_app_identity)) -> list[dict]:
    catalog = get_conversation_catalog()
    try:
        rows = await catalog.list_visible(identity.as_current_user(), limit=100)
    except Exception:
        rows = []
    rows = [row for row in rows if row.source == ConversationSource.SOCIAL]
    if rows:
        return [
            {
                "session_id": row.session_id,
                "mode": row.mode or "social",
                "title": row.title or "新对话",
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ]
    mapper = await _loaded_session_mapper(request)
    session_id = await mapper.get_session(identity.social_user_id)
    return [{"session_id": session_id, "mode": "social", "title": "新对话"}] if session_id else []


@router.post("/sessions")
async def create_app_session(request: Request, identity: AppIdentity = Depends(require_app_identity)) -> dict:
    """Create and persist a new Android App conversation session."""
    mapper = await _loaded_session_mapper(request)
    session_id = mapper.new_session_id(mode="social")
    await mapper.save_mapping(identity.social_user_id, session_id)
    await get_conversation_catalog().register_identity(
        session_id=session_id,
        owner_user_id=identity.social_user_id,
        owner_username=identity.account_id,
        owner_display_name=identity.display_name,
        source=ConversationSource.SOCIAL,
        mode="social",
        title="新对话",
        read_only_on_web=True,
    )
    return {"session_id": session_id, "mode": "social", "title": "新对话"}


@router.patch("/sessions/{session_id}")
async def rename_app_session(
    session_id: str,
    payload: AppRenameSessionRequest,
    identity: AppIdentity = Depends(require_app_identity),
) -> dict:
    catalog = get_conversation_catalog()
    row = await catalog.require_read(session_id, identity.as_current_user())
    if row.source != ConversationSource.SOCIAL:
        raise HTTPException(status_code=404, detail="session_not_found")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title_required")
    if not await catalog.rename(session_id, title):
        raise HTTPException(status_code=404, detail="session_not_found")
    return {"session_id": session_id, "title": title}


@router.delete("/sessions/{session_id}")
async def delete_app_session(
    request: Request,
    session_id: str,
    identity: AppIdentity = Depends(require_app_identity),
) -> dict:
    catalog = get_conversation_catalog()
    row = await catalog.require_read(session_id, identity.as_current_user())
    if row.source != ConversationSource.SOCIAL:
        raise HTTPException(status_code=404, detail="session_not_found")
    from app.conversations.adapters import get_conversation_adapters

    await get_conversation_adapters().get(row.source).delete(row)
    deleted = await catalog.delete(session_id)
    mapper = await _loaded_session_mapper(request)
    if await mapper.get_session(identity.social_user_id) == session_id:
        await mapper.delete_mapping(identity.social_user_id)
    return {"session_id": session_id, "deleted": bool(deleted)}


@router.get("/sessions/{session_id}/messages")
async def app_session_messages(session_id: str, identity: AppIdentity = Depends(require_app_identity)) -> dict:
    """Restore the latest messages for an App-owned conversation."""
    catalog = get_conversation_catalog()
    row = await catalog.require_read(session_id, identity.as_current_user())
    if row.source != ConversationSource.SOCIAL:
        raise HTTPException(status_code=404, detail="session_not_found")
    from app.conversations.adapters import get_conversation_adapters

    restored = await get_conversation_adapters().get(row.source).restore(
        row, message_limit=100, lazy_artifacts=True
    )
    if not restored:
        return {"session_id": session_id, "messages": []}
    payload = restored.get("normalized_session") or {}
    history = list(payload.get("conversation_history") or [])
    # Resource outputs are stored in the session resource catalog separately
    # from the text transcript. Project them onto the latest assistant turn so
    # the Android history view can render generated images/files as well.
    try:
        descriptors = await _app_resource_descriptors(session_id, [])
        if descriptors:
            for item in reversed(history):
                role = str(item.get("role") or item.get("type") or "").lower() if isinstance(item, dict) else ""
                if role in {"assistant", "final"}:
                    existing = item.get("attachments") if isinstance(item.get("attachments"), list) else []
                    known = {str(value.get("file_id") or value.get("resource_id") or value.get("url") or "") for value in existing if isinstance(value, dict)}
                    item["attachments"] = existing + [value for value in descriptors if value["file_id"] not in known]
                    break
    except Exception as exc:
        logger.warning("app_session_resources_restore_failed", session_id=session_id, error=str(exc))
    return {"session_id": session_id, "messages": history}


@router.get("/sessions/{session_id}/resources")
async def app_session_resources(
    session_id: str,
    identity: AppIdentity = Depends(require_app_identity),
) -> dict:
    """List user-visible generated resources for the Android App."""
    row = await get_conversation_catalog().require_read(session_id, identity.as_current_user())
    if row.source != ConversationSource.SOCIAL:
        raise HTTPException(status_code=404, detail="session_not_found")
    return {
        "session_id": session_id,
        "resources": await _app_resource_descriptors(session_id, []),
    }


@router.get("/sessions/{session_id}/resources/{resource_id}/content")
async def app_session_resource_content(
    session_id: str,
    resource_id: str,
    identity: AppIdentity = Depends(require_app_identity),
) -> FileResponse:
    """Serve generated resource bytes to the authenticated Android App."""
    row = await get_conversation_catalog().require_read(session_id, identity.as_current_user())
    if row.source != ConversationSource.SOCIAL:
        raise HTTPException(status_code=404, detail="session_not_found")
    resource = await SessionResourceService.database().get_resource(session_id, resource_id, status="active")
    if resource is None or resource.role not in {"output", "report", "attachment"} or resource.kind not in {"data", "file", "artifact", "visual"}:
        raise HTTPException(status_code=404, detail="resource_not_found")
    raw_path = str((resource.locator or {}).get("path") or "").strip()
    if not raw_path:
        raise HTTPException(status_code=404, detail="resource_content_unavailable")
    registry_root = get_data_registry().expanduser().resolve()
    target = Path(raw_path).expanduser().resolve()
    if resource.kind == "artifact" and resource.metadata.get("entrypoint"):
        target = (target / str(resource.metadata["entrypoint"])).resolve()
    try:
        target.relative_to(registry_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="resource_path_forbidden") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="resource_content_missing")
    media_type = str(resource.media_type or mimetypes.guess_type(target.name)[0] or "application/octet-stream")
    return FileResponse(target, media_type=media_type, filename=resource.label or target.name)


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(
    request: Request,
    session_id: str,
    identity: AppIdentity = Depends(require_app_identity),
) -> dict:
    from app.agent.runtime.cancellation import cancellation_registry

    await _ensure_session(request, identity, session_id)
    cancelled = await cancellation_registry.cancel(session_id, reason="app_user_cancelled")
    return {"session_id": session_id, "cancelled": bool(cancelled)}


@router.post("/sessions/{session_id}/steer")
async def steer_session(
    request: Request,
    session_id: str,
    payload: AppSteerRequest,
    identity: AppIdentity = Depends(require_app_identity),
) -> dict:
    from app.agent.runtime.steering import steering_registry

    await _ensure_session(request, identity, session_id)
    accepted = await steering_registry.add_input(session_id, payload.message)
    return {"session_id": session_id, "accepted": bool(accepted)}

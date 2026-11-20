"""微信群 RPA 推送队列 API：本机推送 agent 取消息/回执，管理侧查积压与心跳。

鉴权与 dashboard 直连令牌同构：中间件按部署级前缀+Bearer 令牌放行，
路由层复核同一令牌（防中间件漏配时令牌直接命中路由）；管理员登录身份
也放行，便于浏览器直接排查 /status。
"""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth.dependencies import optional_current_user
from app.auth.models import CurrentUser
from app.scenarios.xuchang_station_deviation import wechat_push_queue as queue
from app.utils.path_config import (
    get_data_registry,
    is_agent_sensitive_path,
    is_path_within,
    resolve_agent_path,
)

router = APIRouter(prefix="/api/xuchang-wechat-push", tags=["xuchang-wechat-push"])

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

# 文档附件默认拒绝：只放行业务报告常用格式，未知后缀不下发。
_ATTACHMENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}
_MAX_ATTACHMENT_SIZE = 50 * 1024 * 1024


def _configured_token() -> str:
    from config.settings import settings

    return settings.xuchang_wechat_push_token


def _bearer_token(request: Request) -> str:
    scheme, separator, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not separator:
        return ""
    return token.strip()


async def require_push_agent(
    request: Request,
    user: CurrentUser | None = Depends(optional_current_user),
) -> CurrentUser | None:
    if user is not None:
        if not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="wechat_push_admin_only",
            )
        return user
    configured = _configured_token()
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="wechat_push_disabled",
        )
    supplied = _bearer_token(request)
    if supplied and hmac.compare_digest(supplied, configured):
        return None
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication_required",
    )


class AckPayload(BaseModel):
    id: str
    status: str  # sent | failed
    detail: Optional[str] = None
    agent_id: Optional[str] = None


@router.get("/pending")
async def list_pending(
    request: Request,
    limit: int = 10,
    agent_id: Optional[str] = None,
    _: CurrentUser | None = Depends(require_push_agent),
) -> dict:
    # 新版 agent 用 caps=attachments 上报文件附件能力；旧 agent 不带该能力，
    # 带附件消息留在 pending，避免文本发出后附件被静默丢弃。
    caps = {part.strip() for part in (request.query_params.get("caps") or "").split(",") if part.strip()}
    queue.record_agent_heartbeat({"agent_id": agent_id} if agent_id else None)
    messages = queue.list_pending_messages(
        limit, supports_attachments="attachments" in caps
    )
    queue.cleanup_archive()
    return {"messages": messages, "count": len(messages)}


@router.post("/ack")
async def ack_message(
    payload: AckPayload,
    _: CurrentUser | None = Depends(require_push_agent),
) -> dict:
    try:
        result = queue.ack_message(payload.id, payload.status, detail=payload.detail)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    queue.record_agent_heartbeat(
        {"agent_id": payload.agent_id} if payload.agent_id else None
    )
    return {"id": payload.id, "result": result}


@router.get("/status")
async def push_status(_: CurrentUser | None = Depends(require_push_agent)) -> dict:
    return queue.push_status_snapshot()


@router.get("/media/{message_id}/{index}")
async def get_media(
    message_id: str,
    index: int,
    _: CurrentUser | None = Depends(require_push_agent),
) -> FileResponse:
    """下发告警通报的证据附图：pending 优先，已归档消息兜底（供补图排障）。"""
    if index < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_media_index"
        )
    record = queue.find_message(message_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="message_not_found"
        )
    media = record.get("media") or []
    if index >= len(media):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="media_index_out_of_range"
        )
    try:
        path = resolve_agent_path(str(media[index]))
    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"invalid_media_path: {exc}"
        ) from exc
    # 附图只允许来自 data registry（入队数据是 worker 受信收集，仍复核边界）
    if not is_path_within(path, [get_data_registry()]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="media_outside_registry"
        )
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="media_file_missing"
        )
    return FileResponse(
        path, media_type=_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    )


def _attachment_display_name(item: dict, path) -> str:
    raw = str(item.get("filename") or "").strip() or path.name
    name = Path(raw.replace("\\", "/")).name
    name = name.replace('"', "").replace("\r", "").replace("\n", "").strip()
    return name[:120] or path.name


@router.get("/attachment/{message_id}/{index}")
async def get_attachment(
    message_id: str,
    index: int,
    _: CurrentUser | None = Depends(require_push_agent),
) -> FileResponse:
    """下发报告等文档附件：白名单默认拒绝，路径/大小/敏感文件逐项守门。"""
    if index < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_attachment_index"
        )
    record = queue.find_message(message_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="message_not_found"
        )
    attachments = record.get("attachments") or []
    if index >= len(attachments):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="attachment_index_out_of_range"
        )
    item = attachments[index]
    if not isinstance(item, dict) or not str(item.get("path") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="invalid_attachment_record"
        )
    try:
        path = resolve_agent_path(str(item["path"]))
    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"invalid_attachment_path: {exc}"
        ) from exc
    # 与附图同边界：只允许 data registry 内的非敏感文件。
    if not is_path_within(path, [get_data_registry()]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="attachment_outside_registry"
        )
    if is_agent_sensitive_path(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="attachment_sensitive_path"
        )
    media_type = _ATTACHMENT_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unsupported_attachment_type"
        )
    try:
        attachment_size = path.stat().st_size
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="attachment_file_missing"
        ) from exc
    if attachment_size > _MAX_ATTACHMENT_SIZE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="attachment_too_large"
        )
    return FileResponse(
        path,
        media_type=media_type,
        filename=_attachment_display_name(item, path),
    )

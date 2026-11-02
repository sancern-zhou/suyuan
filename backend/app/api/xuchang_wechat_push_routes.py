"""微信群 RPA 推送队列 API：本机推送 agent 取消息/回执，管理侧查积压与心跳。

鉴权与 dashboard 直连令牌同构：中间件按部署级前缀+Bearer 令牌放行，
路由层复核同一令牌（防中间件漏配时令牌直接命中路由）；管理员登录身份
也放行，便于浏览器直接排查 /status。
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth.dependencies import optional_current_user
from app.auth.models import CurrentUser
from app.scenarios.xuchang_station_deviation import wechat_push_queue as queue
from app.utils.path_config import get_data_registry, is_path_within, resolve_agent_path

router = APIRouter(prefix="/api/xuchang-wechat-push", tags=["xuchang-wechat-push"])

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


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
    limit: int = 10,
    agent_id: Optional[str] = None,
    _: CurrentUser | None = Depends(require_push_agent),
) -> dict:
    queue.record_agent_heartbeat({"agent_id": agent_id} if agent_id else None)
    messages = queue.list_pending_messages(limit)
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

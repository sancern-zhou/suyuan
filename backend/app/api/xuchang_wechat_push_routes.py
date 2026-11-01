"""微信群 RPA 推送队列 API：本机推送 agent 取消息/回执，管理侧查积压与心跳。

鉴权与 dashboard 直连令牌同构：中间件按部署级前缀+Bearer 令牌放行，
路由层复核同一令牌（防中间件漏配时令牌直接命中路由）；管理员登录身份
也放行，便于浏览器直接排查 /status。
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.auth.dependencies import optional_current_user
from app.auth.models import CurrentUser
from app.scenarios.xuchang_station_deviation import wechat_push_queue as queue

router = APIRouter(prefix="/api/xuchang-wechat-push", tags=["xuchang-wechat-push"])


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

"""External single sign-on endpoints (public)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config.settings import Settings, settings

from .errors import AuthenticationRejected, AuthenticationUnavailable
from .models import CurrentUser
from .sso import SsoSessionStore, SsoTicketError, SsoTicketService, build_sso_user

router = APIRouter(tags=["Authentication"])
logger = structlog.get_logger(__name__)


class SsoExchangeRequest(BaseModel):
    ticket: str = Field(default="", max_length=8192)


def get_auth_settings() -> Settings:
    return settings


def ticket_service(auth_settings: Settings) -> SsoTicketService | None:
    secret = (auth_settings.sso_shared_secret or "").strip()
    if not secret:
        return None
    return SsoTicketService(secret, ttl_seconds=auth_settings.sso_ticket_ttl_seconds)


def session_store(request: Request) -> SsoSessionStore:
    store = getattr(request.app.state, "sso_session_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="sso_unavailable")
    return store


async def resolve_user(
    request: Request,
    auth_settings: Settings,
    claims: dict,
) -> CurrentUser:
    """Prefer the upstream token: 身份以认证服务返回为准，票据声明只作兜底。"""
    upstream_token = str(claims.get("t") or "").strip()
    if upstream_token:
        auth_service = getattr(request.app.state, "auth_service", None)
        platform_client = getattr(auth_service, "_platform_client", None)
        if platform_client is not None:
            try:
                return await platform_client.get_current_user(
                    upstream_token, auth_settings.auth_sys_code
                )
            except AuthenticationRejected as exc:
                raise SsoTicketError("sso_upstream_token_rejected") from exc
            except AuthenticationUnavailable as exc:
                raise SsoTicketError("sso_upstream_unavailable") from exc
    return build_sso_user(
        claims,
        default_roles=auth_settings.sso_default_roles_set,
        admin_role_codes=auth_settings.auth_admin_role_codes_set,
        sys_code=auth_settings.auth_sys_code,
    )


@router.get("/auth/sso/config")
async def sso_config(auth_settings: Settings = Depends(get_auth_settings)):
    enabled = bool((auth_settings.sso_shared_secret or "").strip())
    return JSONResponse(
        {"enabled": enabled, "sysCode": auth_settings.auth_sys_code},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/auth/sso/exchange")
async def sso_exchange(
    payload: SsoExchangeRequest,
    request: Request,
    auth_settings: Settings = Depends(get_auth_settings),
):
    service = ticket_service(auth_settings)
    if service is None:
        raise HTTPException(status_code=404, detail="sso_disabled")
    try:
        claims = service.verify(payload.ticket)
        store = session_store(request)
        if not await store.consume_ticket(str(claims.get("j"))):
            raise SsoTicketError("sso_ticket_replayed")
        user = await resolve_user(request, auth_settings, claims)
        token = await store.issue(user)
    except SsoTicketError as exc:
        logger.warning("sso_exchange_rejected", reason=str(exc))
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    logger.info("sso_exchange_succeeded", user_id=user.id)
    return JSONResponse(
        {
            "token": token,
            "sysCode": auth_settings.auth_sys_code,
            "expiresIn": store.ttl_seconds,
            "user": {
                "id": user.id,
                "userName": user.username,
                "name": user.display_name,
                "roleCodes": list(user.role_codes),
                "isAdmin": user.is_admin,
                "sysCode": user.sys_code,
                "authSource": user.auth_source,
            },
        },
        headers={"Cache-Control": "no-store"},
    )

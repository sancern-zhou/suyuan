"""Authenticated endpoints supporting non-HTTP transports."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from config.settings import Settings, settings

from .dependencies import require_current_user
from .errors import AuthenticationRejected, AuthenticationUnavailable
from .models import CurrentUser
from .oauth_client import PlatformOAuthClient
from .service import build_mock_user
from .ws_tickets import WebSocketTicketService


router = APIRouter(tags=["Authentication"])


def get_ws_ticket_service(request: Request) -> WebSocketTicketService:
    return request.app.state.ws_ticket_service


def get_auth_settings() -> Settings:
    return settings


def get_oauth_client(request: Request) -> PlatformOAuthClient:
    client = getattr(request.app.state, "oauth_client", None)
    if not isinstance(client, PlatformOAuthClient):
        raise HTTPException(status_code=503, detail="oauth_not_configured")
    return client


async def _run_oauth(coro):
    """把 OAuth 客户端异常翻译成 HTTP 语义（拒绝=401，平台不可达=503）。"""
    try:
        return await coro
    except AuthenticationRejected as exc:
        # 平台拒绝（授权码一次性失效/回调地址不匹配等），原样透出便于定位
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AuthenticationUnavailable as exc:
        raise HTTPException(status_code=503, detail="oauth_unavailable") from exc


@router.get("/auth/oauth/exchange")
async def oauth_exchange(
    code: str = Query(..., min_length=1),
    redirectUri: str = Query(..., min_length=1),
    oauth: PlatformOAuthClient = Depends(get_oauth_client),
):
    """授权码换访问令牌：client_secret 只在服务端参与，浏览器侧不可见。"""
    if not oauth.configured:
        raise HTTPException(status_code=503, detail="oauth_not_configured")
    result = await _run_oauth(oauth.exchange_code(code.strip(), redirectUri.strip()))
    return {
        "accessToken": result.get("accessToken"),
        "refreshToken": result.get("refreshToken"),
        "expiresIn": result.get("expiresIn", result.get("expireIn")),
        "tokenType": result.get("tokenType", "bearer"),
    }


@router.get("/auth/oauth/refresh")
async def oauth_refresh(
    refreshToken: str = Query(..., min_length=1),
    oauth: PlatformOAuthClient = Depends(get_oauth_client),
):
    """刷新令牌续期访问令牌，避免用户在页面上遭遇一小时硬过期。"""
    if not oauth.configured:
        raise HTTPException(status_code=503, detail="oauth_not_configured")
    result = await _run_oauth(oauth.refresh(refreshToken.strip()))
    return {
        "accessToken": result.get("accessToken"),
        "refreshToken": result.get("refreshToken"),
        "expiresIn": result.get("expiresIn", result.get("expireIn")),
        "tokenType": result.get("tokenType", "bearer"),
    }


@router.get("/auth/runtime-config")
async def runtime_auth_config(
    auth_settings: Settings = Depends(get_auth_settings),
):
    payload = {
        "authMode": "company",
        "sysCode": auth_settings.auth_sys_code,
    }
    if auth_settings.auth_mode == "mock":
        user = build_mock_user(auth_settings)
        payload = {
            "authMode": "mock",
            "sysCode": user.sys_code,
            "mockUser": {
                "id": user.id,
                "userName": user.username,
                "name": user.display_name,
                "roleCodes": list(user.role_codes),
                "isAdmin": user.is_admin,
                "sysCode": user.sys_code,
                "authSource": user.auth_source,
            },
        }
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.get("/auth/me")
async def current_user_profile(
    user: CurrentUser = Depends(require_current_user),
):
    """当前登录用户（网关解析后的权威身份），前端会话建立/校验统一走这里。

    OAuth2.0 授权码 token 绑定业务应用，平台 getCurrentUser 需要业务 SysCode；
    该回退逻辑在服务端 PlatformAuthClient 内完成，浏览器侧不感知。
    """
    return {
        "id": user.id,
        "userName": user.username,
        "name": user.display_name,
        "roleCodes": list(user.role_codes),
        "isAdmin": user.is_admin,
        "sysCode": user.sys_code,
        "authSource": user.auth_source,
    }


@router.post("/auth/ws-ticket")
async def issue_ws_ticket(
    user: CurrentUser = Depends(require_current_user),
    service: WebSocketTicketService = Depends(get_ws_ticket_service),
):
    ticket = await service.issue(user, purpose="scheduled-tasks")
    return {"ticket": ticket, "expires_in": service.ttl_seconds}

"""Authenticated endpoints supporting non-HTTP transports."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from config.settings import Settings, settings

from .dependencies import require_admin_user, require_current_user
from .errors import AuthenticationRejected, AuthenticationUnavailable
from .models import CurrentUser
from .service import build_mock_user
from .session_tokens import issue_session_token
from .ws_tickets import WebSocketTicketService


router = APIRouter(tags=["Authentication"])


def get_ws_ticket_service(request: Request) -> WebSocketTicketService:
    return request.app.state.ws_ticket_service


def get_auth_settings() -> Settings:
    return settings


def get_auth_service(request: Request):
    return request.app.state.auth_service


def get_operation_access_policy(request: Request):
    return getattr(request.app.state, "operation_access_policy", None)


def _operation_access_denial(request: Request, user: CurrentUser) -> JSONResponse | None:
    """403 payload when the roster blocks this ops-platform account."""
    policy = get_operation_access_policy(request)
    if policy is None or user.auth_source != "operation":
        return None
    allowed, _reason = policy.decide(user.username)
    if allowed:
        return None
    return JSONResponse(
        {
            "detail": "operation_account_blocked",
            "message": "该账号所属单位无权访问智能体平台，如需使用请联系管理员",
        },
        status_code=403,
        headers={"Cache-Control": "no-store"},
    )


def _operation_user_payload(user: CurrentUser) -> dict:
    return {
        "id": user.id,
        "userName": user.username,
        "name": user.display_name,
        "roleCodes": list(user.role_codes),
        "isAdmin": user.is_admin,
        "sysCode": user.sys_code,
        "authSource": user.auth_source,
    }


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator:
        return ""
    return token.strip()


def _issued_session_token(user: CurrentUser, auth_settings: Settings) -> dict:
    secret = auth_settings.auth_session_token_secret.strip()
    if not secret or auth_settings.auth_session_token_ttl_seconds <= 0:
        return {}
    token, expires_in = issue_session_token(
        user,
        secret=secret,
        ttl_seconds=auth_settings.auth_session_token_ttl_seconds,
    )
    return {"sessionToken": token, "expiresIn": expires_in}


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
            "mockUser": _operation_user_payload(user),
        }
    elif auth_settings.auth_mode == "operation":
        payload = {
            "authMode": "operation",
            "sysCode": auth_settings.auth_sys_code,
            "loginUrl": "/Home/LogOn",
        }
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.post("/auth/operation-session")
async def operation_session(
    request: Request,
    auth_settings: Settings = Depends(get_auth_settings),
    service=Depends(get_auth_service),
):
    """Exchange the browser's ops-platform cookie for the resolved identity.

    Public by design: the only accepted credential is the ops-platform
    Forms cookie, which is always re-validated by the ops platform itself.
    """
    if auth_settings.auth_mode != "operation":
        return JSONResponse(
            {"detail": "operation_session_not_enabled"},
            status_code=404,
        )
    # A previously issued agent token wins (sliding renewal); otherwise the
    # ops Forms cookie is re-validated by the ops platform itself.
    user = service.resolve_session_token(_bearer_token(request))
    if user is None:
        cookie = request.cookies.get(auth_settings.auth_operation_cookie_name, "")
        if not cookie:
            return JSONResponse(
                {"detail": "authentication_required"}, status_code=401
            )
        try:
            user = await service.authenticate(
                cookie, auth_settings.auth_sys_code
            )
        except AuthenticationRejected:
            return JSONResponse(
                {"detail": "authentication_rejected"}, status_code=401
            )
        except AuthenticationUnavailable:
            return JSONResponse(
                {"detail": "authentication_unavailable"}, status_code=503
            )
    denial = _operation_access_denial(request, user)
    if denial is not None:
        return denial
    return JSONResponse(
        {
            "authenticated": True,
            "user": _operation_user_payload(user),
            **_issued_session_token(user, auth_settings),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/auth/ws-ticket")
async def issue_ws_ticket(
    user: CurrentUser = Depends(require_current_user),
    service: WebSocketTicketService = Depends(get_ws_ticket_service),
):
    ticket = await service.issue(user, purpose="scheduled-tasks")
    return {"ticket": ticket, "expires_in": service.ttl_seconds}


@router.get("/auth/operation-access")
async def operation_access_summary(
    _admin: CurrentUser = Depends(require_admin_user),
    policy=Depends(get_operation_access_policy),
):
    """Admin view of the ops-platform roster backing the access decision."""
    if policy is None:
        return {"enabled": False, "detail": "operation_access_control_disabled"}
    return policy.summary()

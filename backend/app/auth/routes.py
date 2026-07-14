"""Authenticated endpoints supporting non-HTTP transports."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from config.settings import Settings, settings

from .dependencies import require_current_user
from .models import CurrentUser
from .service import build_mock_user
from .ws_tickets import WebSocketTicketService


router = APIRouter(tags=["Authentication"])


def get_ws_ticket_service(request: Request) -> WebSocketTicketService:
    return request.app.state.ws_ticket_service


def get_auth_settings() -> Settings:
    return settings


@router.get("/auth/runtime-config")
async def runtime_auth_config(
    auth_settings: Settings = Depends(get_auth_settings),
):
    payload = {
        "authMode": "company",
        "sysCode": auth_settings.auth_sys_code,
    }
    if auth_settings.auth_mode == "mock" and auth_settings.auth_mock_enabled:
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


@router.post("/auth/ws-ticket")
async def issue_ws_ticket(
    user: CurrentUser = Depends(require_current_user),
    service: WebSocketTicketService = Depends(get_ws_ticket_service),
):
    ticket = await service.issue(user, purpose="scheduled-tasks")
    return {"ticket": ticket, "expires_in": service.ttl_seconds}

"""Internal HTTP API served by app.worker for live social account state."""

from __future__ import annotations

import asyncio
import ipaddress
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import structlog
import uvicorn

from app.api.social_account_routes import router as social_account_router
from app.api.social_account_routes import set_channel_manager_override
from app.api.fetcher_worker_routes import router as fetcher_worker_router
from app.api.scheduled_task_routes import router as scheduled_task_router
from app.api.social_broadcast_worker_routes import router as social_broadcast_worker_router
from app.auth.internal_identity import INTERNAL_USER_HEADER, decode_internal_user
from config.settings import settings

logger = structlog.get_logger()


def _trusted_internal_identity_transport(request: Request, internal_token: str) -> bool:
    if internal_token:
        return True
    client = request.client
    if client is None:
        return False
    try:
        return ipaddress.ip_address(client.host).is_loopback
    except ValueError:
        return False


def create_social_worker_api_app(
    worker_state: SimpleNamespace,
    *,
    internal_token: str = "",
) -> FastAPI:
    """Create the internal worker API app bound to the worker's runtime state."""
    app = FastAPI(title="Social Worker Internal API", docs_url=None, redoc_url=None)

    set_channel_manager_override(getattr(worker_state, "channel_manager", None))

    @app.middleware("http")
    async def require_internal_token(request: Request, call_next):
        if request.url.path == "/internal/social/broadcast" and not internal_token:
            return JSONResponse(
                {"detail": "Social worker token is not configured"},
                status_code=503,
            )
        if internal_token and request.headers.get("x-social-worker-token") != internal_token:
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
        identity_envelope = (
            request.headers.get(INTERNAL_USER_HEADER)
            if request.url.path == "/api/scheduled-tasks"
            or request.url.path.startswith("/api/scheduled-tasks/")
            else None
        )
        if identity_envelope:
            if not _trusted_internal_identity_transport(request, internal_token):
                return JSONResponse(
                    {"detail": "internal_identity_transport_not_configured"},
                    status_code=503,
                )
            try:
                request.state.current_user = decode_internal_user(identity_envelope)
            except ValueError:
                return JSONResponse(
                    {"detail": "invalid_internal_identity"},
                    status_code=401,
                )
        return await call_next(request)

    app.include_router(social_account_router)
    app.include_router(fetcher_worker_router)
    app.include_router(scheduled_task_router)
    app.include_router(social_broadcast_worker_router)
    return app


async def start_social_worker_api_service(app) -> None:
    """Start the worker-only HTTP API used by web processes as an IPC endpoint."""
    internal_app = create_social_worker_api_app(
        app.state,
        internal_token=settings.social_worker_internal_token,
    )
    config = uvicorn.Config(
        internal_app,
        host=settings.social_worker_internal_host,
        port=settings.social_worker_internal_port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    app.state.social_worker_api_server = server
    app.state.social_worker_api_task = task

    logger.info(
        "social_worker_internal_api_started",
        host=settings.social_worker_internal_host,
        port=settings.social_worker_internal_port,
    )


async def stop_social_worker_api_service(app) -> None:
    """Stop the worker-only HTTP API if it was started."""
    server = getattr(app.state, "social_worker_api_server", None)
    task = getattr(app.state, "social_worker_api_task", None)
    if not server or not task:
        return

    server.should_exit = True
    try:
        await asyncio.wait_for(task, timeout=5)
    except asyncio.TimeoutError:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("social_worker_internal_api_stopped")

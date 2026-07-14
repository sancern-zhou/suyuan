"""Middleware configuration extracted from app/main.py."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis

from app.auth.identity_cache import IdentityCache
from app.auth.middleware import GatewayAuthenticationMiddleware
from app.auth.platform_client import PlatformAuthClient
from app.auth.service import AuthenticationService
from app.auth.share_access import get_share_access_service
from app.auth.ws_tickets import WebSocketTicketService
from app.core.fetcher_worker_proxy import FetcherWorkerProxyMiddleware
from app.core.scheduled_task_worker_proxy import ScheduledTaskWorkerProxyMiddleware
from app.core.social_account_worker_proxy import SocialAccountWorkerProxyMiddleware
from config.settings import settings


def configure_middleware(app: FastAPI) -> None:
    """Configure FastAPI middleware."""
    app.add_middleware(
        ScheduledTaskWorkerProxyMiddleware,
        app_role=settings.app_role,
        worker_base_url=settings.social_worker_internal_url,
        worker_token=settings.social_worker_internal_token,
    )
    app.add_middleware(
        FetcherWorkerProxyMiddleware,
        app_role=settings.app_role,
        worker_base_url=settings.social_worker_internal_url,
        worker_token=settings.social_worker_internal_token,
    )
    app.add_middleware(
        SocialAccountWorkerProxyMiddleware,
        app_role=settings.app_role,
        worker_base_url=settings.social_worker_internal_url,
        worker_token=settings.social_worker_internal_token,
    )

    auth_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    auth_service = AuthenticationService(
        settings=settings,
        cache=IdentityCache(
            auth_redis,
            key_prefix=settings.auth_identity_cache_key_prefix,
            max_ttl_seconds=settings.auth_identity_cache_ttl_seconds,
        ),
        platform_client=PlatformAuthClient(
            base_url=settings.auth_service_url,
            current_user_path=settings.auth_current_user_path,
            admin_role_codes=settings.auth_admin_role_codes_set,
        ),
    )
    app.state.auth_redis = auth_redis
    app.state.auth_service = auth_service
    app.state.ws_ticket_service = WebSocketTicketService(
        auth_redis,
        key_prefix=settings.auth_identity_cache_key_prefix,
        ttl_seconds=settings.auth_ws_ticket_ttl_seconds,
    )
    app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=settings,
        auth_service=auth_service,
        share_access=get_share_access_service(),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=3600,
    )

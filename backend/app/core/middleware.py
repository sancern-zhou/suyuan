"""Middleware configuration extracted from app/main.py."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=3600,
    )

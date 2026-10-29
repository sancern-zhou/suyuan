"""API routes - Basic configuration endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import structlog

from app.api.tool_routes import router as tool_router

logger = structlog.get_logger()

router = APIRouter()


class ConfigResponse(BaseModel):
    """Response model for config endpoint."""

    amapPublicKey: Optional[str] = None
    features: dict = {}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "atmospheric-environment-decision-support-api",
        "version": "1.0.0",
    }


@router.options("/config")
async def config_options():
    """Handle OPTIONS preflight request for /config endpoint."""
    return {}


# Canonical tools API (mounted under /api by core.routing).
router.include_router(tool_router)

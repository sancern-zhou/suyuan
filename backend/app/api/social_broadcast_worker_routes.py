"""Worker-only API for targeted social broadcasts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.social.targeted_broadcast_service import TargetedSocialBroadcastService


router = APIRouter(prefix="/internal/social", tags=["social-worker"])
_targeted_broadcast_service_override = None


class TargetedBroadcastRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    target_user_names: list[str] = Field(min_length=1)
    media: list[str] = Field(default_factory=list)
    context_metadata: dict[str, Any] = Field(default_factory=dict)


def set_targeted_broadcast_service_override(service) -> None:
    """Replace the service in focused route tests."""
    global _targeted_broadcast_service_override
    _targeted_broadcast_service_override = service


def get_targeted_broadcast_service() -> TargetedSocialBroadcastService:
    return _targeted_broadcast_service_override or TargetedSocialBroadcastService()


@router.post("/broadcast")
async def broadcast_to_named_users(request: TargetedBroadcastRequest):
    return await get_targeted_broadcast_service().broadcast(
        message=request.message,
        target_user_names=request.target_user_names,
        media=request.media,
        context_metadata=request.context_metadata,
    )

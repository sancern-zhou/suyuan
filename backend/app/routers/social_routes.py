"""Social platform management API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import structlog

from app.social.session_mapper import SessionMapper
from app.social.monitoring import get_monitor
from app.social.cache import get_query_cache
from app.channels.manager import ChannelManager

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/social", tags=["social"])


# 依赖注入函数：从 app.state 获取实例
def get_channel_manager(request: Request) -> ChannelManager | None:
    """获取 ChannelManager 实例"""
    return getattr(request.app.state, "channel_manager", None)


def get_session_mapper(request: Request) -> SessionMapper | None:
    """获取 SessionMapper 实例"""
    return getattr(request.app.state, "session_mapper", None)


class SocialStatusResponse(BaseModel):
    """Social platform status response."""

    enabled: bool
    channels: Dict[str, Dict[str, Any]]
    active_sessions: int


class ChannelConfigUpdate(BaseModel):
    """Channel configuration update."""

    enabled: Optional[bool] = None
    allow_from: Optional[List[str]] = None


class SessionInfo(BaseModel):
    """Session information."""

    social_user_id: str
    session_id: str
    last_used: str


@router.get("/status", response_model=SocialStatusResponse)
async def get_social_status(
    channel_manager: ChannelManager = Depends(get_channel_manager),
    session_mapper: SessionMapper = Depends(get_session_mapper)
) -> SocialStatusResponse:
    """
    Get social platform integration status.

    Returns:
        Status of all enabled channels and active sessions
    """
    try:
        if not channel_manager:
            return SocialStatusResponse(
                enabled=False,
                channels={},
                active_sessions=0
            )

        # Get channel status
        channels_status = channel_manager.get_status()

        # Count active sessions
        active_sessions = 0
        if session_mapper:
            active_sessions = len(session_mapper._mappings)

        # Check if any platform is enabled
        enabled = any(
            channel_config.get("enabled", False)
            for channel_config in channels_status.values()
        )

        return SocialStatusResponse(
            enabled=enabled,
            channels=channels_status,
            active_sessions=active_sessions
        )
    except Exception as e:
        logger.error("Failed to get social status", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels")
async def list_channels(
    channel_manager: ChannelManager = Depends(get_channel_manager)
) -> Dict[str, Any]:
    """
    List all available channels and their status.

    Returns:
        Dictionary with channel status
    """
    try:
        if channel_manager:
            return channel_manager.get_status()

        return {
            "qq": {"enabled": False, "running": False},
            "weixin": {"enabled": False, "running": False},
            "dingtalk": {"enabled": False, "running": False},
            "wecom": {"enabled": False, "running": False}
        }
    except Exception as e:
        logger.error("Failed to list channels", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(
    session_mapper: SessionMapper = Depends(get_session_mapper),
    limit: int = 100
) -> List[SessionInfo]:
    """
    List active social platform sessions.

    Args:
        session_mapper: Session mapper instance
        limit: Maximum number of sessions to return

    Returns:
        List of active sessions
    """
    try:
        if not session_mapper:
            return []

        # Get active sessions from mapper
        sessions = []
        for social_user_id, session_id in session_mapper._mappings.items():
            if len(sessions) >= limit:
                break

            last_used = session_mapper._timestamp_cache.get(social_user_id)
            if last_used:
                sessions.append(SessionInfo(
                    social_user_id=social_user_id,
                    session_id=session_id,
                    last_used=last_used.isoformat()
                ))

        return sessions
    except Exception as e:
        logger.error("Failed to list sessions", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{social_user_id}")
async def delete_session(
    social_user_id: str,
    session_mapper: SessionMapper = Depends(get_session_mapper)
) -> Dict[str, Any]:
    """
    Delete a social platform session mapping.

    Args:
        social_user_id: Social platform user ID
        session_mapper: Session mapper instance

    Returns:
        Deletion result
    """
    try:
        if not session_mapper:
            raise HTTPException(status_code=404, detail="Session mapper not available")

        deleted = await session_mapper.delete_mapping(social_user_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"success": True, "message": "Session deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete session", social_user_id=social_user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/cleanup")
async def cleanup_expired_sessions(
    ttl_hours: int = 24,
    session_mapper: SessionMapper = Depends(get_session_mapper)
) -> Dict[str, Any]:
    """
    Clean up expired session mappings.

    Args:
        ttl_hours: Time-to-live in hours
        session_mapper: Session mapper instance

    Returns:
        Cleanup result
    """
    try:
        if not session_mapper:
            raise HTTPException(status_code=404, detail="Session mapper not available")

        count = await session_mapper.cleanup_expired(ttl_hours)

        return {
            "success": True,
            "cleaned_count": count,
            "message": f"Cleaned up {count} expired sessions"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to cleanup sessions", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_metrics() -> Dict[str, Any]:
    """
    Get social platform metrics.

    Returns:
        Metrics including message throughput, response times, error rates
    """
    try:
        monitor = get_monitor()
        return await monitor.get_metrics()
    except Exception as e:
        logger.error("Failed to get metrics", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_health_status() -> Dict[str, Any]:
    """
    Get health status of all social platforms.

    Returns:
        Health status for each channel
    """
    try:
        monitor = get_monitor()
        return await monitor.get_health_status()
    except Exception as e:
        logger.error("Failed to get health status", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/stats")
async def get_cache_stats() -> Dict[str, Any]:
    """
    Get query cache statistics.

    Returns:
        Cache statistics including hit rate, size, etc.
    """
    try:
        cache = get_query_cache()
        return await cache.get_stats()
    except Exception as e:
        logger.error("Failed to get cache stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_cache() -> Dict[str, Any]:
    """
    Clear all cached query results.

    Returns:
        Confirmation message
    """
    try:
        cache = get_query_cache()
        await cache.clear_all()

        return {
            "success": True,
            "message": "Cache cleared"
        }
    except Exception as e:
        logger.error("Failed to clear cache", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/metrics/reset")
async def reset_metrics(
    channel_name: str | None = None
) -> Dict[str, Any]:
    """
    Reset metrics for a channel or all channels.

    Args:
        channel_name: Channel name to reset, or None for all channels

    Returns:
        Confirmation message
    """
    try:
        monitor = get_monitor()
        await monitor.reset_metrics(channel_name)

        return {
            "success": True,
            "message": f"Metrics reset for {channel_name or 'all channels'}"
        }
    except Exception as e:
        logger.error("Failed to reset metrics", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weixin/qrcode")
async def get_weixin_qrcode(
    channel_manager: ChannelManager = Depends(get_channel_manager)
):
    """
    Get WeChat login QR code image.

    Returns:
        QR code image in PNG format
    """
    try:
        if not channel_manager:
            raise HTTPException(status_code=404, detail="Channel manager not available")

        weixin_channel = channel_manager.channels.get("weixin")
        if not weixin_channel:
            raise HTTPException(status_code=404, detail="WeChat channel not enabled")

        # Get QR code path from channel
        qr_path = getattr(weixin_channel, "_current_qr_code_path", None)
        if not qr_path or not qr_path.exists():
            # Try to trigger QR code generation
            from fastapi.responses import Response
            import qrcode
            from io import BytesIO

            # Generate a placeholder QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data("https://github.com")
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)

            return Response(content=buffer.getvalue(), media_type="image/png")

        # Return QR code image
        from fastapi.responses import FileResponse
        return FileResponse(qr_path, media_type="image/png")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get QR code", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weixin/status")
async def get_weixin_status(
    channel_manager: ChannelManager = Depends(get_channel_manager)
):
    """
    Get WeChat login status.

    Returns:
        Login status information
    """
    try:
        if not channel_manager:
            return {
                "enabled": False,
                "logged_in": False,
                "scanned": False
            }

        weixin_channel = channel_manager.channels.get("weixin")
        if not weixin_channel:
            return {
                "enabled": False,
                "logged_in": False,
                "scanned": False
            }

        # Check if logged in
        is_logged_in = bool(getattr(weixin_channel, "_token", None))
        is_scanned = getattr(weixin_channel, "_qr_scanned", False)

        return {
            "enabled": True,
            "logged_in": is_logged_in,
            "scanned": is_scanned
        }

    except Exception as e:
        logger.error("Failed to get WeChat status", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/weixin/refresh-qrcode")
async def refresh_weixin_qrcode(
    channel_manager: ChannelManager = Depends(get_channel_manager)
):
    """
    Force refresh WeChat QR code.

    Returns:
        Confirmation message
    """
    try:
        if not channel_manager:
            raise HTTPException(status_code=404, detail="Channel manager not available")

        weixin_channel = channel_manager.channels.get("weixin")
        if not weixin_channel:
            raise HTTPException(status_code=404, detail="WeChat channel not enabled")

        # Force login refresh
        success = await weixin_channel.login(force=True)

        if success:
            return {
                "success": True,
                "message": "QR code refreshed successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to refresh QR code")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to refresh QR code", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


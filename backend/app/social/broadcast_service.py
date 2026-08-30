"""Broadcast social messages to many social users."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.social.events import OutboundMessage
from app.social.broadcast_context import persist_broadcast_context
from app.social.push_service import get_unified_push_service
from app.social.message_bus_singleton import get_message_bus
from app.social.session_mapper import SessionMapper
from app.utils.path_config import resolve_agent_path

logger = structlog.get_logger(__name__)


class SocialBroadcastService:
    """Fan-out broadcast messages to social users."""

    def __init__(self, message_bus=None, session_mapper: Optional[SessionMapper] = None):
        self.message_bus = message_bus or get_message_bus()
        self.session_mapper = session_mapper

    async def _get_session_mapper(self) -> Optional[SessionMapper]:
        if self.session_mapper:
            return self.session_mapper

        bus = self.message_bus or get_message_bus()
        if bus and getattr(bus, "agent_bridge", None) and getattr(bus.agent_bridge, "session_mapper", None):
            self.session_mapper = bus.agent_bridge.session_mapper
            return self.session_mapper

        self.session_mapper = SessionMapper()
        await self.session_mapper.load()
        return self.session_mapper

    def _normalize_media(self, media: Optional[List[str]] = None) -> List[str]:
        media = media or []
        normalized_media: List[str] = []

        for media_path in media:
            if media_path.startswith(("http://", "https://")):
                normalized_media.append(media_path)
                continue

            if media_path.startswith("/api/image/"):
                match = re.match(r"/api/image/([a-zA-Z0-9_-]+)", media_path)
                if match:
                    from app.services.image_cache import get_image_cache

                    image_id = match.group(1)
                    cache = get_image_cache()
                    local_path = f"{cache.cache_dir}/{image_id}.png"
                    if Path(local_path).exists():
                        normalized_media.append(local_path)
                        continue

            if os.path.isabs(media_path):
                normalized_media.append(media_path)
                continue

            abs_path = resolve_agent_path(media_path)
            normalized_media.append(str(abs_path) if abs_path.exists() else media_path)

        return normalized_media

    @staticmethod
    def _matches_channel(social_user_id: str, channels: Optional[List[str]]) -> bool:
        if not channels:
            return True

        parts = social_user_id.rsplit(":", 2)
        if len(parts) != 3:
            return False

        channel = parts[0]
        return any(channel == target or channel.startswith(f"{target}:") for target in channels)

    @staticmethod
    def _parse_social_user_id(social_user_id: str) -> Optional[Dict[str, str]]:
        parts = social_user_id.rsplit(":", 2)
        if len(parts) != 3:
            return None

        return {
            "channel": parts[0],
            "bot_account": parts[1],
            "sender_id": parts[2],
        }

    async def broadcast(
        self,
        message: str,
        media: Optional[List[str]] = None,
        channels: Optional[List[str]] = None,
        target_user_ids: Optional[List[str]] = None,
        persist_context: bool = False,
        context_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Broadcast a message to all matching social users."""
        if not message:
            return {
                "status": "failed",
                "success": False,
                "summary": "缺少广播内容"
            }

        if not self.message_bus:
            self.message_bus = get_message_bus()
        if not self.message_bus:
            return {
                "status": "failed",
                "success": False,
                "summary": "消息总线未初始化，无法广播"
            }

        session_mapper = await self._get_session_mapper()
        if not session_mapper:
            return {
                "status": "failed",
                "success": False,
                "summary": "无法获取社交用户列表"
            }

        all_user_ids = (
            await session_mapper.get_all_social_user_ids()
            if target_user_ids is None
            else target_user_ids
        )
        normalized_media = self._normalize_media(media)

        channels_sent: List[str] = []
        failed_user_ids: List[str] = []
        delivery_results: List[Dict[str, Any]] = []

        for social_user_id in all_user_ids:
            user_info = self._parse_social_user_id(social_user_id)
            if not user_info:
                failed_user_ids.append(social_user_id)
                delivery_results.append({
                    "social_user_id": social_user_id,
                    "sent": False,
                    "context_persisted": False,
                    "error": "invalid social_user_id",
                })
                continue

            if not self._matches_channel(social_user_id, channels):
                delivery_results.append({
                    "social_user_id": social_user_id,
                    "sent": False,
                    "context_persisted": False,
                    "error": "channel did not match",
                })
                continue

            try:
                outbound_msg = OutboundMessage(
                    channel=user_info["channel"],
                    chat_id=user_info["sender_id"],
                    content=message,
                    media=normalized_media,
                    reply_to=user_info["sender_id"]
                )
                await self.message_bus.publish_outbound(outbound_msg)
                channels_sent.append(social_user_id)
                context_persisted = False
                context_error = None
                if persist_context:
                    try:
                        context_persisted = await persist_broadcast_context(
                            session_mapper=session_mapper,
                            social_user_id=social_user_id,
                            message=message,
                            media=normalized_media,
                            metadata=context_metadata or {},
                        )
                    except Exception as exc:
                        context_error = str(exc)
                        logger.warning(
                            "broadcast_context_persist_failed",
                            social_user_id=social_user_id,
                            error=context_error,
                        )
                push_result = None
                if context_persisted and social_user_id.startswith("app:"):
                    # Push is best-effort: the durable broadcast inbox remains
                    # the source of truth if the provider is unavailable.
                    push_result = await get_unified_push_service().send_broadcast(
                        social_user_id=social_user_id,
                        message=message,
                    )
                delivery_results.append({
                    "social_user_id": social_user_id,
                    "sent": True,
                    "context_persisted": context_persisted if persist_context else None,
                    "error": context_error,
                    "push": push_result,
                })
            except Exception as e:
                logger.error(
                    "broadcast_send_failed",
                    social_user_id=social_user_id,
                    error=str(e),
                    exc_info=True
                )
                failed_user_ids.append(social_user_id)
                delivery_results.append({
                    "social_user_id": social_user_id,
                    "sent": False,
                    "context_persisted": False,
                    "error": str(e),
                })

        summary = f"已广播给 {len(channels_sent)} 个社交用户"
        if failed_user_ids:
            summary += f"，失败 {len(failed_user_ids)} 个"

        return {
            "status": "success" if channels_sent else "failed",
            "success": bool(channels_sent),
            "channels_sent": channels_sent,
            "failed_user_ids": failed_user_ids,
            "delivery_results": delivery_results,
            "media_sent": len(normalized_media),
            "summary": summary
        }

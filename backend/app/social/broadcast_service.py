"""Broadcast social messages to many social users."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.social.events import OutboundMessage
from app.social.message_bus_singleton import get_message_bus
from app.social.session_mapper import SessionMapper

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

            current_dir = Path.cwd()
            project_root = current_dir.parent if current_dir.name == "backend" else current_dir
            abs_path = (project_root / media_path).resolve()
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
        target_user_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Broadcast a message to all matching social users."""
        if not message:
            return {
                "status": "failed",
                "success": False,
                "summary": "缺少广播内容"
            }

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

        all_user_ids = target_user_ids or await session_mapper.get_all_social_user_ids()
        normalized_media = self._normalize_media(media)

        channels_sent: List[str] = []
        failed_user_ids: List[str] = []

        for social_user_id in all_user_ids:
            user_info = self._parse_social_user_id(social_user_id)
            if not user_info:
                failed_user_ids.append(social_user_id)
                continue

            if not self._matches_channel(social_user_id, channels):
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
            except Exception as e:
                logger.error(
                    "broadcast_send_failed",
                    social_user_id=social_user_id,
                    error=str(e),
                    exc_info=True
                )
                failed_user_ids.append(social_user_id)

        summary = f"已广播给 {len(channels_sent)} 个社交用户"
        if failed_user_ids:
            summary += f"，失败 {len(failed_user_ids)} 个"

        return {
            "status": "success" if channels_sent else "failed",
            "success": bool(channels_sent),
            "channels_sent": channels_sent,
            "failed_user_ids": failed_user_ids,
            "media_sent": len(normalized_media),
            "summary": summary
        }


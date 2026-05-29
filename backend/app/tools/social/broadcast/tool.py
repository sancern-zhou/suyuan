"""
广播社交用户工具

用于助手模式定时任务中，将 LLM 生成的广播内容投递给所有社交用户。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class BroadcastSocialUsersTool(LLMTool):
    """Broadcast a generated message to social users."""

    def __init__(self):
        function_schema = {
            "name": "broadcast_social_users",
            "description": "将生成好的广播内容发送给社交模式的用户，可按渠道筛选",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "要广播的内容"
                    },
                    "media": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选媒体路径或URL",
                        "default": []
                    },
                    "channels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选目标渠道，例如 ['weixin', 'qq', 'dingtalk', 'wecom']；不传则广播给所有已知社交用户",
                        "default": []
                    }
                },
                "required": ["message"]
            }
        }

        super().__init__(
            name="broadcast_social_users",
            description="将助手生成的广播内容发送给所有社交用户",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

    async def execute(
        self,
        message: str = None,
        media: Optional[List[str]] = None,
        channels: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        if not message:
            return {
                "status": "failed",
                "success": False,
                "summary": "缺少广播内容"
            }

        try:
            from app.social.broadcast_service import SocialBroadcastService
            from app.social.message_bus_singleton import get_message_bus

            message_bus = get_message_bus()
            service = SocialBroadcastService(message_bus=message_bus)
            result = await service.broadcast(
                message=message,
                media=media,
                channels=channels
            )

            logger.info(
                "broadcast_social_users_executed",
                success=result.get("success", False),
                sent_count=len(result.get("channels_sent", [])),
                failed_count=len(result.get("failed_user_ids", []))
            )
            return result

        except Exception as e:
            logger.error("broadcast_social_users_failed", error=str(e), exc_info=True)
            return {
                "status": "failed",
                "success": False,
                "summary": f"广播失败：{str(e)}"
            }

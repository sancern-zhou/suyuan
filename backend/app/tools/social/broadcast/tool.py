"""
广播社交用户工具

用于助手模式中，将 LLM 生成的广播内容投递给明确指定的微信用户。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class BroadcastSocialUsersTool(LLMTool):
    """Broadcast a generated message to explicitly named WeChat users."""

    def __init__(self, worker_client=None):
        self.worker_client = worker_client
        function_schema = {
            "name": "broadcast_social_users",
            "description": "将广播内容发送给明确指定的后台微信用户名称",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "要广播的内容"
                    },
                    "target_user_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "后台微信用户名称列表，精确匹配且重名时拒绝"
                    },
                    "media": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选媒体路径或URL",
                        "default": []
                    }
                },
                "required": ["message", "target_user_names"]
            }
        }

        super().__init__(
            name="broadcast_social_users",
            description="将助手生成的广播内容发送给明确指定的微信用户",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

    async def execute(
        self,
        message: str = None,
        target_user_names: Optional[List[str]] = None,
        media: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        if not message:
            return {
                "status": "failed",
                "success": False,
                "summary": "缺少广播内容"
            }
        if not any(name.strip() for name in (target_user_names or [])):
            return {
                "status": "failed",
                "success": False,
                "summary": "必须指定目标用户名称"
            }

        try:
            from app.core.social_broadcast_worker_client import (
                SocialBroadcastWorkerClient,
                SocialBroadcastWorkerUnavailable,
            )

            client = self.worker_client or SocialBroadcastWorkerClient()
            result = await client.broadcast(
                message=message,
                target_user_names=target_user_names or [],
                media=media or [],
                context_metadata={
                    "source": "assistant_tool",
                    "tool_name": "broadcast_social_users",
                },
            )

            logger.info(
                "broadcast_social_users_executed",
                success=result.get("success", False),
                sent_count=len(result.get("channels_sent", [])),
                failed_count=len(result.get("failed_user_names", []))
            )
            return result

        except SocialBroadcastWorkerUnavailable as e:
            logger.warning("broadcast_social_worker_unavailable", error=str(e))
            return {
                "status": "failed",
                "success": False,
                "summary": f"社交 Worker 不可用：{str(e)}"
            }
        except Exception as e:
            logger.error("broadcast_social_users_failed", error=str(e), exc_info=True)
            return {
                "status": "failed",
                "success": False,
                "summary": f"广播失败：{str(e)}"
            }

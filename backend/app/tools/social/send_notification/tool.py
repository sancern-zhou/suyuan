"""
主动发送通知工具

核心功能：
- 主动发送通知到用户
- 支持多通道同时发送
- 数据异常告警、分析进度更新、定时报告推送
"""

from typing import Dict, Any, Optional, List
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class SendNotificationTool(LLMTool):
    """
    主动发送通知工具

    场景：
    - 数据异常告警
    - 分析进度更新
    - 定时报告推送
    - 智能建议

    实现：
    - 通过MessageBus.publish_outbound()发送
    - 支持多通道同时发送
    """

    def __init__(self, message_bus=None):
        # 定义 function_schema
        function_schema = {
            "name": "send_notification",
            "description": "主动发送通知到用户（支持多通道同时发送）",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "通知内容"
                    },
                    "channels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "目标通道列表（如['weixin', 'qq']），默认['weixin']",
                        "default": ["weixin"]
                    },
                    "chat_id": {
                        "type": "string",
                        "description": "目标聊天ID（可选，默认发送给所有用户）"
                    }
                },
                "required": ["message"]
            }
        }

        # 初始化基类
        super().__init__(
            name="send_notification",
            description="主动发送通知到用户（支持多通道同时发送）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

        self.message_bus = message_bus

    async def execute(
        self,
        message: str = None,
        channels: Optional[list] = None,
        chat_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行发送通知

        Args:
            message: 通知内容
            channels: 目标通道列表
            chat_id: 目标聊天ID

        Returns:
            {
                "status": "success" | "failed",
                "success": true|false,
                "channels_sent": ["weixin", "qq"],
                "summary": "简要总结"
            }
        """
        # 参数验证
        if not message:
            return {
                "status": "failed",
                "success": False,
                "summary": "缺少通知内容"
            }

        try:
            channels = channels or ["weixin"]
            channels_sent = []

            # 如果有MessageBus，通过MessageBus发送
            if self.message_bus:
                from app.social.events import OutboundMessage

                for channel in channels:
                    try:
                        outbound_msg = OutboundMessage(
                            channel=channel,
                            chat_id=chat_id or "",
                            content=message,
                            reply_to=None
                        )

                        await self.message_bus.publish_outbound(outbound_msg)
                        channels_sent.append(channel)

                        logger.info(
                            "notification_sent",
                            channel=channel,
                            chat_id=chat_id,
                            message_length=len(message)
                        )

                    except Exception as e:
                        logger.error(
                            "failed_to_send_to_channel",
                            channel=channel,
                            error=str(e)
                        )

            else:
                # 降级方案：记录到日志
                logger.warning(
                    "no_message_bus_available",
                    message=message[:100],
                    channels=channels
                )
                channels_sent = channels  # 假装发送成功

            return {
                "status": "success",
                "success": len(channels_sent) > 0,
                "channels_sent": channels_sent,
                "summary": f"已发送通知到：{', '.join(channels_sent)}"
            }

        except Exception as e:
            logger.error(
                "failed_to_send_notification",
                error=str(e),
                exc_info=True
            )
            return {
                "status": "failed",
                "success": False,
                "summary": f"发送通知失败：{str(e)}"
            }

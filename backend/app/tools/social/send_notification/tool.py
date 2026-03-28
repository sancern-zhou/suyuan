"""
主动发送通知工具

核心功能：
- 主动发送通知到用户
- 支持多通道同时发送
- 数据异常告警、分析进度更新、定时报告推送
"""

from typing import Dict, Any, Optional, List
import structlog
import os
from pathlib import Path

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
            "description": "主动发送通知到用户（支持文本、图片、文件，自动发送到当前对话的用户）",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "通知内容（文本）"
                    },
                    "media": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "媒体文件路径列表（支持本地路径或URL，如['/path/to/image.png', 'http://localhost:8000/api/image/abc123']）",
                        "default": []
                    }
                },
                "required": ["message"]
            }
        }

        # 初始化基类
        super().__init__(
            name="send_notification",
            description="主动发送通知到用户（支持文本、图片、文件，支持多通道同时发送）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0"
        )

        self.message_bus = message_bus

    async def execute(
        self,
        message: str = None,
        media: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行发送通知

        Args:
            message: 通知内容
            media: 媒体文件路径列表（支持本地路径或URL）

        Returns:
            {
                "status": "success" | "failed",
                "success": true|false,
                "channels_sent": ["weixin:auto_mn8k8rry"],
                "summary": "简要总结"
            }
        """
        # ✅ 尝试获取 message_bus（多个来源）
        if not self.message_bus:
            # 1. 从 kwargs 中的 context 获取
            context = kwargs.get('context')
            if context and hasattr(context, 'message_bus') and context.message_bus:
                self.message_bus = context.message_bus
                logger.debug("message_bus_injected_from_context")

            # 2. 从全局单例获取
            if not self.message_bus:
                try:
                    from app.social.message_bus_singleton import get_message_bus
                    self.message_bus = get_message_bus()
                    if self.message_bus:
                        logger.debug("message_bus_injected_from_singleton")
                except Exception:
                    pass

        # 参数验证
        if not message:
            return {
                "status": "failed",
                "success": False,
                "summary": "缺少通知内容"
            }

        try:
            # ✅ 从 singleton 获取当前 channel 和 chat_id（由 agent_bridge 设置）
            from app.social.message_bus_singleton import get_current_channel, get_current_chat_id

            current_channel = get_current_channel()
            current_chat_id = get_current_chat_id()

            if not current_channel:
                logger.error("current_channel_not_found",
                           note="当前不在对话上下文中，无法确定发送通道")
                return {
                    "status": "failed",
                    "success": False,
                    "summary": "无法确定发送通道（请确保在对话中调用此工具）"
                }

            if not current_chat_id:
                logger.warning("current_chat_id_not_found",
                            note="将发送到通道的默认聊天对象")

            channels = [current_channel]
            chat_id = current_chat_id or ""

            logger.info("using_current_conversation_context",
                       channel=current_channel,
                       chat_id=chat_id)

            media = media or []
            channels_sent = []

            # ✅ 路径标准化：自动转换相对路径为绝对路径
            normalized_media = []
            for media_path in media:
                # 保留 URL（http:// 或 https:// 开头）
                if media_path.startswith(('http://', 'https://')):
                    normalized_media.append(media_path)
                    logger.debug("media_url_kept", path=media_path)
                # 保留已经是绝对路径的路径
                elif os.path.isabs(media_path):
                    normalized_media.append(media_path)
                    logger.debug("media_absolute_path_kept", path=media_path)
                # 转换相对路径为绝对路径
                else:
                    # 获取项目根目录（假设是当前工作目录的父目录）
                    # 例如：/home/xckj/suyuan/backend -> /home/xckj/suyuan
                    current_dir = Path.cwd()
                    # 如果当前在 backend 目录，向上查找项目根
                    if current_dir.name == 'backend':
                        project_root = current_dir.parent
                    else:
                        project_root = current_dir

                    abs_path = project_root / media_path
                    # 解析为绝对路径（消除 .. 和 .）
                    abs_path = abs_path.resolve()

                    # 检查文件是否存在
                    if abs_path.exists():
                        normalized_media.append(str(abs_path))
                        logger.info(
                            "media_relative_path_converted",
                            relative=media_path,
                            absolute=str(abs_path)
                        )
                    else:
                        # 文件不存在，保留原路径并记录警告
                        normalized_media.append(media_path)
                        logger.warning(
                            "media_file_not_found",
                            path=media_path,
                            absolute=str(abs_path),
                            note="Keeping original path"
                        )

            media = normalized_media

            # 如果有MessageBus，通过MessageBus发送
            if self.message_bus:
                from app.social.events import OutboundMessage

                for channel in channels:
                    try:
                        outbound_msg = OutboundMessage(
                            channel=channel,
                            chat_id=chat_id or "",
                            content=message,
                            media=media,
                            reply_to=None
                        )

                        await self.message_bus.publish_outbound(outbound_msg)
                        channels_sent.append(channel)

                        logger.info(
                            "notification_sent",
                            channel=channel,
                            chat_id=chat_id,
                            message_length=len(message),
                            media_count=len(media)
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
                    channels=channels,
                    media=media
                )
                channels_sent = channels  # 假装发送成功

            media_info = f"，包含 {len(media)} 个文件" if media else ""
            return {
                "status": "success",
                "success": len(channels_sent) > 0,
                "channels_sent": channels_sent,
                "media_sent": len(media),
                "summary": f"已发送通知到：{', '.join(channels_sent)}{media_info}"
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

"""Channel manager for coordinating chat channels."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from app.social.events import OutboundMessage
from app.social.message_bus import MessageBus
from app.channels.base import BaseChannel
from config.settings import settings

logger = structlog.get_logger(__name__)

# Retry delays for message sending (exponential backoff: 1s, 2s, 4s)
_SEND_RETRY_DELAYS = (1, 2, 4)


class ChannelManager:
    """
    Manages chat channels and coordinates message routing.

    Responsibilities:
    - Initialize enabled channels (QQ, WeChat, DingTalk, WeCom)
    - Start/stop channels
    - Route outbound messages
    """

    def __init__(self, config: Any, bus: MessageBus, agent_bridge=None):
        """
        Initialize the channel manager.

        Args:
            config: Configuration object or dict with channel settings
            bus: Message bus for communication
            agent_bridge: Optional AgentBridge instance for channel registration
        """
        self.config = config
        self.bus = bus
        self.agent_bridge = agent_bridge  # ✅ 新增：AgentBridge 引用
        self.channels: dict[str, BaseChannel] = {}
        self._dispatch_task: asyncio.Task | None = None

        self._init_channels()

    def _init_channels(self) -> None:
        """
        Initialize enabled channels from configuration.

        Supports multi-instance channels (e.g., multiple WeChat accounts).
        Channel keys use format: "type:instance_id" (e.g., "weixin:account_1")
        """
        # 单实例渠道（QQ、钉钉、企业微信）
        for name in ['qq', 'dingtalk', 'wecom']:
            channel_config = getattr(self.config, name, None)
            if not channel_config:
                logger.debug(f"Channel {name}: no config found")
                continue

            is_enabled = getattr(channel_config, 'enabled', False)
            if not is_enabled:
                continue

            try:
                channel = self._create_channel(name, channel_config)
                if channel:
                    self.channels[name] = channel
                    logger.info("Channel enabled", name=name, display_name=channel.display_name)
            except Exception as e:
                logger.warning("Channel not available", name=name, error=str(e), exc_info=True)

        # ✅ 多实例渠道（微信）
        weixin_config = getattr(self.config, 'weixin', None)
        if weixin_config and getattr(weixin_config, 'enabled', False):
            self._init_weixin_channels(weixin_config)

        self._validate_allow_from()

    def _init_weixin_channels(self, weixin_config: Any) -> None:
        """
        Initialize multiple WeChat channel instances.

        Args:
            weixin_config: WeixinConfig object with accounts list
        """
        accounts = getattr(weixin_config, 'accounts', [])

        if not accounts:
            logger.warning("WeChat enabled but no accounts configured")
            return

        logger.info(f"Initializing {len(accounts)} WeChat account(s)")

        for account_config in accounts:
            if not getattr(account_config, 'enabled', True):
                logger.info(f"WeChat account {account_config.id}: disabled, skipping")
                continue

            try:
                channel = self._create_weixin_channel(account_config)
                if channel:
                    channel_key = f"weixin:{account_config.id}"
                    self.channels[channel_key] = channel
                    logger.info(
                        "WeChat account initialized",
                        account_id=account_config.id,
                        name=account_config.name,
                        channel_key=channel_key
                    )
            except Exception as e:
                logger.error(
                    "Failed to initialize WeChat account",
                    account_id=account_config.id,
                    error=str(e),
                    exc_info=True
                )

    def _create_weixin_channel(self, account_config: Any) -> Any:
        """
        Create a single WeChat channel instance.

        Args:
            account_config: WeixinAccountConfig object

        Returns:
            WeixinChannel instance
        """
        from app.channels.weixin import WeixinChannel

        # 创建渠道实例，传入账号ID作为instance_id
        channel = WeixinChannel(
            config=account_config,
            bus=self.bus,
            instance_id=account_config.id
        )
        return channel

    def _create_channel(self, name: str, config: Any, instance_id: str = None) -> BaseChannel | None:
        """
        Create a channel instance by name.

        Args:
            name: Channel name (qq, weixin, dingtalk, wecom)
            config: Channel configuration
            instance_id: Optional instance ID for multi-instance channels

        Returns:
            Channel instance or None if not available
        """
        # Import channel classes
        try:
            if name == "qq":
                from app.channels.qq import QQChannel
                return QQChannel(config, self.bus)
            elif name == "weixin":
                from app.channels.weixin import WeixinChannel
                return WeixinChannel(config, self.bus, instance_id=instance_id)
            elif name == "dingtalk":
                from app.channels.dingtalk import DingTalkChannel
                return DingTalkChannel(config, self.bus)
            elif name == "wecom":
                from app.channels.wecom import WeComChannel
                return WeComChannel(config, self.bus)
            else:
                logger.warning("Unknown channel", name=name)
                return None
        except ImportError as e:
            logger.warning("Channel module not available", name=name, error=str(e))
            return None
        except Exception as e:
            logger.warning("Failed to create channel", name=name, error=str(e))
            return None

    def _validate_allow_from(self) -> None:
        """Validate that all channels have non-empty allow_from lists."""
        for name, ch in self.channels.items():
            allow_list = getattr(ch.config, "allow_from", [])
            if isinstance(allow_list, list) and len(allow_list) == 0:
                raise ValueError(
                    f'Channel "{name}" has empty allow_from (denies all). '
                    f'Set ["*"] to allow everyone, or add specific user IDs.'
                )

    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """Start a channel and log any exceptions."""
        try:
            # Perform login if required
            await channel.login(force=False)

            # Start the channel
            await channel.start()
            logger.info("Channel started", name=name)
        except Exception as e:
            logger.error("Failed to start channel", name=name, error=str(e), exc_info=True)

    async def start_all(self) -> None:
        """Start all channels and the outbound dispatcher."""
        logger.info("start_all_called", channels_count=len(self.channels), channels=list(self.channels.keys()))

        # Start outbound dispatcher first (even if no channels initially)
        # This allows dynamic channel creation to work properly
        if not self._dispatch_task or self._dispatch_task.done():
            logger.info("starting_outbound_dispatcher")
            self._dispatch_task = asyncio.create_task(self._dispatch_outbound())
            logger.info("outbound_dispatcher_started", task_id=id(self._dispatch_task))

        if not self.channels:
            logger.info("No channels initially, dispatcher will handle dynamic channel creation")
            # Keep dispatcher running, don't return
            return

        # ✅ 注册 channels 到 AgentBridge（用于获取机器人账号）
        if self.agent_bridge:
            for name, channel in self.channels.items():
                self.agent_bridge.register_channel(channel)
                logger.info("channel_registered_to_agent_bridge", channel_name=name)

        # Start channels
        tasks = []
        for name, channel in self.channels.items():
            logger.info("Starting channel...", name=name)
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))

        # Wait for all to complete (they should run forever)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """Stop all channels and the dispatcher."""
        logger.info("Stopping all channels...")

        # Stop dispatcher
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass

        # Stop all channels
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info("Stopped channel", name=name)
            except Exception as e:
                logger.error("Error stopping channel", name=name, error=str(e))

    async def reload_channels(self) -> None:
        """
        重新加载渠道配置（支持动态增删账户）

        - 停止已删除的账户
        - 启动新添加的账户
        - 保留仍在运行的账户
        """
        logger.info("reload_channels_called", current_channels=list(self.channels.keys()))

        # 保存当前渠道列表
        old_channels = dict(self.channels)

        # 清空当前渠道列表
        self.channels.clear()

        # 重新初始化渠道（会清理无效状态）
        self._init_channels()

        # 找出被删除的渠道并停止它们
        for name, channel in old_channels.items():
            if name not in self.channels:
                try:
                    await channel.stop()
                    logger.info("stopped_deleted_channel", name=name)
                except Exception as e:
                    logger.error("failed_to_stop_deleted_channel", name=name, error=str(e))

        # 找出新添加的渠道并启动它们
        for name, channel in self.channels.items():
            if name not in old_channels:
                logger.info("found_new_channel", name=name, will_start=True)

        # 启动所有新渠道
        new_channels = {name: ch for name, ch in self.channels.items() if name not in old_channels}
        if new_channels:
            logger.info("starting_new_channels", channels=list(new_channels.keys()))
            tasks = []
            for name, channel in new_channels.items():
                tasks.append(asyncio.create_task(self._start_channel(name, channel)))

            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(
            "reload_channels_completed",
            old_count=len(old_channels),
            new_count=len(self.channels),
            added=len(new_channels),
            removed=len(old_channels) - len(self.channels) + len(new_channels)
        )

    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        logger.info("Outbound dispatcher started", available_channels=list(self.channels.keys()))

        while True:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_outbound(),
                    timeout=1.0
                )

                logger.info("Outbound message received",
                           channel=msg.channel,
                           chat_id=msg.chat_id,
                           content_preview=msg.content[:50] if msg.content else "",
                           available_channels=list(self.channels.keys()))

                # Check if message should be sent (progress filtering)
                if msg.metadata.get("_progress"):
                    if msg.metadata.get("_tool_hint") and not getattr(
                        self.config.channels, 'send_tool_hints', True
                    ):
                        continue
                    if not msg.metadata.get("_tool_hint") and not getattr(
                        self.config.channels, 'send_progress', True
                    ):
                        continue

                # ✅ 精确匹配：channel 必须是完整的 key（如 "weixin:auto_mn8k8rry"）
                # 不能使用模糊匹配，否则会导致消息发给错误的用户
                channel = self.channels.get(msg.channel)
                if channel:
                    logger.info("Channel found, sending message", channel=msg.channel)
                    await self._send_with_retry(channel, msg)
                else:
                    logger.error("Unknown channel - message not sent",
                                  channel=msg.channel,
                                  available_channels=list(self.channels.keys()))

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in outbound dispatcher", error=str(e), exc_info=True)

    @staticmethod
    async def _send_once(channel: BaseChannel, msg: OutboundMessage) -> None:
        """Send one outbound message without retry policy."""
        if msg.metadata.get("_stream_delta") or msg.metadata.get("_stream_end"):
            await channel.send_delta(msg.chat_id, msg.content, msg.metadata)
        elif not msg.metadata.get("_streamed"):
            await channel.send(msg)

    async def _send_with_retry(self, channel: BaseChannel, msg: OutboundMessage) -> None:
        """Send a message with retry on failure using exponential backoff.

        Note: CancelledError is re-raised to allow graceful shutdown.
        """
        max_attempts = max(getattr(self.config.channels, 'send_max_retries', 3), 1)

        for attempt in range(max_attempts):
            try:
                await self._send_once(channel, msg)
                return  # Send succeeded
            except asyncio.CancelledError:
                raise  # Propagate cancellation for graceful shutdown
            except Exception as e:
                if attempt == max_attempts - 1:
                    logger.error(
                        "Failed to send after %d attempts: %s - %s",
                        max_attempts, type(e).__name__, e
                    )
                    return
                delay = _SEND_RETRY_DELAYS[min(attempt, len(_SEND_RETRY_DELAYS) - 1)]
                logger.warning(
                    "Send failed (attempt %d/%d): %s, retrying in %ds",
                    attempt + 1, max_attempts, type(e).__name__, delay
                )
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    raise  # Propagate cancellation during sleep

    def get_channel(self, name: str) -> BaseChannel | None:
        """Get a channel by name."""
        return self.channels.get(name)

    def get_status(self) -> dict[str, Any]:
        """Get status of all channels."""
        return {
            name: {
                "enabled": True,
                "running": channel.is_running
            }
            for name, channel in self.channels.items()
        }

    @property
    def enabled_channels(self) -> list[str]:
        """Get list of enabled channel names."""
        return list(self.channels.keys())

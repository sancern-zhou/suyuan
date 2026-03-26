"""Channel manager for coordinating chat channels."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.social.events import OutboundMessage
from app.social.message_bus import MessageBus
from app.channels.base import BaseChannel

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

    def __init__(self, config: Any, bus: MessageBus):
        """
        Initialize the channel manager.

        Args:
            config: Configuration object or dict with channel settings
            bus: Message bus for communication
        """
        self.config = config
        self.bus = bus
        self.channels: dict[str, BaseChannel] = {}
        self._dispatch_task: asyncio.Task | None = None

        self._init_channels()

    def _init_channels(self) -> None:
        """Initialize enabled channels from configuration."""
        # SocialConfig has separate channel attributes (qq, weixin, dingtalk, wecom)
        # not a 'channels' dict
        channel_names = ['qq', 'weixin', 'dingtalk', 'wecom']

        for name in channel_names:
            channel_config = getattr(self.config, name, None)
            if not channel_config:
                logger.debug(f"Channel {name}: no config found")
                continue

            # Check if enabled
            is_enabled = getattr(channel_config, 'enabled', False)
            logger.info(f"Channel {name}: enabled={is_enabled}, config={channel_config}")

            if not is_enabled:
                continue

            try:
                channel = self._create_channel(name, channel_config)
                if channel:
                    self.channels[name] = channel
                    logger.info("Channel enabled", name=name, display_name=channel.display_name)
            except Exception as e:
                logger.warning("Channel not available", name=name, error=str(e), exc_info=True)

        self._validate_allow_from()

    def _create_channel(self, name: str, config: Any) -> BaseChannel | None:
        """
        Create a channel instance by name.

        Args:
            name: Channel name (qq, weixin, dingtalk, wecom)
            config: Channel configuration

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
                return WeixinChannel(config, self.bus)
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
        if not self.channels:
            logger.warning("No channels enabled")
            return

        # Start outbound dispatcher
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

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

    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        logger.info("Outbound dispatcher started")

        while True:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_outbound(),
                    timeout=1.0
                )

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

                channel = self.channels.get(msg.channel)
                if channel:
                    await self._send_with_retry(channel, msg)
                else:
                    logger.warning("Unknown channel", channel=msg.channel)

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

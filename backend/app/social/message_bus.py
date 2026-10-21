"""Async message queue for decoupled channel-agent communication."""

import asyncio
from uuid import uuid4

from app.social.events import InboundMessage, OutboundMessage


class MessageBus:
    """
    Async message bus that decouples chat channels from the agent core.

    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.
    """

    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self.agent_bridge = None  # ✅ 新增：AgentBridge 引用（用于工具访问）
        self._deliveries: dict[str, asyncio.Future] = {}

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent."""
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()

    async def deliver_outbound(self, msg: OutboundMessage, *, timeout: float = 20) -> None:
        """Wait for the channel adapter's result, rather than treating enqueue as delivery."""
        msg.delivery_id = uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._deliveries[msg.delivery_id] = future
        try:
            await self.publish_outbound(msg)
            if not await asyncio.wait_for(future, timeout):
                raise RuntimeError("channel_delivery_failed")
        except TimeoutError as exc:
            raise TimeoutError("delivery_confirmation_timeout") from exc
        finally:
            self._deliveries.pop(msg.delivery_id, None)

    def delivery_pending(self, msg: OutboundMessage) -> bool:
        return msg.delivery_id is None or msg.delivery_id in self._deliveries

    def acknowledge_delivery(self, msg: OutboundMessage, delivered: bool) -> None:
        future = self._deliveries.get(msg.delivery_id)
        if future is not None and not future.done():
            future.set_result(delivered)

    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()

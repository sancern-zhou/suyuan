import asyncio
from types import SimpleNamespace

import pytest

from app.channels.manager import ChannelManager
from app.social.events import OutboundMessage
from app.social.message_bus import MessageBus
from app.social.broadcast_service import SocialBroadcastService


@pytest.mark.asyncio
@pytest.mark.parametrize("ok", [True, False])
async def test_broadcast_uses_adapter_result_and_persists_it(monkeypatch, ok):
    bus = MessageBus()
    manager = object.__new__(ChannelManager)
    manager.bus = bus
    manager.config = SimpleNamespace(channels=SimpleNamespace(send_max_retries=1))
    async def send(message):
        if not ok:
            raise RuntimeError("synthetic failure")
    manager.channels = {"weixin:one": SimpleNamespace(send=send)}
    recorded = []
    async def persist(**kwargs):
        recorded.append(kwargs["metadata"])
        return True
    monkeypatch.setattr("app.social.broadcast_service.persist_broadcast_context", persist)
    service = SocialBroadcastService(message_bus=bus, session_mapper=SimpleNamespace())
    dispatcher = asyncio.create_task(manager._dispatch_outbound())
    try:
        result = await service.broadcast(message="test", target_user_ids=["weixin:one:bot:user"], persist_context=True)
        assert result["success"] is ok
        assert result["delivery_results"][0]["sent"] is ok
        assert recorded[0]["delivery_status"] == ("delivered" if ok else "failed")
    finally:
        dispatcher.cancel()
        await dispatcher


@pytest.mark.asyncio
async def test_unknown_channel_fails_and_timed_out_queue_is_invalidated():
    bus = MessageBus()
    message = OutboundMessage(channel="missing", chat_id="user", content="hello")
    with pytest.raises(TimeoutError, match="delivery_confirmation_timeout"):
        await bus.deliver_outbound(message, timeout=0.01)
    assert not bus.delivery_pending(await bus.consume_outbound())
    assert bus._deliveries == {}

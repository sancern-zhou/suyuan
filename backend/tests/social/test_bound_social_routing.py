from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.conversations.schemas import ConversationSource
from app.social.agent_bridge import AgentBridge
from app.social.binding_schemas import SocialBindingRecord
from app.social.events import InboundMessage
from app.social.message_bus import MessageBus


def _binding():
    return SocialBindingRecord(
        id="b1", platform_user_id="u1", platform_username="alice",
        platform_display_name="Alice", account_id="a1",
        ilink_user_id="wx-1", bot_account="bot-1", status="active",
        bound_at=datetime.utcnow(),
    )


def _bridge(binding):
    bridge = AgentBridge.__new__(AgentBridge)
    bridge.message_bus = MessageBus()
    bridge.mode = "social"
    bridge.binding_service = SimpleNamespace(resolve_sender=AsyncMock(return_value=binding))
    bridge.catalog = SimpleNamespace(
        register_identity=AsyncMock(), require_read=AsyncMock(), delete=AsyncMock()
    )
    bridge.session_mapper = SimpleNamespace(
        get_session=AsyncMock(return_value=None),
        new_session_id=Mock(return_value="social-session-1"),
        save_mapping=AsyncMock(),
    )
    bridge._active_social_sessions = set()
    bridge._get_bot_account = AsyncMock(return_value="bot-1")
    bridge._process_message = AsyncMock()
    bridge._build_agent_attachments = Mock(return_value=[])
    return bridge


def _inbound(content="hello"):
    return InboundMessage(
        channel="weixin:a1", sender_id="wx-1", chat_id="chat-1", content=content
    )


@pytest.mark.asyncio
async def test_unbound_sender_gets_instruction_without_session_or_agent_call():
    bridge = _bridge(None)

    await bridge._route_message(_inbound())

    bridge.session_mapper.get_session.assert_not_awaited()
    bridge._process_message.assert_not_awaited()
    outbound = await bridge.message_bus.consume_outbound()
    assert "先登录 Web" in outbound.content


@pytest.mark.asyncio
async def test_bound_sender_registers_social_catalog_before_processing():
    bridge = _bridge(_binding())

    await bridge._route_message(_inbound())

    bridge.catalog.register_identity.assert_awaited_once_with(
        session_id="social-session-1",
        owner_user_id="u1",
        owner_username="alice",
        owner_display_name="Alice",
        source=ConversationSource.SOCIAL,
        mode="social",
        title="hello",
        read_only_on_web=True,
    )
    bridge.session_mapper.save_mapping.assert_awaited_once_with(
        "weixin:a1:bot-1:wx-1", "social-session-1"
    )
    bridge._process_message.assert_awaited_once()
    assert bridge.catalog.register_identity.await_count == 1


@pytest.mark.asyncio
async def test_legacy_four_digit_code_does_not_bind_unbound_wechat():
    bridge = _bridge(None)

    await bridge._route_message(_inbound("1234"))

    bridge._process_message.assert_not_awaited()
    outbound = await bridge.message_bus.consume_outbound()
    assert "先登录 Web" in outbound.content

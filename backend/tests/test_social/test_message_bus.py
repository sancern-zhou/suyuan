"""Unit tests for MessageBus."""

import asyncio
import pytest
from datetime import datetime

from app.social.events import InboundMessage, OutboundMessage
from app.social.message_bus import MessageBus


@pytest.mark.asyncio
async def test_message_bus_basic_flow():
    """Test basic message flow through the bus."""
    bus = MessageBus()

    # Create test message
    inbound_msg = InboundMessage(
        channel="test",
        sender_id="user123",
        chat_id="chat456",
        content="Test message"
    )

    # Publish inbound
    await bus.publish_inbound(inbound_msg)

    # Verify queue size
    assert bus.inbound_size == 1

    # Consume inbound
    consumed_msg = await bus.consume_inbound()
    assert consumed_msg.channel == "test"
    assert consumed_msg.sender_id == "user123"
    assert consumed_msg.content == "Test message"

    # Verify queue is empty
    assert bus.inbound_size == 0


@pytest.mark.asyncio
async def test_message_bus_outbound():
    """Test outbound message flow."""
    bus = MessageBus()

    # Create test message
    outbound_msg = OutboundMessage(
        channel="test",
        chat_id="chat456",
        content="Test response"
    )

    # Publish outbound
    await bus.publish_outbound(outbound_msg)

    # Verify queue size
    assert bus.outbound_size == 1

    # Consume outbound
    consumed_msg = await bus.consume_outbound()
    assert consumed_msg.channel == "test"
    assert consumed_msg.chat_id == "chat456"
    assert consumed_msg.content == "Test response"


@pytest.mark.asyncio
async def test_message_bus_concurrent():
    """Test concurrent message handling."""
    bus = MessageBus()

    # Publish multiple messages concurrently
    tasks = []
    for i in range(10):
        msg = InboundMessage(
            channel="test",
            sender_id=f"user{i}",
            chat_id=f"chat{i}",
            content=f"Message {i}"
        )
        tasks.append(bus.publish_inbound(msg))

    await asyncio.gather(*tasks)

    # Verify all messages were queued
    assert bus.inbound_size == 10

    # Consume all messages
    consumed = []
    for _ in range(10):
        msg = await bus.consume_inbound()
        consumed.append(msg)

    # Verify all messages were consumed
    assert len(consumed) == 10
    assert bus.inbound_size == 0


@pytest.mark.asyncio
async def test_inbound_message_session_key():
    """Test InboundMessage session_key property."""
    # Test default session key (channel:chat_id)
    msg1 = InboundMessage(
        channel="qq",
        sender_id="user123",
        chat_id="chat456",
        content="Test"
    )
    assert msg1.session_key == "qq:chat456"

    # Test custom session key override
    msg2 = InboundMessage(
        channel="qq",
        sender_id="user123",
        chat_id="chat456",
        content="Test",
        session_key_override="custom_key"
    )
    assert msg2.session_key == "custom_key"


@pytest.mark.asyncio
async def test_message_bus_with_metadata():
    """Test messages with metadata."""
    bus = MessageBus()

    inbound_msg = InboundMessage(
        channel="test",
        sender_id="user123",
        chat_id="chat456",
        content="Test message",
        media=["http://example.com/image.png"],
        metadata={"_wants_stream": True, "custom_field": "value"}
    )

    await bus.publish_inbound(inbound_msg)
    consumed_msg = await bus.consume_inbound()

    assert consumed_msg.media == ["http://example.com/image.png"]
    assert consumed_msg.metadata["_wants_stream"] is True
    assert consumed_msg.metadata["custom_field"] == "value"

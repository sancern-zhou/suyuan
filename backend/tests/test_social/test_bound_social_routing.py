import asyncio
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.agent.react_agent import ReActAgent
from app.agent.resources.resource_service import SessionResourceService
from app.agent.runtime.agent_runtime import AgentRuntime, AgentRuntimeConfig
from app.agent.runtime.steering import InMemorySteeringStore, steering_registry
from app.agent.runtime.types import RunState
from app.agent.session import Session
from app.channels.weixin import ITEM_IMAGE, MESSAGE_TYPE_USER, WeixinChannel
from app.conversations.schemas import ConversationSource
from app.social.agent_bridge import SOCIAL_IMAGE_MAX_BYTES, AgentBridge
from app.social.binding_schemas import SocialBindingRecord
from app.social.events import InboundMessage
from app.social.message_bus import MessageBus

_DEFAULT_AGENT = object()


class RecordingResourceService:
    def __init__(self):
        self.calls = []
        self.service = SessionResourceService.in_memory()

    async def publish_group(
        self, session_id, run_id, group_key, resources, *, turn_sequence=0
    ):
        self.calls.append((session_id, run_id, resources))
        return await self.service.publish_group(
            session_id,
            run_id,
            group_key,
            resources,
            turn_sequence=turn_sequence,
        )


def _resource_bridge(
    resource_service,
    agent=_DEFAULT_AGENT,
    resource_storage_root=None,
):
    return AgentBridge(
        message_bus=MessageBus(), agent=agent, session_mapper=object(),
        mode="social", enable_heartbeat=False, enable_memory=False,
        resource_service=resource_service,
        resource_storage_root=resource_storage_root,
    )


@pytest.mark.asyncio
async def test_weixin_inbound_media_does_not_embed_storage_path_in_content():
    channel = object.__new__(WeixinChannel)
    channel._processed_ids = OrderedDict()
    channel._context_tokens = {}
    channel._save_state = Mock()
    channel._download_media_item = AsyncMock(return_value="/registry/social/meal.jpg")
    channel._handle_message = AsyncMock()

    await channel._process_message({
        "message_type": MESSAGE_TYPE_USER,
        "message_id": "message-1",
        "from_user_id": "wx-user",
        "item_list": [{"type": ITEM_IMAGE, "image_item": {}}],
    })

    kwargs = channel._handle_message.await_args.kwargs
    assert kwargs["content"] == "[image]"
    assert kwargs["media"] == ["/registry/social/meal.jpg"]


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
    bridge._active_social_sessions = {}
    bridge._social_route_lock = asyncio.Lock()
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


@pytest.mark.asyncio
async def test_social_media_is_registered_as_a_session_attachment(tmp_path: Path):
    image_path = tmp_path / "meal.jpg"
    image_path.write_bytes(b"jpg")
    resource_service = RecordingResourceService()
    bridge = _resource_bridge(resource_service, resource_storage_root=tmp_path / "resources")

    attachments = await bridge._prepare_social_attachments(
        session_id="social-session",
        channel="weixin:account",
        media=[str(image_path)],
    )

    _, run_id, declarations = resource_service.calls[0]
    assert run_id.startswith("social-inbound:")
    assert declarations[0].role.value == "attachment"
    stored_path = Path(declarations[0].locator.path)
    assert stored_path.parent.parent == (tmp_path / "resources").resolve()
    assert stored_path.read_bytes() == b"jpg"
    assert declarations[0].metadata["source"] == "social_inbound"
    assert attachments[0]["resource_id"]
    assert "url" not in attachments[0]


@pytest.mark.asyncio
async def test_social_remote_only_media_is_not_registered_as_durable():
    bridge = _resource_bridge(RecordingResourceService())

    with pytest.raises(ValueError, match="social_attachment_requires_local_file"):
        await bridge._prepare_social_attachments(
            session_id="social-session",
            channel="weixin:account",
            media=["https://temporary.example.com/image.jpg"],
        )


@pytest.mark.asyncio
async def test_social_attachment_identity_is_immutable_when_channel_path_is_reused(
    tmp_path: Path,
):
    channel_path = tmp_path / "channel" / "meal.jpg"
    channel_path.parent.mkdir()
    channel_path.write_bytes(b"first")
    resource_service = RecordingResourceService()
    bridge = _resource_bridge(
        resource_service,
        resource_storage_root=tmp_path / "resources",
    )

    [first] = await bridge._prepare_social_attachments(
        session_id="social-session",
        channel="weixin:account",
        media=[str(channel_path)],
    )
    first_path = Path(first["local_path"])
    channel_path.write_bytes(b"second")
    [second] = await bridge._prepare_social_attachments(
        session_id="social-session",
        channel="weixin:account",
        media=[str(channel_path)],
    )

    assert first["resource_id"] != second["resource_id"]
    assert first_path.read_bytes() == b"first"
    assert Path(second["local_path"]).read_bytes() == b"second"


@pytest.mark.asyncio
async def test_social_image_over_inline_limit_is_rejected_before_registration(
    tmp_path: Path,
):
    image_path = tmp_path / "large.jpg"
    with image_path.open("wb") as handle:
        handle.truncate(SOCIAL_IMAGE_MAX_BYTES + 1)
    resource_service = RecordingResourceService()
    bridge = _resource_bridge(
        resource_service,
        resource_storage_root=tmp_path / "resources",
    )

    with pytest.raises(ValueError, match="social_attachment_too_large"):
        await bridge._prepare_social_attachments(
            session_id="social-session",
            channel="weixin:account",
            media=[str(image_path)],
        )

    assert resource_service.calls == []


@pytest.mark.asyncio
async def test_social_transcript_keeps_resource_refs_for_initial_and_steered_images(
    monkeypatch,
    tmp_path: Path,
):
    image_path = tmp_path / "meal.jpg"
    image_path.write_bytes(b"jpg")
    resource_service = RecordingResourceService()

    class RecordingAgent:
        def __init__(self):
            self._session_store = {}

        async def analyze(self, **_kwargs):
            yield {
                "type": "steering_applied",
                "data": {"inputs": [{
                    "message": "补充这张图", "input_id": "steer-1",
                    "attachments": [{
                        "type": "image", "name": "detail.jpg",
                        "mime_type": "image/jpeg",
                        "resource_id": "resource-steer-1",
                        "ref_id": "resource-steer-1",
                    }],
                }]},
            }
            yield {"type": "complete", "data": {"answer": "看到了"}}

    async def no_disk_write(*_args, **_kwargs):
        return True

    monkeypatch.setattr(
        "app.social.agent_bridge.append_session_transcript_for_mode", no_disk_write
    )
    bridge = _resource_bridge(
        resource_service,
        RecordingAgent(),
        resource_storage_root=tmp_path / "resources",
    )
    attachments = await bridge._prepare_social_attachments(
        session_id="social-session", channel="weixin:account",
        media=[str(image_path)],
    )
    session = Session(session_id="social-session", query="[image]")

    await bridge._aggregate_agent_events(
        content="[image]", session_id=session.session_id, chat_id="chat",
        channel="weixin:account", attachments=attachments, session=session,
    )

    initial, steering = session.conversation_history[:2]
    assert initial["attachments"][0]["resource_id"] == attachments[0]["resource_id"]
    assert str(image_path) not in str(initial)
    assert steering["attachments"][0]["resource_id"] == "resource-steer-1"
    assert steering["attachments"][0]["url"].endswith("/resource-steer-1/content")


def test_attachment_prompt_context_uses_resource_id_not_storage_path():
    context = ReActAgent._build_attachment_reference_context([{
        "type": "image", "name": "meal.jpg",
        "local_path": "/srv/private/social/meal.jpg",
        "resource_id": "resource-123",
    }])

    assert "resource-123" in context
    assert "/srv/private/social/meal.jpg" not in context


@pytest.mark.asyncio
async def test_steering_projects_resource_refs_without_storage_paths():
    class FakeSession:
        def __init__(self):
            self.messages = []

        def add_user_message(self, content):
            self.messages.append(content)

        def get_messages_for_llm(self):
            return list(self.messages)

    memory = SimpleNamespace(session_id="social-session", session=FakeSession())
    runtime = AgentRuntime(AgentRuntimeConfig(
        memory_manager=memory, planner=object(), tool_executor=object(),
        context_builder=object(),
    ))
    state = RunState(
        session_id=memory.session_id, user_query="开始", mode="social",
        run_id="run-social",
    )
    previous = steering_registry.store
    steering_registry.store = InMemorySteeringStore()
    try:
        await steering_registry.register(state.session_id, state.run_id, state.mode)
        await steering_registry.add_input(
            state.session_id,
            "补充这张图",
            attachments=[{
                "type": "image", "name": "detail.jpg",
                "local_path": "/srv/private/social/detail.jpg",
                "mime_type": "image/jpeg", "resource_id": "resource-steer-1",
            }],
        )

        [event] = [item async for item in runtime._apply_steering_inputs(state)]

        projected = event["data"]["inputs"][0]["attachments"][0]
        assert projected["resource_id"] == "resource-steer-1"
        assert "local_path" not in projected
        assert "/srv/private/social/detail.jpg" not in memory.session.messages[-1]
    finally:
        await steering_registry.unregister(state.session_id, state.run_id)
        steering_registry.store = previous


@pytest.mark.asyncio
async def test_terminal_steering_drain_emits_safe_deferred_user_input():
    memory = SimpleNamespace(
        session_id="social-session",
        session=SimpleNamespace(
            add_user_message=lambda _content: None,
            get_messages_for_llm=lambda: [],
        ),
    )
    runtime = AgentRuntime(AgentRuntimeConfig(
        memory_manager=memory, planner=object(), tool_executor=object(),
        context_builder=object(),
    ))
    state = RunState(
        session_id=memory.session_id, user_query="开始", mode="social",
        run_id="run-social",
    )
    previous = steering_registry.store
    steering_registry.store = InMemorySteeringStore()
    try:
        await steering_registry.register(state.session_id, state.run_id, state.mode)
        await steering_registry.add_input(
            state.session_id,
            "终态前补充",
            attachments=[{
                "type": "image", "name": "detail.jpg",
                "local_path": "/srv/private/detail.jpg",
                "resource_id": "resource-deferred-1",
            }],
        )

        event = await runtime._close_steering_event(state)

        assert event["type"] == "steering_deferred"
        projected = event["data"]["inputs"][0]["attachments"][0]
        assert projected["resource_id"] == "resource-deferred-1"
        assert "local_path" not in projected
    finally:
        await steering_registry.unregister(state.session_id, state.run_id)
        steering_registry.store = previous

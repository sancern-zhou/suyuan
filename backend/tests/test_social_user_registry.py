import pytest

from app.social.agent_bridge import AgentBridge
from app.social.events import InboundMessage
from app.social.message_bus import MessageBus
from app.social.user_registry import (
    SocialUserCreate,
    SocialUserRegistry,
    SocialUserUpdate,
)


@pytest.mark.asyncio
async def test_binding_code_binds_pending_user_once():
    registry = SocialUserRegistry()
    user = await registry.create_user(
        SocialUserCreate(name="张三", email="zhangsan@example.com"),
        bind_code="8327",
    )

    bound = await registry.bind_by_code(
        message_text="8327",
        channel="weixin:auto_a",
        bot_account="wx_bot",
        sender_id="wx_user_1",
    )

    assert bound is not None
    assert bound.id == user.id
    assert bound.status == "active"
    assert bound.social_user_id == "weixin:auto_a:wx_bot:wx_user_1"

    duplicate = await registry.bind_by_code(
        message_text="8327",
        channel="weixin:auto_a",
        bot_account="wx_bot",
        sender_id="wx_user_2",
    )

    assert duplicate is None


@pytest.mark.asyncio
async def test_existing_social_identity_cannot_bind_to_another_pending_user():
    registry = SocialUserRegistry()
    await registry.create_user(SocialUserCreate(name="张三"), bind_code="8327")
    await registry.create_user(SocialUserCreate(name="李四"), bind_code="9146")

    first = await registry.bind_by_code(
        message_text="8327",
        channel="weixin:auto_a",
        bot_account="wx_bot",
        sender_id="wx_user_1",
    )
    second = await registry.bind_by_code(
        message_text="9146",
        channel="weixin:auto_a",
        bot_account="wx_bot",
        sender_id="wx_user_1",
    )

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_update_user_allows_name_email_and_status_changes():
    registry = SocialUserRegistry()
    user = await registry.create_user(SocialUserCreate(name="张三"), bind_code="8327")

    updated = await registry.update_user(
        user.id,
        SocialUserUpdate(name="张三丰", email="new@example.com", status="disabled"),
    )

    assert updated is not None
    assert updated.name == "张三丰"
    assert updated.email == "new@example.com"
    assert updated.status == "disabled"


@pytest.mark.asyncio
async def test_agent_bridge_intercepts_binding_code_without_creating_agent_session(monkeypatch):
    registry = SocialUserRegistry()
    await registry.create_user(SocialUserCreate(name="王五"), bind_code="7259")
    bus = MessageBus()

    async def fake_get_bot_account(_channel):
        return "wx_bot"

    class FailingSessionMapper:
        async def get_or_create_session(self, *_args, **_kwargs):
            raise AssertionError("binding messages must not create agent sessions")

    import app.social.user_registry as user_registry_module

    monkeypatch.setattr(user_registry_module, "get_social_user_registry", lambda: registry)

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.mode = "social"
    bridge.message_bus = bus
    bridge.session_mapper = FailingSessionMapper()
    bridge._get_bot_account = fake_get_bot_account

    await bridge._route_message(
        InboundMessage(
            channel="weixin:auto_a",
            sender_id="wx_user_1",
            chat_id="wx_user_1",
            content="7259",
        )
    )

    outbound = await bus.consume_outbound()
    assert outbound.content == "绑定成功，王五。现在可以正常使用了。"


@pytest.mark.asyncio
async def test_generated_binding_code_is_four_digits():
    registry = SocialUserRegistry()
    user = await registry.create_user(SocialUserCreate(name="赵六"))

    assert user.bind_code is not None
    assert user.bind_code.isdigit()
    assert len(user.bind_code) == 4

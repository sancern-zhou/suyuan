import pytest
from types import SimpleNamespace

from app.agent.react_agent import ReActAgent
from app.agent.session.conversation_persistence import ConversationPersistenceService
from app.agent.session.models import Session
from app.agent.session.session_manager import SessionManager


@pytest.mark.asyncio
async def test_social_mode_uses_local_file_session_manager(tmp_path, monkeypatch):
    from app.agent.session import session_manager as file_session_module
    from app.agent.session import session_resolver

    local_manager = SessionManager(storage_base_path=str(tmp_path))
    monkeypatch.setattr(file_session_module, "_global_session_manager", local_manager)

    manager = session_resolver.get_session_manager_for_mode("social")
    assert manager is local_manager

    session = Session(
        session_id="social_session_test",
        query="第一轮",
        conversation_history=[{"type": "user", "content": "第一轮"}],
    )

    assert await session_resolver.save_session_metadata_for_mode(session, mode="social")

    loaded = await session_resolver.load_session_for_mode(
        "social_session_test",
        mode="social",
    )

    assert loaded is not None
    assert loaded.conversation_history == [{"type": "user", "content": "第一轮"}]
    assert (tmp_path / "social_session_test.json").exists()


def test_social_persistence_appends_current_turn_without_duplicate_history():
    session = Session(
        session_id="social_session_existing",
        query="第一轮",
        conversation_history=[
            {"type": "user", "content": "第一轮", "timestamp": "2026-06-04T10:00:00"},
            {"type": "final", "content": "第一轮回复", "timestamp": "2026-06-04T10:00:01"},
        ],
    )

    current_turn = [
        {"type": "final", "content": "第一轮回复", "timestamp": "2026-06-04T10:00:01"},
        {"type": "user", "content": "第二轮", "timestamp": "2026-06-04T10:01:00"},
        {"type": "final", "content": "第二轮回复", "timestamp": "2026-06-04T10:01:01"},
    ]

    ConversationPersistenceService().append_complete(
        session,
        display_history=current_turn,
        collected_data_ids=[],
        collected_visuals=[],
    )

    assert session.conversation_history == [
        {"type": "user", "content": "第一轮", "timestamp": "2026-06-04T10:00:00"},
        {"type": "final", "content": "第一轮回复", "timestamp": "2026-06-04T10:00:01"},
        {"type": "user", "content": "第二轮", "timestamp": "2026-06-04T10:01:00"},
        {"type": "final", "content": "第二轮回复", "timestamp": "2026-06-04T10:01:01"},
    ]


def test_social_append_persistence_preserves_existing_artifact_metadata():
    session = Session(
        session_id="social_session_existing",
        query="第一轮",
        data_ids=["data_a"],
        visual_ids=["visual_a"],
        metadata={"visualizations": [{"id": "visual_a"}], "visuals_count": 1},
        conversation_history=[
            {"type": "user", "content": "第一轮", "timestamp": "2026-06-04T10:00:00"},
        ],
    )

    ConversationPersistenceService().append_complete(
        session,
        display_history=[
            {"type": "user", "content": "第二轮", "timestamp": "2026-06-04T10:01:00"},
        ],
        collected_data_ids=[],
        collected_visuals=[],
    )

    assert session.data_ids == ["data_a"]
    assert session.visual_ids == ["visual_a"]
    assert session.metadata["visualizations"] == [{"id": "visual_a"}]


@pytest.mark.asyncio
async def test_react_agent_restores_social_history_from_local_session_manager(tmp_path, monkeypatch):
    from app.agent.session import session_manager as file_session_module

    local_manager = SessionManager(storage_base_path=str(tmp_path))
    monkeypatch.setattr(file_session_module, "_global_session_manager", local_manager)

    local_manager.save_session(
        Session(
            session_id="social_session_restore",
            query="第一轮",
            conversation_history=[
                {"type": "user", "content": "第一轮", "timestamp": "2026-06-04T10:00:00"},
                {"type": "final", "content": "第一轮回复", "timestamp": "2026-06-04T10:00:01"},
            ],
        )
    )

    agent = ReActAgent(tool_registry={})

    session_id, memory_manager, created_new = await agent._get_or_create_session(
        "social_session_restore",
        manual_mode="social",
    )

    assert session_id == "social_session_restore"
    assert created_new is False
    assert len(memory_manager.session.conversation_history) == 2


@pytest.mark.asyncio
async def test_social_mode_does_not_override_llm_provider_or_model(monkeypatch):
    from app.agent import react_agent as react_agent_module

    captured_kwargs = {}

    class FakeReActLoop:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self.context_builder = SimpleNamespace()

        async def run(self, **kwargs):
            yield {
                "type": "complete",
                "data": {"answer": "ok"},
            }

    monkeypatch.setattr(react_agent_module, "ReActLoop", FakeReActLoop)

    agent = ReActAgent(tool_registry={})

    events = [
        event
        async for event in agent.analyze(
            user_query="hello",
            session_id="social_no_model_override",
            manual_mode="social",
            user_identifier="weixin:bot:user",
        )
    ]

    assert events[-1]["type"] == "complete"
    assert "llm_provider" not in captured_kwargs
    assert "llm_model" not in captured_kwargs
    assert captured_kwargs["auto_profile"] is None


@pytest.mark.asyncio
async def test_chart_mode_uses_normal_auto_chain(monkeypatch):
    from app.agent import react_agent as react_agent_module

    captured_kwargs = {}

    class FakeReActLoop:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self.context_builder = SimpleNamespace()

        async def run(self, **kwargs):
            yield {
                "type": "complete",
                "data": {"answer": "ok"},
            }

    monkeypatch.setattr(react_agent_module, "ReActLoop", FakeReActLoop)

    agent = ReActAgent(tool_registry={})
    image_attachment = {
        "type": "image",
        "name": "ref.png",
        "url": "https://example.com/ref.png",
    }

    events = [
        event
        async for event in agent.analyze(
            user_query="按参考图生成图表",
            session_id="chart_session_profile",
            manual_mode="chart",
            attachments=[image_attachment],
        )
    ]

    assert events[-1]["type"] == "complete"
    assert captured_kwargs["auto_profile"] is None
    assert captured_kwargs["attachments"] == [image_attachment]


@pytest.mark.asyncio
async def test_assistant_mode_uses_normal_auto_chain_and_forwards_runtime_attachments(monkeypatch):
    from app.agent import react_agent as react_agent_module

    captured_kwargs = {}

    class FakeReActLoop:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self.context_builder = SimpleNamespace()

        async def run(self, **kwargs):
            yield {
                "type": "complete",
                "data": {"answer": "ok"},
            }

    monkeypatch.setattr(react_agent_module, "ReActLoop", FakeReActLoop)

    agent = ReActAgent(tool_registry={})

    image_attachment = {
        "type": "image",
        "name": "ref.png",
        "url": "https://example.com/ref.png",
    }

    events = [
        event
        async for event in agent.analyze(
            user_query="普通助手问题",
            session_id="assistant_session_profile",
            manual_mode="assistant",
            attachments=[image_attachment],
        )
    ]

    assert events[-1]["type"] == "complete"
    assert captured_kwargs["auto_profile"] is None
    assert captured_kwargs["attachments"] == [image_attachment]

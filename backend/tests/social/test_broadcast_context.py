import pytest

from app.agent.session.models import Session
from app.social.broadcast_context import persist_broadcast_context
from app.social.broadcast_service import SocialBroadcastService


class FakeSessionMapper:
    def __init__(self, session_id="social-1", all_user_ids=None):
        self.session_id = session_id
        self.all_user_ids = all_user_ids or []
        self.get_all_calls = 0

    async def get_or_create_session(self, social_user_id, mode):
        assert mode == "social"
        return self.session_id

    async def get_all_social_user_ids(self):
        self.get_all_calls += 1
        return list(self.all_user_ids)


class FakeMessageBus:
    def __init__(self):
        self.messages = []

    async def publish_outbound(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_broadcast_is_appended_as_assistant_message_with_attachment(
    monkeypatch, tmp_path
):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    session = Session(session_id="social-1", query="social")
    saved = []

    async def fake_load(session_id, *, mode):
        return session

    async def fake_append(value, *, mode):
        saved.append(value)
        return True

    monkeypatch.setattr("app.social.broadcast_context.load_session_for_mode", fake_load)
    monkeypatch.setattr(
        "app.social.broadcast_context.append_session_transcript_for_mode",
        fake_append,
    )

    ok = await persist_broadcast_context(
        session_mapper=FakeSessionMapper(),
        social_user_id="weixin:bot:user",
        message="运城告警摘要",
        media=[str(report)],
        metadata={
            "task_id": "task-1",
            "event_id": "alert-1",
            "event_type": "yuncheng.alert.created",
            "execution_id": "exec-1",
        },
    )

    assert ok is True
    assert saved[0].conversation_history[-1]["role"] == "assistant"
    attachment = saved[0].conversation_history[-1]["data"]["attachments"][0]
    assert attachment["path"] == str(report)
    assert saved[0].office_documents[-1]["file_path"] == str(report)


@pytest.mark.asyncio
async def test_same_broadcast_message_is_idempotent(monkeypatch, tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    session = Session(session_id="social-1", query="social")

    async def fake_load(session_id, *, mode):
        return session

    async def fake_append(value, *, mode):
        return True

    monkeypatch.setattr("app.social.broadcast_context.load_session_for_mode", fake_load)
    monkeypatch.setattr(
        "app.social.broadcast_context.append_session_transcript_for_mode",
        fake_append,
    )
    kwargs = {
        "session_mapper": FakeSessionMapper(),
        "social_user_id": "weixin:bot:user",
        "message": "运城告警摘要",
        "media": [str(report)],
        "metadata": {
            "task_id": "task-1",
            "event_id": "alert-1",
            "event_type": "yuncheng.alert.created",
            "execution_id": "exec-1",
        },
    }

    assert await persist_broadcast_context(**kwargs)
    assert await persist_broadcast_context(**kwargs)

    broadcasts = [
        item for item in session.conversation_history if item.get("type") == "broadcast"
    ]
    documents = [
        item
        for item in session.office_documents
        if item.get("file_path") == str(report)
    ]
    assert len(broadcasts) == 1
    assert len(documents) == 1


@pytest.mark.asyncio
async def test_explicit_empty_targets_never_broadcast_to_all_users():
    mapper = FakeSessionMapper(all_user_ids=["weixin:bot:unexpected"])
    bus = FakeMessageBus()
    service = SocialBroadcastService(message_bus=bus, session_mapper=mapper)

    result = await service.broadcast(
        message="告警摘要",
        target_user_ids=[],
    )

    assert result["success"] is False
    assert mapper.get_all_calls == 0
    assert bus.messages == []


@pytest.mark.asyncio
async def test_targeted_broadcast_persists_context_for_each_success(
    monkeypatch,
):
    mapper = FakeSessionMapper()
    bus = FakeMessageBus()
    persisted = []

    async def fake_persist(**kwargs):
        persisted.append(kwargs["social_user_id"])
        return True

    monkeypatch.setattr(
        "app.social.broadcast_service.persist_broadcast_context",
        fake_persist,
        raising=False,
    )
    service = SocialBroadcastService(message_bus=bus, session_mapper=mapper)

    result = await service.broadcast(
        message="告警摘要",
        target_user_ids=["weixin:bot:one", "weixin:bot:two"],
        persist_context=True,
        context_metadata={
            "task_id": "task-1",
            "event_id": "alert-1",
            "event_type": "yuncheng.alert.created",
            "execution_id": "exec-1",
        },
    )

    assert result["success"] is True
    assert len(bus.messages) == 2
    assert persisted == ["weixin:bot:one", "weixin:bot:two"]
    assert all(row["context_persisted"] for row in result["delivery_results"])

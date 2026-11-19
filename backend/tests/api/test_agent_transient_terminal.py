"""SSE 端到端：瞬时故障只在日志留存，终态落库/上屏都是友好文案。"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.agent.session.models import Session
from app.api import agent as routes
from app.auth.models import CurrentUser
from app.services.llm_failover import TRANSIENT_FAILURE_USER_MESSAGE


USER = CurrentUser(id="alice", username="alice", display_name="Alice")
RAW_ERROR = (
    "Server error '504 Gateway Time-out' for url "
    "'http://<llm-gateway>:41080/large-model/api/v1/chat/completions'"
)


class RecordingPersistence:
    instances = []

    def __init__(self) -> None:
        self.terminals = []
        self.completes = []
        RecordingPersistence.instances.append(self)

    def append_terminal(self, session, **kwargs) -> None:
        self.terminals.append(kwargs["terminal_message"])

    def append_complete(self, session, **kwargs) -> None:
        self.completes.append(kwargs)


class FakeAgent:
    def __init__(self, events) -> None:
        self.events = events
        self._session_store = {}

    async def analyze(self, **kwargs):
        for event in self.events:
            yield event


class BodyRequest:
    async def json(self):
        return {}


class Catalog:
    async def find(self, session_id):
        return SimpleNamespace(mode="assistant")

    async def require_write(self, session_id, user):
        return None


@pytest.fixture
def stream_env(monkeypatch):
    """把路由的外部依赖替换成内存替身，跑通 unlocked_event_generator。"""
    RecordingPersistence.instances.clear()
    session = Session(session_id="web-session", query="q", metadata={"mode": "assistant"})
    saved = {"metadata": 0, "transcript": 0}

    async def noop(*args, **kwargs):
        return True

    async def load(*args, **kwargs):
        return session

    async def register(*args, **kwargs):
        return asyncio.Event()

    async def save_transcript(loaded_session):
        saved["transcript"] += 1
        return True

    @asynccontextmanager
    async def lock(*args, **kwargs):
        yield

    async def persist_new_web_session(**kwargs):
        return None

    monkeypatch.setattr(routes, "ConversationPersistenceService", RecordingPersistence)
    monkeypatch.setattr(routes, "get_session_manager", lambda: SimpleNamespace(
        load_session_light=load,
        load_session=load,
        save_session_metadata=noop,
        append_session_transcript=save_transcript,
    ))
    monkeypatch.setattr(routes, "session_advisory_lock", lock)
    monkeypatch.setattr(routes, "persist_new_web_session", persist_new_web_session)
    monkeypatch.setattr(routes.cancellation_registry, "register", register)
    for name in ("attach_run_task", "arm_run_task", "unregister", "can_finalize"):
        monkeypatch.setattr(routes.cancellation_registry, name, noop)
    for name in ("register", "can_write", "complete", "revoke", "begin_pause"):
        monkeypatch.setattr(routes.run_ownership_registry, name, noop)
    return saved


def _request() -> routes.AgentAnalyzeRequest:
    return routes.AgentAnalyzeRequest(
        query="分析一下",
        session_id="web-session",
        mode="assistant",
        skill_ids=[],
        context_refs=[],
    )


async def _collect_chunks() -> tuple[list[str], RecordingPersistence]:
    response = await routes.analyze_stream(
        _request(),
        BodyRequest(),
        user=USER,
        catalog=Catalog(),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    await response.body_iterator.aclose()
    return chunks, RecordingPersistence.instances[-1]


def test_fatal_error_persists_friendly_message_and_keeps_technical_error_out(
    monkeypatch, stream_env
):
    raw_fatal = {
        "type": "fatal_error",
        "stream": "error",
        "data": {
            "error": RAW_ERROR,
            "error_type": "RuntimeError",
            "user_message": TRANSIENT_FAILURE_USER_MESSAGE,
        },
    }
    monkeypatch.setattr(
        routes, "multi_expert_agent_instance", FakeAgent([{"type": "start", "data": {}}, raw_fatal])
    )

    chunks, persistence = asyncio.run(_collect_chunks())

    wire = "".join(
        chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks
    )
    assert '"user_message"' in wire

    terminals = persistence.terminals
    assert len(terminals) == 1
    assert terminals[0]["content"] == TRANSIENT_FAILURE_USER_MESSAGE
    assert "504" not in terminals[0]["content"]
    # 技术错误仍保留在事件数据里，供日志/审计使用
    assert terminals[0]["data"]["error"] == RAW_ERROR
    assert stream_env["transcript"] == 1


def test_non_transient_fatal_error_keeps_technical_message(monkeypatch, stream_env):
    raw_fatal = {
        "type": "fatal_error",
        "stream": "error",
        "data": {"error": RAW_ERROR, "error_type": "RuntimeError"},
    }
    monkeypatch.setattr(
        routes, "multi_expert_agent_instance", FakeAgent([{"type": "start", "data": {}}, raw_fatal])
    )

    _chunks, persistence = asyncio.run(_collect_chunks())

    assert persistence.terminals[0]["content"] == RAW_ERROR

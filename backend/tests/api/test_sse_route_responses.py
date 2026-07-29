import asyncio
import json

import pytest
from sse_starlette import EventSourceResponse
from sse_starlette.sse import AppStatus

from app.auth.models import CurrentUser
from app.routers import agent, knowledge_qa, report_generation
from app.routers.expert_deliberation import run_deliberation_stream
from app.services.expert_deliberation import ExpertDeliberationEngine
from app.services.expert_deliberation.schemas import (
    DeliberationRequest,
    DeliberationResult,
    TimeRange,
)
from config.settings import settings


@pytest.fixture(autouse=True)
def reset_sse_app_status_event():
    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None


def _assert_system_sse_response(response):
    assert isinstance(response, EventSourceResponse)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.ping_interval == settings.sse_heartbeat_interval_seconds
    assert response.send_timeout == settings.sse_send_timeout_seconds


async def _collect_wire_frames(response):
    return [frame async for frame in response.body_iterator]


def _http_scope(path):
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("test", 1234),
        "server": ("test", 80),
    }


def test_report_generation_uses_system_sse_response():
    response = report_generation._stream_template_report_agent(
        template_content="# Template",
        target_time_range={"start": "2026-07-01", "end": "2026-07-15"},
    )

    _assert_system_sse_response(response)


async def test_report_generation_preserves_first_and_terminal_frames(monkeypatch):
    class FakeAgent:
        async def _get_or_create_session(self, **kwargs):
            return "session-1", object(), True

        async def analyze(self, **kwargs):
            yield {"type": "streaming_text", "data": {"chunk": "answer"}}

        async def _mark_session_used(self, session_id):
            return None

    monkeypatch.setattr(report_generation, "get_react_agent", lambda: FakeAgent())
    response = report_generation._stream_template_report_agent(
        template_content="# Template",
        target_time_range={"start": "2026-07-01", "end": "2026-07-15"},
    )

    frames = await _collect_wire_frames(response)

    assert frames[0].startswith(b"event: start\n")
    assert frames[-1].startswith(b"event: complete\n")
    assert sum(frame.startswith(b"event: start\n") for frame in frames) == 1
    assert sum(frame.startswith(b"event: complete\n") for frame in frames) == 1


async def test_expert_deliberation_uses_system_sse_response():
    response = await run_deliberation_stream(DeliberationRequest())

    _assert_system_sse_response(response)


async def test_expert_deliberation_preserves_first_and_terminal_frames(monkeypatch):
    async def fail_run_async(self, request, progress_callback=None):
        raise RuntimeError("deliberation failed")

    monkeypatch.setattr(ExpertDeliberationEngine, "run_async", fail_run_async)
    response = await run_deliberation_stream(DeliberationRequest())

    frames = await _collect_wire_frames(response)

    assert b'"event": "connected"' in frames[0]
    assert b'"event": "error"' in frames[-1]
    assert b"deliberation failed" in frames[-1]


async def test_expert_deliberation_success_preserves_result_terminal_frame(monkeypatch):
    result = DeliberationResult(
        topic="test",
        region="test",
        time_range=TimeRange(),
        pollutants=[],
        facts=[],
        experts=[],
        analyses=[],
        conclusions=[],
        dissents=[],
        forbidden_claims=[],
        report_markdown="done",
    )

    async def succeed_run_async(self, request, progress_callback=None):
        return result

    monkeypatch.setattr(ExpertDeliberationEngine, "run_async", succeed_run_async)
    response = await run_deliberation_stream(DeliberationRequest())

    frames = await _collect_wire_frames(response)

    assert b'"event": "connected"' in frames[0]
    assert b'"event": "result"' in frames[-1]
    assert b'"report_markdown": "done"' in frames[-1]


async def test_knowledge_qa_preserves_start_and_complete_frames(monkeypatch):
    class Store:
        async def get_or_create_session(self, **kwargs):
            return "knowledge-session", [], True

    async def fake_store(db):
        return Store()

    async def fake_search(**kwargs):
        return []

    async def fake_streaming_answer(**kwargs):
        yield 'data: {"type": "start"}\n\n'
        yield 'data: {"type": "complete"}\n\n'

    monkeypatch.setattr(knowledge_qa, "get_conversation_store", fake_store)
    monkeypatch.setattr(knowledge_qa, "search_knowledge_bases", fake_search)
    monkeypatch.setattr(knowledge_qa, "generate_streaming_answer", fake_streaming_answer)

    response = await knowledge_qa.knowledge_qa_stream(
        knowledge_qa.KnowledgeQARequest(query="question"),
        db=object(),
        user=CurrentUser(id="user-1", username="user", display_name="User"),
    )
    frames = await _collect_wire_frames(response)

    assert frames == [
        b'data: {"type": "start"}\n\n',
        b'data: {"type": "complete"}\n\n',
    ]


async def test_agent_heartbeat_stays_out_of_wire_contract_and_persistence(monkeypatch):
    persisted_sessions = []

    class SessionManager:
        async def load_session_light(self, session_id):
            return None

        async def save_session_metadata(self, session):
            return True

        async def append_session_transcript(self, session):
            persisted_sessions.append(session.model_copy(deep=True))

        async def delete_session(self, session_id):
            raise AssertionError("successful persistence must not roll back")

    class Catalog:
        async def find(self, session_id):
            return None

        async def register(self, **kwargs):
            return None

    class RawRequest:
        async def json(self):
            return {}

    class FakeAgent:
        def __init__(self):
            self._session_store = {}

        async def analyze(self, **kwargs):
            yield {"type": "start", "data": {"session_id": "agent-session"}}
            await asyncio.sleep(0.03)
            yield {
                "type": "complete",
                "data": {"session_id": "agent-session", "answer": "done"},
            }

    monkeypatch.setattr(agent, "get_session_manager", lambda: SessionManager())
    monkeypatch.setattr(agent, "multi_expert_agent_instance", FakeAgent())

    response = await agent.analyze_stream(
        agent.AgentAnalyzeRequest(
            query="question",
            session_id="agent-session",
            skill_ids=[],
            context_refs=[],
        ),
        RawRequest(),
        user=CurrentUser(id="user-1", username="user", display_name="User"),
        catalog=Catalog(),
    )
    response.ping_interval = 0.01
    sent_bodies = []

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        if message["type"] == "http.response.body":
            sent_bodies.append(message.get("body", b""))

    await asyncio.wait_for(
        response(_http_scope("/api/agent/analyze"), receive, send),
        timeout=1,
    )

    business_frames = [body for body in sent_bodies if body.startswith(b"data: ")]
    assert b'"type": "start"' in business_frames[0]
    assert b'"type": "complete"' in business_frames[-1]
    assert any(body.startswith(b": keepalive") for body in sent_bodies)
    assert len(persisted_sessions) == 1
    persisted_json = json.dumps(
        persisted_sessions[0].conversation_history,
        ensure_ascii=False,
    )
    assert "keepalive" not in persisted_json
    assert [message["type"] for message in persisted_sessions[0].conversation_history] == [
        "user",
        "final",
    ]


async def test_expert_deliberation_disconnect_cancels_engine_task(monkeypatch):
    engine_started = asyncio.Event()
    engine_cleaned = asyncio.Event()
    release_engine = asyncio.Event()
    engine_cancelled = False
    disconnect = asyncio.Event()

    async def fake_run_async(self, request, progress_callback=None):
        nonlocal engine_cancelled
        engine_started.set()
        try:
            await release_engine.wait()
        except asyncio.CancelledError:
            engine_cancelled = True
            raise
        finally:
            engine_cleaned.set()

    monkeypatch.setattr(ExpertDeliberationEngine, "run_async", fake_run_async)
    response = await run_deliberation_stream(DeliberationRequest())

    async def receive():
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body" and b'"event": "connected"' in message.get(
            "body", b""
        ):
            await engine_started.wait()
            disconnect.set()

    await asyncio.wait_for(
        response(_http_scope("/expert-deliberation/run-stream"), receive, send),
        timeout=1,
    )
    await asyncio.sleep(0)

    cancelled_before_release = engine_cancelled
    release_engine.set()
    await asyncio.wait_for(engine_cleaned.wait(), timeout=1)
    assert cancelled_before_release is True

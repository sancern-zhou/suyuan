import asyncio

from sse_starlette import EventSourceResponse

from app.routers import report_generation
from app.routers.expert_deliberation import run_deliberation_stream
from app.services.expert_deliberation import ExpertDeliberationEngine
from app.services.expert_deliberation.schemas import DeliberationRequest
from config.settings import settings


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

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/expert-deliberation/run-stream",
        "raw_path": b"/expert-deliberation/run-stream",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("test", 1234),
        "server": ("test", 80),
    }
    await asyncio.wait_for(response(scope, receive, send), timeout=1)
    await asyncio.sleep(0)

    cancelled_before_release = engine_cancelled
    release_engine.set()
    await asyncio.wait_for(engine_cleaned.wait(), timeout=1)
    assert cancelled_before_release is True

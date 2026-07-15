import asyncio

import pytest
from sse_starlette import EventSourceResponse
from sse_starlette.sse import AppStatus

from app.core.sse import _encode_sse_frames, create_sse_response
from config.settings import Settings


async def _collect(source):
    return [item async for item in source]


@pytest.fixture(autouse=True)
def reset_sse_app_status():
    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None


def test_sse_transport_defaults():
    config = Settings(_env_file=None)

    assert config.sse_heartbeat_interval_seconds == 15.0
    assert config.sse_send_timeout_seconds == 30.0


def test_sse_transport_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("SSE_HEARTBEAT_INTERVAL_SECONDS", "22.5")
    monkeypatch.setenv("SSE_SEND_TIMEOUT_SECONDS", "45")

    config = Settings(_env_file=None)

    assert config.sse_heartbeat_interval_seconds == 22.5
    assert config.sse_send_timeout_seconds == 45.0


@pytest.mark.asyncio
async def test_encode_sse_frames_preserves_existing_wire_format():
    async def source():
        yield 'data: {"type":"start"}\n\n'
        yield b'data: {"type":"complete"}\n\n'
        yield bytearray(b": existing-comment\n\n")
        yield memoryview(b'data: {"type":"final"}\n\n')

    frames = await _collect(_encode_sse_frames(source()))

    assert frames == [
        b'data: {"type":"start"}\n\n',
        b'data: {"type":"complete"}\n\n',
        b": existing-comment\n\n",
        b'data: {"type":"final"}\n\n',
    ]


@pytest.mark.asyncio
async def test_encode_sse_frames_rejects_non_wire_values():
    async def source():
        yield {"data": "not pre-serialized"}

    with pytest.raises(TypeError, match="SSE source must yield str or bytes-like frames"):
        await _collect(_encode_sse_frames(source()))


def test_create_sse_response_applies_system_transport_policy():
    async def source():
        yield 'data: {"type":"complete"}\n\n'

    response = create_sse_response(
        source(),
        heartbeat_interval_seconds=0.05,
        send_timeout_seconds=0.25,
        headers={"X-Route-Name": "test", "Cache-Control": "public"},
    )

    assert isinstance(response, EventSourceResponse)
    assert response.media_type == "text/event-stream"
    assert response.ping_interval == 0.05
    assert response.send_timeout == 0.25
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["x-route-name"] == "test"
    assert response.ping_message_factory().encode() == b": keepalive\r\n\r\n"


def _http_scope():
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/events",
        "raw_path": b"/events",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("test", 1234),
        "server": ("test", 80),
    }


@pytest.mark.asyncio
async def test_idle_stream_sends_comment_heartbeat_and_cleans_up_on_disconnect():
    source_cleaned = asyncio.Event()
    disconnect = asyncio.Event()
    sent = []

    async def source():
        try:
            await asyncio.Event().wait()
            yield b"unreachable"
        finally:
            source_cleaned.set()

    async def receive():
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body", b"").startswith(
            b": keepalive"
        ):
            disconnect.set()

    response = create_sse_response(
        source(),
        heartbeat_interval_seconds=0.01,
        send_timeout_seconds=0.25,
    )
    await asyncio.wait_for(response(_http_scope(), receive, send), timeout=1)

    bodies = [message.get("body", b"") for message in sent]
    assert any(body.startswith(b": keepalive") for body in bodies)
    await asyncio.wait_for(source_cleaned.wait(), timeout=1)


@pytest.mark.asyncio
async def test_business_frames_are_sent_once_and_in_order():
    sent = []

    async def source():
        yield 'data: {"type":"start"}\n\n'
        yield 'data: {"type":"complete"}\n\n'

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)

    response = create_sse_response(
        source(),
        heartbeat_interval_seconds=10,
        send_timeout_seconds=0.25,
    )
    await asyncio.wait_for(response(_http_scope(), receive, send), timeout=1)

    bodies = [
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body" and message.get("body")
    ]
    assert bodies == [
        b'data: {"type":"start"}\n\n',
        b'data: {"type":"complete"}\n\n',
    ]


@pytest.mark.asyncio
async def test_source_exception_terminates_the_response():
    async def source():
        raise RuntimeError("source exploded")
        yield b"unreachable"

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        return None

    response = create_sse_response(
        source(),
        heartbeat_interval_seconds=10,
        send_timeout_seconds=0.25,
    )
    with pytest.raises(BaseException) as exc:
        await asyncio.wait_for(response(_http_scope(), receive, send), timeout=1)

    assert "source exploded" in repr(exc.value)


@pytest.mark.asyncio
async def test_stalled_socket_send_times_out_and_closes_source():
    source_cleaned = asyncio.Event()

    async def source():
        try:
            yield b'data: {"type":"start"}\n\n'
            await asyncio.Event().wait()
        finally:
            source_cleaned.set()

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            await asyncio.Event().wait()

    response = create_sse_response(
        source(),
        heartbeat_interval_seconds=10,
        send_timeout_seconds=0.01,
    )
    with pytest.raises(BaseException) as exc:
        await asyncio.wait_for(response(_http_scope(), receive, send), timeout=1)

    assert "SendTimeoutError" in repr(exc.value)
    await asyncio.wait_for(source_cleaned.wait(), timeout=1)

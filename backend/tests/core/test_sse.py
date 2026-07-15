import pytest

from app.core.sse import _encode_sse_frames
from config.settings import Settings


async def _collect(source):
    return [item async for item in source]


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

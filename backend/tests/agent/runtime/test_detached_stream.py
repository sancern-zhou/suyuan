"""RunEventStream 契约测试：镜像、回放、重连、失败降级。"""

import pytest

from app.agent.runtime.detached_stream import (
    STREAM_CLOSED_EVENT_TYPE,
    STREAM_LOST_EVENT_TYPE,
    STREAM_OPEN_EVENT_TYPE,
    RunEventStream,
    parse_sse_payload,
)


class FakeRedis:
    """覆盖 RunEventStream 所用命令的最小内存 Redis。"""

    def __init__(self, *, fail_xadd: bool = False):
        self.fail_xadd = fail_xadd
        self.streams: dict[str, list[tuple[str, dict]]] = {}
        self.strings: dict[str, str] = {}
        self._seq: dict[str, int] = {}

    async def xadd(self, key, fields, id="*", maxlen=None, approximate=False):
        if self.fail_xadd:
            raise ConnectionError("redis unavailable")
        seq = self._seq.get(key, 0) + 1
        self._seq[key] = seq
        entry_id = f"{seq}-{seq}"
        self.streams.setdefault(key, []).append((entry_id, dict(fields)))
        return entry_id

    async def xread(self, streams, block=None, count=None):
        result = {}
        for key, last_id in streams.items():
            entries = [
                (eid, fields)
                for eid, fields in self.streams.get(key, [])
                if _entry_gt(eid, last_id)
            ]
            if entries:
                result[key] = entries[: count or len(entries)]
        return result

    async def expire(self, key, ttl):
        return True

    async def set(self, key, value, ex=None):
        self.strings[key] = value
        return True

    async def get(self, key):
        return self.strings.get(key)

    async def delete(self, key):
        return self.strings.pop(key, None) is not None

    def scan_iter(self, match="*"):
        prefix = match.rstrip("*")
        keys = [key for key in list(self.strings) if key.startswith(prefix)]

        async def _iterate():
            for key in keys:
                yield key

        return _iterate()


def _entry_gt(a: str, b: str) -> bool:
    return tuple(int(p) for p in a.split("-")) > tuple(int(p) for p in b.split("-"))


def _sse(event_type: str, data: dict | None = None) -> str:
    import json

    payload = {"type": event_type}
    if data is not None:
        payload["data"] = data
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _event_frames(frames) -> list[str]:
    """过滤 keepalive 注释帧，仅保留业务事件帧。"""
    return [frame for frame in frames if not frame.startswith(":")]


@pytest.fixture
def stream() -> RunEventStream:
    return RunEventStream(FakeRedis(), read_block_ms=0)


@pytest.mark.asyncio
async def test_parse_sse_payload_rejects_non_data_frames():
    assert parse_sse_payload("data: {\"type\":\"complete\"}\n\n") == {"type": "complete"}
    assert parse_sse_payload(": keepalive\n\n") is None
    assert parse_sse_payload("data: not-json\n\n") is None


@pytest.mark.asyncio
async def test_open_publishes_stream_open_and_sets_mappings():
    fake = FakeRedis()
    stream = RunEventStream(fake, read_block_ms=0)
    await stream.open("sess-1", "abc")
    assert await stream.resolve_active("sess-1") == "abc"
    assert await stream.owner_of("abc") == "sess-1"
    entries = await stream.read("abc", "0", block_ms=0)
    assert entries and entries[0][0] == "1-1"
    assert parse_sse_payload(f"data: {entries[0][1]}")["type"] == STREAM_OPEN_EVENT_TYPE


@pytest.mark.asyncio
async def test_follow_replays_until_terminal_and_clears_active(stream):
    await stream.open("sess-1", "abc")
    await stream.publish("abc", _sse("thought", {"n": 1}))
    await stream.publish("abc", _sse("tool_result", {"n": 2}))
    await stream.publish("abc", _sse("complete", {"answer": "done"}))

    frames = _event_frames([
        frame async for frame in stream.follow("abc", session_id="sess-1")
    ])
    types = [parse_sse_payload(frame)["type"] for frame in frames]
    assert types == [STREAM_OPEN_EVENT_TYPE, "thought", "tool_result", "complete"]
    assert await stream.resolve_active("sess-1") is None
    # 最后带 SSE id 字段，前端可据此断线续传
    assert frames[-1].startswith("id: ")


@pytest.mark.asyncio
async def test_follow_resumes_from_last_id(stream):
    await stream.open("sess-1", "abc")
    await stream.publish("abc", _sse("thought", {"n": 1}))
    first = await stream.read("abc", "0", block_ms=0)
    last_id = first[-1][0]

    await stream.publish("abc", _sse("thought", {"n": 2}))
    await stream.publish("abc", _sse("complete", {}))

    frames = _event_frames([
        frame
        async for frame in stream.follow("abc", session_id="sess-1", last_id=last_id)
    ])
    types = [parse_sse_payload(frame)["type"] for frame in frames]
    assert types == ["thought", "complete"]


@pytest.mark.asyncio
async def test_close_appends_closed_event_and_clears_mappings(stream):
    await stream.open("sess-1", "abc")
    await stream.publish("abc", _sse("thought", {}))
    await stream.close("abc")

    assert await stream.resolve_active("sess-1") is None
    assert await stream.owner_of("abc") is None
    frames = _event_frames([
        frame async for frame in stream.follow("abc", session_id="sess-1")
    ])
    types = [parse_sse_payload(frame)["type"] for frame in frames]
    assert types[-1] == STREAM_CLOSED_EVENT_TYPE


@pytest.mark.asyncio
async def test_follow_yields_stream_lost_when_stream_missing(stream):
    frames = _event_frames([
        frame
        async for frame in stream.follow("ghost", session_id="sess-1", last_id="0")
    ])
    assert len(frames) == 1
    assert parse_sse_payload(frames[0])["type"] == STREAM_LOST_EVENT_TYPE


@pytest.mark.asyncio
async def test_publish_swallows_redis_failures():
    stream = RunEventStream(FakeRedis(fail_xadd=True), read_block_ms=0)
    await stream.open("sess-1", "abc")
    await stream.publish("abc", _sse("complete", {}))


@pytest.mark.asyncio
async def test_owner_mismatch_detectable(stream):
    await stream.open("sess-1", "abc")
    assert await stream.owner_of("abc") == "sess-1"
    assert await stream.is_active("sess-1", "abc")
    assert not await stream.is_active("sess-2", "abc")

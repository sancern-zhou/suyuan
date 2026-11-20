import json
from typing import Any

import pytest

from app.services.chat_completions_adapter import (
    EmptyCompletionError,
    ToolCallArgumentsError,
)
from app.services.chat_completions_collect import (
    aggregate_stream_events,
    collect_chat_completions_stream,
)


def sse(*chunks: dict[str, Any]) -> list[str]:
    lines = ["data: " + json.dumps(c, ensure_ascii=False) for c in chunks]
    lines.append("data: [DONE]")
    return lines


def text_chunks(text: str, usage: dict[str, Any] = None) -> list[str]:
    chunks = [{"choices": [{"index": 0, "delta": {"role": "assistant"}}]}]
    for i in range(0, len(text), 4):
        chunks.append({"choices": [{"index": 0, "delta": {"content": text[i:i + 4]}}]})
    chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    if usage:
        chunks.append({"choices": [], "usage": usage})
    return chunks


class FakeResponse:
    def __init__(self, lines: list[str], status: int = 200):
        self._lines = lines
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP " + str(self.status_code))

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeStream:
    def __init__(self, response: FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc):
        return False


class FakeClient:
    def __init__(self, responses: list[list[dict[str, Any]]]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def stream(self, method, url, headers=None, json=None):
        self.calls.append({"method": method, "url": url, "json": json})
        chunks = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        return FakeStream(FakeResponse(sse(*chunks)))


def text_of(response: dict[str, Any]) -> str:
    return "".join(
        str(block.get("text") or "")
        for block in response["content"]
        if block.get("type") == "text"
    )


@pytest.mark.asyncio
async def test_text_stream_aggregates_into_single_response():
    client = FakeClient([text_chunks("声环境监测说明", usage={"prompt_tokens": 11, "completion_tokens": 7})])

    response = await collect_chat_completions_stream(
        client=client,
        url="http://gateway/v1/chat/completions",
        headers={"Authorization": "Bearer x"},
        payload={"model": "m", "messages": [], "stream": True},
        model="m",
    )

    assert text_of(response) == "声环境监测说明"
    assert response["usage"] == {"input_tokens": 11, "output_tokens": 7}
    assert response["stop_reason"] == "end_turn"
    assert client.calls[0]["json"]["stream"] is True


def tool_chunks(arguments: str, *, finish_reason: str = "tool_calls") -> list[dict[str, Any]]:
    chunks = [{"choices": [{"index": 0, "delta": {"role": "assistant"}}]}]
    chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "id": "call_1", "function": {"name": "get_noise_events", "arguments": ""}}
    ]}}]})
    mid = len(arguments) // 2
    for piece in (arguments[:mid], arguments[mid:]):
        if not piece:
            continue
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": piece}}
        ]}}]})
    chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}]})
    return chunks


@pytest.mark.asyncio
async def test_tool_call_stream_aggregates_arguments():
    client = FakeClient([tool_chunks('{"station": "1733A", "limit": 5}')])

    response = await collect_chat_completions_stream(
        client=client,
        url="http://gateway/v1/chat/completions",
        headers={},
        payload={"model": "m", "messages": [], "stream": True},
        model="m",
    )

    tool_blocks = [b for b in response["content"] if b.get("type") == "tool_use"]
    assert len(tool_blocks) == 1
    assert tool_blocks[0]["name"] == "get_noise_events"
    assert tool_blocks[0]["input"] == {"station": "1733A", "limit": 5}
    assert response["stop_reason"] == "tool_use"


@pytest.mark.asyncio
async def test_truncated_tool_arguments_raise():
    with pytest.raises(ToolCallArgumentsError):
        await collect_chat_completions_stream(
            client=FakeClient([tool_chunks('{"station": "1733', finish_reason=None)]),
            url="http://gateway/v1/chat/completions",
            headers={},
            payload={"model": "m", "messages": [], "stream": True},
            model="m",
        )


@pytest.mark.asyncio
async def test_empty_first_stream_is_retried_once():
    empty = [{"choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": "stop"}]}]
    client = FakeClient([empty, text_chunks("正文")])

    response = await collect_chat_completions_stream(
        client=client,
        url="http://gateway/v1/chat/completions",
        headers={},
        payload={"model": "m", "messages": [], "stream": True},
        model="m",
    )

    assert text_of(response) == "正文"
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_empty_stream_without_retry_raises():
    empty = [{"choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": "stop"}]}]
    with pytest.raises(EmptyCompletionError):
        await collect_chat_completions_stream(
            client=FakeClient([empty]),
            url="http://gateway/v1/chat/completions",
            headers={},
            payload={"model": "m", "messages": [], "stream": True},
            model="m",
            empty_retry=False,
        )


def test_aggregate_stream_events_keeps_thinking_and_text():
    events = [
        {"type": "content_block_start", "data": {"index": 0, "block": {"type": "thinking", "thinking": ""}}},
        {"type": "content_block_delta", "data": {"index": 0, "delta": {"type": "thinking_delta", "thinking": "推理"}}},
        {"type": "content_block_stop", "data": {"index": 0}},
        {"type": "content_block_start", "data": {"index": 1, "block": {"type": "text", "text": ""}}},
        {"type": "content_block_delta", "data": {"index": 1, "delta": {"type": "text_delta", "text": "回答"}}},
        {"type": "content_block_stop", "data": {"index": 1}},
        {"type": "message_delta", "data": {"stop_reason": "end_turn", "usage": {
            "input_tokens": 9, "output_tokens": 3, "cache_read_input_tokens": 4}}},
    ]

    response = aggregate_stream_events(events, model="m")

    assert [b["type"] for b in response["content"]] == ["thinking", "text"]
    assert response["content"][0]["thinking"] == "推理"
    assert response["content"][1]["text"] == "回答"
    assert response["usage"] == {"input_tokens": 9, "output_tokens": 3, "cache_read_input_tokens": 4}


@pytest.mark.asyncio
async def test_empty_delta_heartbeat_trips_first_block_watchdog(monkeypatch):
    from app.services import chat_completions_collect as collect_module

    heartbeat = [
        {"choices": [{"index": 0, "delta": {"role": "assistant"}}]},
        {"choices": [{"index": 0, "delta": {"role": "assistant"}}]},
    ]
    clock = iter([0.0, 0.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0])
    monkeypatch.setattr(collect_module.time, "monotonic", lambda: next(clock, 100.0))

    with pytest.raises(collect_module.FirstBlockTimeoutError):
        await collect_chat_completions_stream(
            client=FakeClient([heartbeat]),
            url="http://gateway/v1/chat/completions",
            headers={},
            payload={"model": "m", "messages": [], "stream": True},
            model="m",
            first_block_timeout=45,
        )


class SlowFakeResponse(FakeResponse):
    def __init__(self, chunks: list[dict[str, Any]], sleep: float = 0.0):
        super().__init__(sse(*chunks))
        self._sleep = sleep

    async def aiter_lines(self):
        import asyncio

        for line in self._lines:
            if self._sleep:
                await asyncio.sleep(self._sleep)
            yield line


@pytest.mark.asyncio
async def test_first_block_watchdog_does_not_trip_on_heartbeat_with_content():
    from app.services import chat_completions_collect as collect_module

    chunks = [
        {"choices": [{"index": 0, "delta": {"role": "assistant"}}]},
        {"choices": [{"index": 0, "delta": {"content": "正"}}]},
        {"choices": [{"index": 0, "delta": {"content": "文"}, "finish_reason": "stop"}]},
    ]

    class Client:
        def stream(self, method, url, headers=None, json=None):
            return FakeStream(SlowFakeResponse(chunks))

    response = await collect_module.collect_chat_completions_stream(
        client=Client(),
        url="http://gateway/v1/chat/completions",
        headers={},
        payload={"model": "m", "messages": [], "stream": True},
        model="m",
        first_block_timeout=0.001,
    )

    assert text_of(response) == "正文"


@pytest.mark.asyncio
async def test_create_dispatches_to_stream_collect_when_enabled(monkeypatch):
    from app.services import llm_service as llm_module

    service = llm_module.LLMService()
    calls = []

    async def stream_collect(**kwargs):
        calls.append(("stream_collect", kwargs["messages"][0]["content"]))
        return {"content": [], "model": "m"}

    monkeypatch.setattr(llm_module.settings, "llm_chat_completions_stream_collect", True)
    monkeypatch.setattr(service, "_chat_completions_stream_collect", stream_collect)

    result = await service._chat_completions_create(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        max_tokens=64,
        temperature=0.3,
        system=None,
    )

    assert result == {"content": [], "model": "m"}
    assert calls == [("stream_collect", "hi")]


@pytest.mark.asyncio
async def test_create_uses_non_streaming_request_when_disabled(monkeypatch):
    from app.services import llm_service as llm_module

    service = llm_module.LLMService()
    captured = {}

    class FakePostResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "model": "m",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ],
            }

    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            captured.update(json)
            return FakePostResponse()

    monkeypatch.setattr(llm_module.settings, "llm_chat_completions_stream_collect", False)
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", FakeHttpClient)

    result = await service._chat_completions_create(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        max_tokens=64,
        temperature=0.3,
        system=None,
    )

    assert captured["stream"] is False
    assert result["content"][0]["text"] == "ok"



"""非流式 chat_completions 的流式替代实现。

网关（nginx/APISIX）对「上游 6s 内没有任何响应字节」直接返回 504。非流式请求
必须等整段生成结束才回首个字节，因此长输出必然超时（2026-11-15 实测：小 prompt
+ max_tokens>=600 即 504；同一 prompt 改流式可正常跑完 23s）。这里用流式请求
上游、在本地聚合为完整响应，对外语义与 chat_completions 非流式一致。
"""
import json
import time
from typing import Any

from app.services.chat_completions_adapter import (
    AttrDict,
    ChatCompletionsStreamAdapter,
    EmptyCompletionError,
)


class FirstBlockTimeoutError(TimeoutError):
    """上游持续推送空 delta（心跳）时，read timeout 永不触发，需墙钟兜底。"""


def aggregate_stream_events(
    events: list[dict[str, Any]],
    *,
    model: str,
) -> dict[str, Any]:
    """把 Anthropic 形状的流事件聚合为一次性响应。

    与 ``convert_chat_response_to_anthropic`` 输出形状保持一致，调用方无需区分
    本次响应是流式聚合还是真正非流式。
    """
    blocks: list[AttrDict] = []
    open_blocks: dict[int, AttrDict] = {}
    usage: dict[str, Any] = {}
    stop_reason: str | None = None

    for event in events:
        event_type = event.get("type")
        data = event.get("data") or {}
        if event_type == "content_block_start":
            index = int(data.get("index", 0))
            open_blocks[index] = AttrDict(dict(data.get("block") or {}))
        elif event_type == "content_block_delta":
            block = open_blocks.get(int(data.get("index", 0)))
            if block is None:
                continue
            delta = data.get("delta")
            if isinstance(delta, dict):
                delta_type = delta.get("type")
                text_piece = delta.get("text")
                thinking_piece = delta.get("thinking")
            else:
                delta_type = getattr(delta, "type", None)
                text_piece = getattr(delta, "text", None)
                thinking_piece = getattr(delta, "thinking", None)
            if delta_type == "text_delta":
                block["text"] = (block.get("text") or "") + str(text_piece or "")
            elif delta_type == "thinking_delta":
                block["thinking"] = (block.get("thinking") or "") + str(thinking_piece or "")
        elif event_type == "content_block_stop":
            block = open_blocks.pop(int(data.get("index", 0)), None)
            if block is not None:
                blocks.append(block)
        elif event_type == "message_delta":
            stop_reason = data.get("stop_reason") or stop_reason
            usage = data.get("usage") or usage

    for index in sorted(open_blocks):
        blocks.append(open_blocks[index])

    if not blocks:
        raise EmptyCompletionError(
            "Chat Completions stream produced no content block after aggregation"
        )

    normalized_usage: dict[str, Any] = {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
    }
    if usage.get("cache_read_input_tokens"):
        normalized_usage["cache_read_input_tokens"] = int(usage["cache_read_input_tokens"])

    return {
        "content": blocks,
        "model": model,
        "usage": normalized_usage,
        "stop_reason": stop_reason,
    }


async def _consume_stream(
    *,
    client: Any,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    model: str,
    first_block_timeout: float | None = None,
) -> list[dict[str, Any]]:
    adapter = ChatCompletionsStreamAdapter(model=model)
    events: list[dict[str, Any]] = []
    deadline = (
        time.monotonic() + first_block_timeout
        if first_block_timeout and first_block_timeout > 0
        else None
    )

    def content_started() -> bool:
        return any(event.get("type") == "content_block_start" for event in events)

    async with client.stream("POST", url, headers=headers, json=payload) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                if deadline is not None and not content_started() and time.monotonic() > deadline:
                    raise FirstBlockTimeoutError(
                        f"first content block timeout after {first_block_timeout}s"
                    )
                continue
            data_str = line[len("data: "):].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            events.extend(adapter.feed_chunk(chunk))
            if deadline is not None and not content_started() and time.monotonic() > deadline:
                raise FirstBlockTimeoutError(
                    f"first content block timeout after {first_block_timeout}s"
                )
    events.extend(adapter.finish())
    return events


async def collect_chat_completions_stream(
    *,
    client: Any,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    model: str,
    empty_retry: bool = True,
    first_block_timeout: float | None = None,
) -> dict[str, Any]:
    """流式请求上游并聚合为完整响应。

    ``empty_retry`` 用于上游只回 role/空 delta 就收流的情况：部分网关在冷启动
    时会先吐一个空帧，重投一次即可拿到正文；仍为空才抛错，交由上层换候选。
    ``first_block_timeout`` 兜住「上游只推空 delta 心跳」——此时 httpx 的 read
    timeout 永远不会触发（实测空转 140s+），必须用墙钟看门狗。
    """
    try:
        events = await _consume_stream(
            client=client,
            url=url,
            headers=headers,
            payload=payload,
            model=model,
            first_block_timeout=first_block_timeout,
        )
        return aggregate_stream_events(events, model=model)
    except EmptyCompletionError:
        if not empty_retry:
            raise
    events = await _consume_stream(
        client=client,
        url=url,
        headers=headers,
        payload=payload,
        model=model,
        first_block_timeout=first_block_timeout,
    )
    return aggregate_stream_events(events, model=model)

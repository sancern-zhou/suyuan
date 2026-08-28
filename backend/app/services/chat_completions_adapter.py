"""Adapters between internal Anthropic blocks and OpenAI Chat Completions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


class AttrDict(dict):
    """Dict-compatible content object with Anthropic SDK-style attributes."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


class ToolCallArgumentsError(ValueError):
    """Raised when Chat Completions returns malformed tool call arguments."""

    def __init__(self, raw: Any, *, tool_name: str = "", tool_call_id: str = "") -> None:
        self.raw = raw
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id
        super().__init__(
            "Invalid tool call arguments JSON"
            f" for tool '{tool_name or 'unknown'}': {raw}"
        )


def _compact_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))


def _block_get(block: Any, key: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _message_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)
    parts: List[str] = []
    for block in content:
        if _block_get(block, "type") == "text":
            parts.append(str(_block_get(block, "text", "")))
    return "\n".join(part for part in parts if part)


def _image_url_block(block: Any) -> Optional[Dict[str, Any]]:
    if _block_get(block, "type") != "image":
        return None
    source = _block_get(block, "source", {}) or {}
    if not isinstance(source, dict):
        return None

    if source.get("type") == "url" and source.get("url"):
        return {
            "type": "image_url",
            "image_url": {"url": str(source["url"])},
        }
    if source.get("type") == "base64" and source.get("data"):
        media_type = str(source.get("media_type") or "image/png")
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{source['data']}",
            },
        }
    return None


def _chat_user_content_from_blocks(content: List[Any]) -> str | List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = []
    for block in content:
        block_type = _block_get(block, "type")
        if block_type == "text":
            text = str(_block_get(block, "text", ""))
            if text:
                parts.append({"type": "text", "text": text})
            continue
        image_url = _image_url_block(block)
        if image_url:
            parts.append(image_url)

    if any(part.get("type") == "image_url" for part in parts):
        return parts
    return "\n".join(
        part["text"]
        for part in parts
        if part.get("type") == "text" and part.get("text")
    )


def _tool_result_content(block: Any) -> str:
    content = _block_get(block, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(_block_get(item, "text", item)) for item in content)
    return json.dumps(content, ensure_ascii=False)


def convert_anthropic_tools_to_chat(
    tools: Optional[List[Dict[str, Any]]],
) -> Optional[List[Dict[str, Any]]]:
    if not tools:
        return None
    converted: List[Dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            converted.append(tool)
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool.get("name", "unknown_tool"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get(
                        "input_schema",
                        {"type": "object", "properties": {}},
                    ),
                },
            }
        )
    return converted


def convert_anthropic_messages_to_chat(
    messages: List[Dict[str, Any]],
    *,
    system: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    converted: List[Dict[str, Any]] = []
    if system:
        converted.append({"role": "system", "content": system})

    for message in messages:
        role = message.get("role")
        content = message.get("content")

        if role == "user" and isinstance(content, list):
            tool_result_blocks = [
                block
                for block in content
                if _block_get(block, "type") == "tool_result"
            ]
            user_content = _chat_user_content_from_blocks(content)
            if user_content:
                converted.append({"role": "user", "content": user_content})
            for block in tool_result_blocks:
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(_block_get(block, "tool_use_id", "")),
                        "content": _tool_result_content(block),
                    }
                )
            if not user_content and not tool_result_blocks:
                converted.append({"role": "user", "content": ""})
            continue

        if role == "assistant" and isinstance(content, list):
            text = _message_text_from_content(content)
            tool_calls = []
            for block in content:
                if _block_get(block, "type") != "tool_use":
                    continue
                tool_calls.append(
                    {
                        "id": str(_block_get(block, "id", "")),
                        "type": "function",
                        "function": {
                            "name": str(_block_get(block, "name", "")),
                            "arguments": _compact_json(_block_get(block, "input", {})),
                        },
                    }
                )
            payload: Dict[str, Any] = {"role": "assistant", "content": text or ""}
            if tool_calls:
                payload["tool_calls"] = tool_calls
            converted.append(payload)
            continue

        if role in {"user", "assistant", "system"}:
            converted.append(
                {"role": role, "content": _message_text_from_content(content)}
            )

    return converted


def map_finish_reason(finish_reason: Optional[str]) -> Optional[str]:
    if finish_reason is None:
        return None
    return {
        "tool_calls": "tool_use",
        "stop": "end_turn",
        "length": "max_tokens",
    }.get(finish_reason, "stop_sequence")


def _parse_arguments(
    raw: Any,
    *,
    tool_name: str = "",
    tool_call_id: str = "",
) -> Dict[str, Any]:
    if raw in (None, ""):
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ToolCallArgumentsError(
            raw,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        ) from exc
    if not isinstance(parsed, dict):
        raise ToolCallArgumentsError(
            raw,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
    return parsed


def convert_chat_response_to_anthropic(response: Dict[str, Any]) -> Dict[str, Any]:
    choices = response.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    content_blocks: List[Dict[str, Any]] = []

    reasoning = message.get("reasoning_content")
    if reasoning:
        content_blocks.append(AttrDict({"type": "thinking", "thinking": reasoning}))

    text = message.get("content")
    if text:
        content_blocks.append(AttrDict({"type": "text", "text": text}))

    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        tool_name = str(function.get("name") or "")
        tool_call_id = str(tool_call.get("id") or "")
        content_blocks.append(
            AttrDict({
                "type": "tool_use",
                "id": tool_call_id,
                "name": tool_name,
                "input": _parse_arguments(
                    function.get("arguments"),
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                ),
            })
        )

    usage = response.get("usage") or {}
    return {
        "content": content_blocks,
        "model": response.get("model", ""),
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
        "stop_reason": map_finish_reason(choice.get("finish_reason")),
    }


@dataclass
class _ToolCallAccumulator:
    id: str = ""
    name: str = ""
    arguments: str = ""
    emitted: bool = False


@dataclass
class ChatCompletionsStreamAdapter:
    model: str
    message_started: bool = False
    next_index: int = 0
    open_block_index: Optional[int] = None
    open_block_type: Optional[str] = None
    finish_reason: Optional[str] = None
    usage: Dict[str, Any] = field(default_factory=dict)
    tool_calls: Dict[int, _ToolCallAccumulator] = field(default_factory=dict)

    def _ensure_message_started(self) -> List[Dict[str, Any]]:
        if self.message_started:
            return []
        self.message_started = True
        return [
            {
                "type": "message_start",
                "data": {"usage": {"input_tokens": 0, "output_tokens": 0}},
            }
        ]

    def _open_block(
        self,
        block_type: str,
        block: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        events = self._ensure_message_started()
        if self.open_block_index is not None and self.open_block_type != block_type:
            events.append(
                {"type": "content_block_stop", "data": {"index": self.open_block_index}}
            )
            self.open_block_index = None
            self.open_block_type = None
        if self.open_block_index is None:
            index = self.next_index
            self.next_index += 1
            self.open_block_index = index
            self.open_block_type = block_type
            events.append(
                {
                    "type": "content_block_start",
                    "data": {"index": index, "block": AttrDict(block)},
                }
            )
        return events

    def _emit_text_delta(self, text: str) -> List[Dict[str, Any]]:
        events = self._open_block("text", {"type": "text", "text": ""})
        events.append(
            {
                "type": "content_block_delta",
                "data": {
                    "index": self.open_block_index,
                    "delta": AttrDict({"type": "text_delta", "text": text}),
                },
            }
        )
        return events

    def _emit_thinking_delta(self, text: str) -> List[Dict[str, Any]]:
        events = self._open_block("thinking", {"type": "thinking", "thinking": ""})
        events.append(
            {
                "type": "content_block_delta",
                "data": {
                    "index": self.open_block_index,
                    "delta": AttrDict({"type": "thinking_delta", "thinking": text}),
                },
            }
        )
        return events

    def _accumulate_tool_calls(self, deltas: Iterable[Dict[str, Any]]) -> None:
        for delta in deltas:
            index = int(delta.get("index", 0))
            accumulator = self.tool_calls.setdefault(index, _ToolCallAccumulator())
            if delta.get("id"):
                accumulator.id = str(delta["id"])
            function = delta.get("function") or {}
            if function.get("name"):
                accumulator.name = str(function["name"])
            if function.get("arguments"):
                accumulator.arguments += str(function["arguments"])

    def _emit_completed_tool_calls(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for index in sorted(self.tool_calls):
            accumulator = self.tool_calls[index]
            if accumulator.emitted:
                continue
            try:
                parsed = _parse_arguments(
                    accumulator.arguments,
                    tool_name=accumulator.name,
                    tool_call_id=accumulator.id,
                )
            except ToolCallArgumentsError:
                continue
            events.extend(
                self._open_block(
                    "tool_use",
                    {
                        "type": "tool_use",
                        "id": accumulator.id,
                        "name": accumulator.name,
                        "input": parsed,
                    },
                )
            )
            events.append(
                {"type": "content_block_stop", "data": {"index": self.open_block_index}}
            )
            self.open_block_index = None
            self.open_block_type = None
            accumulator.emitted = True
        return events

    def feed_chunk(self, chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = self._ensure_message_started()
        choices = chunk.get("choices") or []
        if not choices:
            if chunk.get("usage"):
                self.usage = chunk["usage"]
            return events

        choice = choices[0]
        delta = choice.get("delta") or {}
        if chunk.get("usage"):
            self.usage = chunk["usage"]
        if choice.get("finish_reason") is not None:
            self.finish_reason = choice.get("finish_reason")

        if delta.get("reasoning_content"):
            events.extend(self._emit_thinking_delta(str(delta["reasoning_content"])))
        if delta.get("content"):
            events.extend(self._emit_text_delta(str(delta["content"])))
        if delta.get("tool_calls"):
            self._accumulate_tool_calls(delta["tool_calls"])

        return events

    def finish(self) -> List[Dict[str, Any]]:
        events = self._ensure_message_started()
        events.extend(self._emit_completed_tool_calls())
        if self.finish_reason == "tool_calls":
            for accumulator in self.tool_calls.values():
                if not accumulator.emitted:
                    _parse_arguments(
                        accumulator.arguments,
                        tool_name=accumulator.name,
                        tool_call_id=accumulator.id,
                    )
        if self.open_block_index is not None:
            events.append(
                {"type": "content_block_stop", "data": {"index": self.open_block_index}}
            )
            self.open_block_index = None
            self.open_block_type = None
        events.append(
            {
                "type": "message_delta",
                "data": {
                    "stop_reason": map_finish_reason(self.finish_reason),
                    "usage": {"output_tokens": self.usage.get("completion_tokens", 0)},
                },
            }
        )
        events.append({"type": "message_stop", "data": {}})
        return events

"""上下文占用快照：planner 事件产出、元数据持久化与合并保护。"""

from types import SimpleNamespace

import pytest

from app.agent.core.planner import ReActPlanner
from app.agent.runtime.types import RunState
from app.agent.session import session_resolver
from app.agent.session.session_manager_db import SessionManagerDB
from config.settings import settings


class StreamingLLMWithUsage:
    """模拟 llm_service 流式输出：message_start 携带 usage。"""

    def __init__(self, usage, model="test-model"):
        self.usage = usage
        self.model = model

    async def chat_anthropic_streaming(self, **kwargs):
        yield {
            "type": "message_start",
            "data": {"model": self.model, "usage": self.usage},
        }
        yield {
            "type": "content_block_start",
            "data": {"index": 0, "block": SimpleNamespace(type="text")},
        }
        yield {
            "type": "content_block_delta",
            "data": {
                "index": 0,
                "delta": SimpleNamespace(type="text_delta", text="结论"),
            },
        }
        yield {"type": "content_block_stop", "data": {"index": 0}}
        yield {"type": "message_stop", "data": {}}


class StreamingLLMCompatEndFrame:
    """模拟 OpenAI 兼容适配器：message_start 占位 0，真实 usage 在结束帧 message_delta。"""

    def __init__(self, usage, model="compat-model"):
        self.usage = usage
        self.model = model

    async def chat_anthropic_streaming(self, **kwargs):
        yield {
            "type": "message_start",
            "data": {"model": self.model, "usage": {"input_tokens": 0, "output_tokens": 0}},
        }
        yield {
            "type": "content_block_start",
            "data": {"index": 0, "block": SimpleNamespace(type="text")},
        }
        yield {
            "type": "content_block_delta",
            "data": {
                "index": 0,
                "delta": SimpleNamespace(type="text_delta", text="结论"),
            },
        }
        yield {"type": "content_block_stop", "data": {"index": 0}}
        yield {
            "type": "message_delta",
            "data": {"stop_reason": "end_turn", "usage": self.usage},
        }
        yield {"type": "message_stop", "data": {}}


async def collect_context_usage(usage, llm_cls=StreamingLLMWithUsage):
    planner = ReActPlanner(llm_client=llm_cls(usage))
    events = [
        event
        async for event in planner.think_and_action_streaming(
            query="测试",
            system_prompt="system",
            user_conversation="测试",
            tools=[],
        )
    ]
    return [event for event in events if event["type"] == "context_usage"]


@pytest.mark.asyncio
async def test_context_usage_event_merges_cache_tokens(monkeypatch):
    monkeypatch.setattr(settings, "llm_context_window_tokens", 123456)
    events = await collect_context_usage({
        "input_tokens": 1000,
        "cache_read_input_tokens": 2500,
        "cache_creation_input_tokens": 400,
        "output_tokens": 8,
    })

    assert len(events) == 1
    data = events[0]["data"]
    assert data["input_tokens"] == 1000
    assert data["cache_read_input_tokens"] == 2500
    assert data["cache_creation_input_tokens"] == 400
    # Anthropic 语义：真实 prompt 占用 = input + cache_read + cache_creation
    assert data["context_tokens"] == 3900
    assert data["context_window"] == 123456
    assert data["model"] == "test-model"
    assert data["timestamp"]


@pytest.mark.asyncio
async def test_context_usage_event_without_cache_fields():
    events = await collect_context_usage({"input_tokens": 900, "output_tokens": 5})

    assert len(events) == 1
    assert events[0]["data"]["context_tokens"] == 900


@pytest.mark.asyncio
async def test_context_usage_event_absent_without_usage():
    assert await collect_context_usage({}) == []


@pytest.mark.asyncio
async def test_context_usage_from_compat_end_frame_skips_placeholder_start():
    """OpenAI 兼容协议：占位 message_start 不产出事件，结束帧 message_delta 产出真实快照。"""
    events = await collect_context_usage(
        {"input_tokens": 7800, "output_tokens": 120},
        llm_cls=StreamingLLMCompatEndFrame,
    )

    assert len(events) == 1
    data = events[0]["data"]
    assert data["input_tokens"] == 7800
    assert data["context_tokens"] == 7800
    # 适配器结束帧 message_delta 不携带 model 字段
    assert data["model"] is None


@pytest.mark.asyncio
async def test_context_usage_absent_when_compat_end_frame_has_zero_usage():
    events = await collect_context_usage(
        {"input_tokens": 0, "output_tokens": 0},
        llm_cls=StreamingLLMCompatEndFrame,
    )
    assert events == []


def test_merge_preserved_metadata_keeps_context_usage():
    existing = {
        "llm_compact_state": {"active": True},
        "context_usage": {"context_tokens": 3900, "context_window": 200000},
    }
    merged = SessionManagerDB._merge_preserved_metadata(existing, {"mode": "expert"})

    assert merged["context_usage"] == existing["context_usage"]
    assert merged["llm_compact_state"] == existing["llm_compact_state"]


@pytest.mark.asyncio
async def test_save_context_usage_for_mode_uses_manager(monkeypatch):
    saved = {}

    class FakeManager:
        async def save_context_usage(self, session_id, context_usage):
            saved["session_id"] = session_id
            saved["context_usage"] = context_usage
            return True

    monkeypatch.setattr(
        session_resolver,
        "get_session_manager_for_mode",
        lambda mode=None: FakeManager(),
    )

    ok = await session_resolver.save_context_usage_for_mode(
        "session-1",
        {"context_tokens": 3900, "context_window": 200000},
        mode="expert",
    )

    assert ok is True
    assert saved["session_id"] == "session-1"
    assert saved["context_usage"]["context_tokens"] == 3900


@pytest.mark.asyncio
async def test_save_context_usage_for_mode_skips_unsupported_manager(monkeypatch):
    monkeypatch.setattr(
        session_resolver,
        "get_session_manager_for_mode",
        lambda mode=None: object(),
    )

    ok = await session_resolver.save_context_usage_for_mode(
        "session-1",
        {"context_tokens": 1},
    )

    assert ok is False


@pytest.mark.asyncio
async def test_runtime_persists_context_usage(monkeypatch):
    from app.agent.runtime.agent_runtime import AgentRuntime

    persisted = {}

    async def fake_save(session_id, context_usage, *, mode=None):
        persisted["session_id"] = session_id
        persisted["context_usage"] = context_usage
        persisted["mode"] = mode
        return True

    monkeypatch.setattr(session_resolver, "save_context_usage_for_mode", fake_save)

    state = RunState(session_id="session-1", user_query="q", mode="expert")
    usage = {"context_tokens": 3900, "context_window": 200000}
    await AgentRuntime._persist_context_usage(SimpleNamespace(), state, usage)

    assert persisted["session_id"] == "session-1"
    assert persisted["context_usage"] == usage
    assert persisted["mode"] == "expert"

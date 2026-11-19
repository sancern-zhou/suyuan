"""流式规划器失败后的重试策略。

背景：2026-11-14 江西噪声会话中 execute_echarts_python 的长参数被上游截断，
planner 回退非流式后一次性提交完整长 JSON 载荷，被网关在约 6s 判 504；
单候选配置下 cooldown 反复叠加，形成 12:10-12:14 的 504 风暴。

锁定行为：
- 任意流式失败且尚未下发可见内容时，保持同协议流式重试一次，不回退非流式；
- 已下发用户可见内容（文本/tool_use）后不再重放，避免重复输出；
- 重试次数上限为一次，第二轮失败直接上抛。
"""

import pytest

from app.agent.core.planner import ReActPlanner
from app.services.chat_completions_adapter import ToolCallArgumentsError


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def text_stream(text):
    return [
        {"type": "content_block_start", "data": {"index": 0, "block": _Block(type="text")}},
        {
            "type": "content_block_delta",
            "data": {"index": 0, "delta": _Block(type="text_delta", text=text)},
        },
        {"type": "content_block_stop", "data": {"index": 0}},
        {"type": "message_stop", "data": {}},
    ]


class ScriptedLLM:
    def __init__(self, script):
        self.provider = "openai"
        self.model = "fake-model"
        self.script = list(script)
        self.calls = 0
        self.non_stream_calls = 0

    async def chat_anthropic_streaming(self, **kwargs):
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        for event in step:
            yield event

    async def chat_anthropic(self, **kwargs):
        # 非流式回退在本场景下必须彻底绝迹：它要求一次性生成完整长 JSON 载荷。
        self.non_stream_calls += 1
        raise AssertionError("planner must not fall back to non-streaming")


async def collect(planner, **kwargs):
    events = []
    async for event in planner.think_and_action_streaming(
        query="q",
        system_prompt="s",
        user_conversation="u",
        tools=[],
        iteration=1,
        **kwargs,
    ):
        events.append(event)
    return events


def make_planner(llm):
    planner = ReActPlanner(llm_client=llm)
    planner._tool_registry = {}
    return planner


@pytest.mark.asyncio
async def test_truncated_stream_retries_streaming_not_non_streaming():
    truncation = ToolCallArgumentsError(
        '{"code": "import matplotlib',
        tool_name="execute_echarts_python",
        tool_call_id="call_1",
    )
    llm = ScriptedLLM([truncation, text_stream("retried")])
    events = await collect(make_planner(llm))

    assert llm.calls == 2
    assert llm.non_stream_calls == 0
    assert any(e["type"] == "action" for e in events)
    assert any(
        e["type"] == "streaming_text" and e["data"].get("chunk") == "retried"
        for e in events
    )


@pytest.mark.asyncio
async def test_streaming_failure_after_visible_text_does_not_replay():
    class PartialLLM(ScriptedLLM):
        async def chat_anthropic_streaming(self, **kwargs):
            self.calls += 1
            for event in text_stream("partial")[:2]:
                yield event
            raise RuntimeError("interrupted after visible text")

    llm = PartialLLM([])
    with pytest.raises(RuntimeError):
        await collect(make_planner(llm))
    assert llm.calls == 1
    assert llm.non_stream_calls == 0


@pytest.mark.asyncio
async def test_streaming_retry_is_bounded_to_one_extra_attempt():
    llm = ScriptedLLM([
        ToolCallArgumentsError("{", tool_name="execute_python"),
        ToolCallArgumentsError("{", tool_name="execute_python"),
    ])
    with pytest.raises(ToolCallArgumentsError):
        await collect(make_planner(llm))
    assert llm.calls == 2
    assert llm.non_stream_calls == 0


@pytest.mark.asyncio
async def test_thinking_only_output_still_allows_streaming_retry():
    class ThinkingThenFailLLM(ScriptedLLM):
        async def chat_anthropic_streaming(self, **kwargs):
            self.calls += 1
            if self.calls > 1:
                for event in text_stream("ok"):
                    yield event
                return
            yield {
                "type": "content_block_start",
                "data": {"index": 0, "block": _Block(type="thinking")},
            }
            yield {
                "type": "content_block_delta",
                "data": {
                    "index": 0,
                    "delta": _Block(type="thinking_delta", thinking="plan"),
                },
            }
            raise ToolCallArgumentsError("{", tool_name="execute_python")

    llm = ThinkingThenFailLLM([])
    events = await collect(make_planner(llm))

    # thinking_delta 不进用户可见流，重放安全，因此不受 emitted_visible 拦截。
    assert llm.calls == 2
    assert llm.non_stream_calls == 0
    assert any(e["type"] == "action" for e in events)


@pytest.mark.asyncio
async def test_capacity_failure_still_retries_streaming_once():
    llm = ScriptedLLM([RuntimeError("http 504 gateway timeout"), text_stream("ok")])
    events = await collect(make_planner(llm))

    assert llm.calls == 2
    assert llm.non_stream_calls == 0
    assert any(e["type"] == "action" for e in events)


@pytest.mark.asyncio
async def test_upstream_truncation_is_not_replayed_in_planner():
    """无 finish_reason 的上游截断是确定性失败，重投同一负载只会再被截断。"""
    llm = ScriptedLLM([
        ToolCallArgumentsError(
            '{"code": "import', tool_name="execute_echarts_python", truncated=True,
        ),
    ])
    with pytest.raises(ToolCallArgumentsError) as exc_info:
        await collect(make_planner(llm))

    assert exc_info.value.truncated is True
    assert llm.calls == 1
    assert llm.non_stream_calls == 0


@pytest.mark.asyncio
async def test_every_failure_path_avoids_non_streaming():
    llm = ScriptedLLM([RuntimeError("http 401 unauthorized"), text_stream("ok")])
    events = await collect(make_planner(llm))

    assert llm.calls == 2
    assert llm.non_stream_calls == 0
    assert any(e["type"] == "action" for e in events)

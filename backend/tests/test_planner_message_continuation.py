"""Check the messages sent to the model after a successful tool call."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.agent.context.context_builder import SimplifiedContextBuilder
from app.agent.core.planner import ReActPlanner
from app.services.llm_service import LLMService


class RecordingLLM:
    def __init__(self):
        self.requests = []

    async def chat_anthropic(self, **kwargs):
        self.requests.append(kwargs)
        return {
            "content": [SimpleNamespace(type="text", text="图片已注册")],
            "stop_reason": "end_turn",
        }

    async def chat_anthropic_streaming(self, **kwargs):
        self.requests.append(kwargs)
        yield {
            "type": "content_block_start",
            "data": {"index": 0, "block": SimpleNamespace(type="text")},
        }
        yield {
            "type": "content_block_delta",
            "data": {
                "index": 0,
                "delta": SimpleNamespace(type="text_delta", text="图片已注册"),
            },
        }
        yield {"type": "content_block_stop", "data": {"index": 0}}
        yield {"type": "message_stop", "data": {}}


@pytest.fixture
def tool_history():
    return [
        {"role": "user", "content": "把图片注册为资源"},
        {
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": "call_publish",
                "name": "publish_session_file",
                "input": {"file_path": "/tmp/chart.png"},
            }],
        },
        {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": "call_publish",
                "content": '{"success": true, "resource_id": "chart"}',
            }],
        },
    ]


async def request_messages(streaming, history, user_conversation, user_content=None):
    llm = RecordingLLM()
    planner = ReActPlanner(llm_client=llm)
    kwargs = {
        "query": "把图片注册为资源",
        "system_prompt": "system",
        "user_conversation": user_conversation,
        "user_content": user_content,
        "conversation_history": history,
        "tools": [],
        "iteration": 2 if history else 1,
    }
    if streaming:
        events = [event async for event in planner.think_and_action_streaming(**kwargs)]
        assert any(event["type"] == "action" for event in events)
    else:
        await planner.think_and_action(**kwargs)
    assert len(llm.requests) == 1
    return llm.requests[0]["messages"]


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("empty_content", [None, "", " \n", [], [{"type": "text", "text": " "}]])
async def test_tool_continuation_has_no_extra_user_message(streaming, empty_content, tool_history):
    original = deepcopy(tool_history)
    builder = SimplifiedContextBuilder(llm_client=None, memory_manager=None)
    user_conversation = builder._build_user_conversation(
        query="把图片注册为资源",
        iteration=2,
        latest_observation="注册成功",
        conversation_history=tool_history,
    )
    messages = await request_messages(streaming, tool_history, user_conversation, empty_content)

    assert messages == original
    assert tool_history == original
    assert LLMService._is_tool_continuation(messages)


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("new_content", [
    "另外注册第二张图片",
    [{"type": "image", "source": {"type": "url", "url": "https://example.com/image.png"}}],
    [{"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": "资料"}}],
])
async def test_new_input_is_preserved_after_tool_result(streaming, new_content, tool_history):
    original = deepcopy(tool_history)
    messages = await request_messages(streaming, tool_history, "", new_content)

    assert messages[:-1] == original
    assert messages[-1] == {"role": "user", "content": new_content}
    assert tool_history == original
    assert not LLMService._is_tool_continuation(messages)


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_first_user_query_is_preserved(streaming):
    messages = await request_messages(streaming, [], "把图片注册为资源")
    assert messages == [{"role": "user", "content": "把图片注册为资源"}]

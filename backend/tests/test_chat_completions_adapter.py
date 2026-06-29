import pytest

from app.services.chat_completions_adapter import (
    ChatCompletionsStreamAdapter,
    convert_anthropic_messages_to_chat,
    convert_anthropic_tools_to_chat,
    convert_chat_response_to_anthropic,
    map_finish_reason,
)


def test_convert_anthropic_tools_to_chat_tools():
    tools = [
        {
            "name": "query_weather",
            "description": "Query weather data",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ]

    assert convert_anthropic_tools_to_chat(tools) == [
        {
            "type": "function",
            "function": {
                "name": "query_weather",
                "description": "Query weather data",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]


def test_convert_anthropic_messages_to_chat_messages_with_tool_chain():
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "查广州天气"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "Need weather lookup"},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "query_weather",
                    "input": {"city": "广州"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "晴，28度",
                }
            ],
        },
    ]

    converted = convert_anthropic_messages_to_chat(messages, system="你是助手")

    assert converted == [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "查广州天气"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "toolu_1",
                    "type": "function",
                    "function": {
                        "name": "query_weather",
                        "arguments": '{"city":"广州"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "toolu_1", "content": "晴，28度"},
    ]


def test_convert_chat_response_to_anthropic_content_blocks():
    response = {
        "model": "DeepSeek-V4-Flash",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "reasoning_content": "Need data",
                    "content": "我来查询。",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "query_weather",
                                "arguments": '{"city":"广州"}',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8},
    }

    result = convert_chat_response_to_anthropic(response)

    assert result == {
        "content": [
            {"type": "thinking", "thinking": "Need data"},
            {"type": "text", "text": "我来查询。"},
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "query_weather",
                "input": {"city": "广州"},
            },
        ],
        "model": "DeepSeek-V4-Flash",
        "usage": {"input_tokens": 12, "output_tokens": 8},
        "stop_reason": "tool_use",
    }


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [
        ("tool_calls", "tool_use"),
        ("stop", "end_turn"),
        ("length", "max_tokens"),
        ("content_filter", "stop_sequence"),
        (None, None),
    ],
)
def test_map_finish_reason(finish_reason, expected):
    assert map_finish_reason(finish_reason) == expected


def test_stream_adapter_converts_reasoning_text_and_tool_call_events():
    adapter = ChatCompletionsStreamAdapter(model="DeepSeek-V4-Flash")
    chunks = [
        {"choices": [{"delta": {"reasoning_content": "Need"}}]},
        {"choices": [{"delta": {"reasoning_content": " data"}}]},
        {"choices": [{"delta": {"content": "查询中"}}]},
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "query_weather",
                                    "arguments": '{"city"',
                                },
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {
                                    "arguments": ':"广州"}',
                                },
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        },
    ]

    events = []
    for chunk in chunks:
        events.extend(adapter.feed_chunk(chunk))
    events.extend(adapter.finish())

    assert events[0]["type"] == "message_start"
    assert events[1] == {
        "type": "content_block_start",
        "data": {"index": 0, "block": {"type": "thinking", "thinking": ""}},
    }
    assert events[2] == {
        "type": "content_block_delta",
        "data": {"index": 0, "delta": {"type": "thinking_delta", "thinking": "Need"}},
    }
    assert any(
        event == {
            "type": "content_block_start",
            "data": {
                "index": 2,
                "block": {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "query_weather",
                    "input": {"city": "广州"},
                },
            },
        }
        for event in events
    )
    assert events[-2] == {
        "type": "message_delta",
        "data": {
            "stop_reason": "tool_use",
            "usage": {"output_tokens": 10},
        },
    }
    assert events[-1] == {"type": "message_stop", "data": {}}

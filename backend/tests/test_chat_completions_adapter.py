import pytest

from app.services.chat_completions_adapter import (
    ChatCompletionsStreamAdapter,
    ToolCallArgumentsError,
    convert_anthropic_messages_to_chat,
    convert_anthropic_tools_to_chat,
    convert_chat_response_to_anthropic,
    map_finish_reason,
)
from app.services.llm_service import LLMService


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
            "content": "",
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


def test_convert_anthropic_messages_to_chat_preserves_image_url_blocks():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "描述这张图片"},
                {
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": "https://example.com/image.jpg",
                    },
                },
            ],
        }
    ]

    converted = convert_anthropic_messages_to_chat(messages)

    assert converted == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "描述这张图片"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/image.jpg"},
                },
            ],
        }
    ]


def test_chat_completions_payload_includes_explicit_false_stream():
    service = object.__new__(LLMService)
    service.provider = "openai"
    service.model = "gpt-4.1-mini"

    payload = service._build_chat_completions_payload(
        messages=[{"role": "user", "content": "你好"}],
        tools=None,
        max_tokens=None,
        temperature=0.3,
        system=None,
        stream=False,
    )

    assert payload["stream"] is False
    assert "enable_thinking" not in payload


def test_get_request_config_normalizes_trailing_slash_base_url():
    service = object.__new__(LLMService)
    service.provider = "agnes"
    service.model = "agnes-2.0-flash"
    service.base_url = "https://example.test/v1/"
    service.api_key = "test-key"

    url, headers = service._get_request_config()

    assert url == "https://example.test/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"


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
    assert result["content"][0].type == "thinking"
    assert result["content"][0].thinking == "Need data"
    assert result["content"][2].type == "tool_use"
    assert result["content"][2].input == {"city": "广州"}


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
    assert events[1]["data"]["block"].type == "thinking"
    assert events[2] == {
        "type": "content_block_delta",
        "data": {"index": 0, "delta": {"type": "thinking_delta", "thinking": "Need"}},
    }
    assert events[2]["data"]["delta"].type == "thinking_delta"
    assert events[2]["data"]["delta"].thinking == "Need"
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


def test_stream_adapter_waits_for_tool_call_finish_before_emitting_tool_use():
    adapter = ChatCompletionsStreamAdapter(model="agnes-2.0-flash")

    first_events = adapter.feed_chunk(
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
                                    "name": "read_file",
                                    "arguments": '{"path"',
                                },
                            }
                        ]
                    }
                }
            ]
        }
    )

    assert all(event["type"] != "content_block_start" for event in first_events)

    adapter.feed_chunk(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {
                                    "arguments": ':"backend/AGENTS.md"}',
                                },
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )

    events = adapter.finish()

    assert any(
        event == {
            "type": "content_block_start",
            "data": {
                "index": 0,
                "block": {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "read_file",
                    "input": {"path": "backend/AGENTS.md"},
                },
            },
        }
        for event in events
    )


def test_stream_adapter_does_not_treat_pseudo_tool_markup_as_tool_call():
    adapter = ChatCompletionsStreamAdapter(model="glm-4.7")

    events = []
    events.extend(
        adapter.feed_chunk(
            {
                "choices": [
                    {
                        "delta": {
                            "reasoning_content": (
                                "create_report_chart</arg_value>"
                                "<arg_key>chart_type</arg_key>"
                            )
                        },
                    }
                ]
            }
        )
    )
    events.extend(
        adapter.feed_chunk(
            {
                "choices": [
                    {
                        "delta": {"content": "<tool_call>{bad}</tool_call>"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            }
        )
    )
    events.extend(adapter.finish())

    block_starts = [
        event["data"]["block"].type
        for event in events
        if event["type"] == "content_block_start"
    ]
    assert block_starts == ["thinking", "text"]
    assert all(block_type != "tool_use" for block_type in block_starts)
    assert events[-2]["data"]["stop_reason"] == "end_turn"


def test_stream_adapter_raises_when_tool_call_arguments_remain_malformed_at_finish():
    adapter = ChatCompletionsStreamAdapter(model="glm-4.7")

    adapter.feed_chunk(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_bad",
                                "type": "function",
                                "function": {
                                    "name": "create_report_chart",
                                    "arguments": "{",
                                },
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )

    with pytest.raises(ToolCallArgumentsError) as exc_info:
        adapter.finish()

    assert exc_info.value.tool_name == "create_report_chart"
    assert exc_info.value.tool_call_id == "call_bad"

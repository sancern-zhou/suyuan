import json
from pathlib import Path

import httpx
import pytest

from app.services.llm_service import LLMService
from config.settings import settings


def test_deepseek_api_mode_setting_exists():
    assert settings.deepseek_api_mode in {"anthropic_messages", "chat_completions"}


def test_llm_service_loads_deepseek_api_mode(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_mode", "chat_completions")
    monkeypatch.setattr(
        settings,
        "deepseek_base_url",
        "http://ds.local.ai:30080/compatible-mode/v1",
    )
    monkeypatch.setattr(settings, "deepseek_api_key", "api-key")
    monkeypatch.setattr(settings, "deepseek_model", "DeepSeek-V4-Flash")

    service = LLMService()

    assert service.provider == "deepseek"
    assert service.api_mode == "chat_completions"
    assert service.anthropic_client is None
    assert service.base_url == "http://ds.local.ai:30080/compatible-mode/v1"


@pytest.mark.asyncio
async def test_chat_anthropic_uses_chat_completions_when_api_mode_enabled(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_mode", "chat_completions")
    monkeypatch.setattr(
        settings,
        "deepseek_base_url",
        "http://ds.local.ai:30080/compatible-mode/v1",
    )
    monkeypatch.setattr(settings, "deepseek_api_key", "api-key")
    monkeypatch.setattr(settings, "deepseek_model", "DeepSeek-V4-Flash")

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "model": "DeepSeek-V4-Flash",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "reasoning_content": "fast reasoning",
                            "content": "你好",
                        },
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)

    service = LLMService()
    result = await service.chat_anthropic(
        messages=[{"role": "user", "content": "你好"}],
        tools=None,
        temperature=0.2,
        system="你是助手",
    )

    assert captured["url"] == (
        "http://ds.local.ai:30080/compatible-mode/v1/chat/completions"
    )
    assert captured["authorization"] == "Bearer api-key"
    assert captured["json"]["model"] == "DeepSeek-V4-Flash"
    assert captured["json"]["messages"][0] == {"role": "system", "content": "你是助手"}
    assert captured["json"]["stream"] is False
    assert result["content"] == [
        {"type": "thinking", "thinking": "fast reasoning"},
        {"type": "text", "text": "你好"},
    ]
    assert result["stop_reason"] == "end_turn"


@pytest.mark.asyncio
async def test_chat_anthropic_streaming_uses_chat_completions_events(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_mode", "chat_completions")
    monkeypatch.setattr(
        settings,
        "deepseek_base_url",
        "http://ds.local.ai:30080/compatible-mode/v1",
    )
    monkeypatch.setattr(settings, "deepseek_api_key", "api-key")
    monkeypatch.setattr(settings, "deepseek_model", "DeepSeek-V4-Flash")

    captured = {}
    stream_body = (
        'data: {"choices":[{"delta":{"reasoning_content":"Need"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"你好"},"finish_reason":"stop"}],'
        '"usage":{"prompt_tokens":3,"completion_tokens":4}}\n\n'
        "data: [DONE]\n\n"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, content=stream_body.encode("utf-8"))

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)

    service = LLMService()
    events = [
        event
        async for event in service.chat_anthropic_streaming(
            messages=[{"role": "user", "content": "你好"}],
            tools=None,
            temperature=0.2,
            system="你是助手",
        )
    ]

    assert captured["url"] == (
        "http://ds.local.ai:30080/compatible-mode/v1/chat/completions"
    )
    assert captured["json"]["stream"] is True
    assert captured["json"]["stream_options"] == {"include_usage": True}
    assert events[0]["type"] == "message_start"
    assert any(event["type"] == "content_block_delta" for event in events)
    assert events[-2] == {
        "type": "message_delta",
        "data": {"stop_reason": "end_turn", "usage": {"output_tokens": 4}},
    }
    assert events[-1] == {"type": "message_stop", "data": {}}


def test_env_example_documents_deepseek_v4_chat_completions():
    env_example = Path("backend/.env.example").read_text(encoding="utf-8")

    assert "DEEPSEEK_API_MODE=chat_completions" in env_example
    assert "DEEPSEEK_BASE_URL=http://ds.local.ai:30080/compatible-mode/v1" in env_example
    assert "DEEPSEEK_MODEL=DeepSeek-V4-Flash" in env_example
    assert "MDDEEPSEEK25FF2F3E5E17" in env_example


def test_chat_completions_payload_uses_tool_choice_without_prompt_guardrails(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "glm")
    monkeypatch.setattr(settings, "glm_api_mode", "chat_completions")
    monkeypatch.setattr(settings, "glm_api_key", "api-key")
    monkeypatch.setattr(settings, "glm_model", "glm-4.7")

    service = LLMService()
    payload = service._build_chat_completions_payload(
        messages=[{"role": "user", "content": "生成图表"}],
        tools=[
            {
                "name": "create_report_chart",
                "description": "Create a chart",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "data": {"type": "object"},
                    },
                    "required": ["title", "data"],
                },
            }
        ],
        max_tokens=1024,
        temperature=0.2,
        system="你是助手",
        stream=True,
    )

    assert payload["tool_choice"] == "auto"
    assert payload["tools"][0]["function"]["name"] == "create_report_chart"
    assert payload["messages"][0] == {"role": "system", "content": "你是助手"}


@pytest.mark.asyncio
async def test_chat_completions_retries_malformed_tool_arguments_with_named_tool_choice(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "glm")
    monkeypatch.setattr(settings, "glm_api_mode", "chat_completions")
    monkeypatch.setattr(settings, "glm_base_url", "https://open.bigmodel.cn/api/coding/paas/v4")
    monkeypatch.setattr(settings, "glm_api_key", "api-key")
    monkeypatch.setattr(settings, "glm_model", "glm-4.7")

    captured_payloads = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        captured_payloads.append(payload)
        if len(captured_payloads) == 1:
            return httpx.Response(
                200,
                json={
                    "model": "glm-4.7",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "tool_calls": [
                                    {
                                        "id": "call_bad",
                                        "type": "function",
                                        "function": {
                                            "name": "create_report_chart",
                                            "arguments": "{",
                                        },
                                    }
                                ]
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                },
            )
        return httpx.Response(
            200,
            json={
                "model": "glm-4.7",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_ok",
                                    "type": "function",
                                    "function": {
                                        "name": "create_report_chart",
                                        "arguments": '{"title":"AQI","data":{}}',
                                    },
                                }
                            ]
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 6},
            },
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)

    service = LLMService()
    result = await service.chat_anthropic(
        messages=[{"role": "user", "content": "生成图表"}],
        tools=[
            {
                "name": "create_report_chart",
                "description": "Create a chart",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "data": {"type": "object"},
                    },
                    "required": ["title", "data"],
                },
            }
        ],
        temperature=0.2,
        system="你是助手",
    )

    assert len(captured_payloads) == 2
    assert captured_payloads[0]["tool_choice"] == "auto"
    assert captured_payloads[0]["messages"][0] == {"role": "system", "content": "你是助手"}
    assert captured_payloads[1]["tool_choice"] == {
        "type": "function",
        "function": {"name": "create_report_chart"},
    }
    assert captured_payloads[1]["messages"][0] == {"role": "system", "content": "你是助手"}
    assert result["stop_reason"] == "tool_use"
    assert result["content"][0].type == "tool_use"
    assert result["content"][0].input == {"title": "AQI", "data": {}}

import json
from pathlib import Path

import httpx
import pytest
import anthropic

from app.services.llm_service import LLMService
from config.settings import settings


def test_mimo_anthropic_client_uses_sdk_api_key_authentication(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mimo")
    monkeypatch.setattr(settings, "mimo_api_mode", "anthropic_messages")
    monkeypatch.setattr(
        settings,
        "mimo_base_url",
        "https://api.xiaomimimo.com/anthropic",
    )
    monkeypatch.setattr(settings, "mimo_api_key", "mimo-key")
    monkeypatch.setattr(settings, "mimo_model", "mimo-v2.5")

    captured = {}

    class FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeAsyncAnthropic)

    service = LLMService()

    assert service.anthropic_client is not None
    assert captured["api_key"] == "mimo-key"
    assert captured["auth_token"] is None
    assert captured["base_url"] == "https://api.xiaomimimo.com/anthropic"
    assert "default_headers" not in captured


def test_deepseek_api_mode_setting_exists():
    assert settings.deepseek_api_mode in {"anthropic_messages", "chat_completions"}


def test_text_qwen_settings_are_removed_but_visual_settings_remain():
    assert not hasattr(settings, "qwen_api_key")
    assert not hasattr(settings, "qwen_base_url")
    assert not hasattr(settings, "qwen_model")
    assert not hasattr(settings, "qwen_api_mode")
    assert settings.qwen_vl_model
    assert settings.qwen_vision_model


def test_llm_service_rejects_retired_qwen_provider(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "qwen")

    with pytest.raises(ValueError, match="Unsupported LLM provider: qwen"):
        LLMService()


def test_llm_service_loads_qwen_vl_chat_completions_config(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "qwen_vl")
    monkeypatch.setattr(settings, "qwen_vl_api_key", "vision-key")
    monkeypatch.setattr(
        settings,
        "qwen_vl_base_url",
        "https://dashscope.example/compatible-mode/v1",
    )
    monkeypatch.setattr(settings, "qwen_vision_model", "qwen3.7-plus")

    service = LLMService()

    assert service.provider == "qwen_vl"
    assert service.api_mode == "chat_completions"
    assert service.api_key == "vision-key"
    assert service.base_url == "https://dashscope.example/compatible-mode/v1"
    assert service.model == "qwen3.7-plus"
    assert service.anthropic_client is None


def test_multimodal_auto_profile_includes_qwen_vl_fallback(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(
        settings,
        "llm_multimodal_models",
        "mimo/mimo-v2.5,qwen_vl/qwen3.7-plus",
    )

    service = LLMService()

    with service.use_auto_profile("multimodal"):
        assert service.provider == "mimo"
        assert service.model == "mimo-v2.5"
        assert service.request_fallbacks == "qwen_vl/qwen3.7-plus"


def test_ocr_configuration_uses_only_visual_qwen_settings(monkeypatch):
    import inspect

    from app.services.ops_audit.semantic import ocr_adapter

    monkeypatch.setenv("QWEN_API_KEY", "retired-text-key")
    monkeypatch.setenv("QWEN_VL_API_KEY", "vision-key")
    monkeypatch.setenv("QWEN_VISION_MODEL", "qwen3.7-plus")

    resolver_source = inspect.getsource(ocr_adapter._resolve_qwen_api_key)
    assert 'getattr(settings, "qwen_api_key", "")' not in resolver_source
    assert ocr_adapter._resolve_qwen_api_key() == "vision-key"
    assert ocr_adapter._resolve_qwen_model("flow_visual") == "qwen3.7-plus"


def test_legacy_text_qwen_runtime_branches_are_removed():
    backend_root = Path(__file__).resolve().parents[1]
    for relative_path in [
        "app/routers/knowledge_qa.py",
        "app/agent/core/planner.py",
    ]:
        source = (backend_root / relative_path).read_text(encoding="utf-8")
        assert 'provider == "qwen"' not in source

    proxy_source = (backend_root / "app/proxy_server.py").read_text(
        encoding="utf-8"
    )
    assert "API_BASE_URL" not in proxy_source
    assert "chat/completions" not in proxy_source


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

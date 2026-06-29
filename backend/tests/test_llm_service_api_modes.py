import json

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

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.llm_service import LLMService
from app.services import llm_failover
from config.settings import Settings


def test_mimo_default_base_url_uses_anthropic_endpoint():
    settings = Settings(_env_file=None)

    assert settings.mimo_base_url == "https://api.xiaomimimo.com/anthropic"


def test_agent_modes_use_the_normal_model_chains_without_multimodal_override():
    settings = Settings(_env_file=None)

    assert settings.agnes_base_url == "https://apihub.agnes-ai.com/v1"
    assert settings.agnes_model == "agnes-2.0-flash"
    assert settings.agnes_api_mode == "chat_completions"
    assert settings.llm_multimodal_models == ""


@pytest.mark.asyncio
async def test_chat_anthropic_calls_messages_create_once():
    service = object.__new__(LLMService)
    service.provider = "mimo"
    service.base_url = "https://mimo.example/anthropic"
    service.api_key = "test-key"
    service.model = "mimo-test"
    service._provider_state_lock = asyncio.Lock()
    service.anthropic_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    content=[],
                    model="mimo-test",
                    usage=SimpleNamespace(input_tokens=7, output_tokens=3),
                    stop_reason="end_turn",
                )
            )
        )
    )

    result = await service.chat_anthropic(
        messages=[{"role": "user", "content": "hello"}],
        tools=None,
        temperature=0.3,
        system="test system",
    )

    assert service.anthropic_client.messages.create.await_count == 1
    assert result["usage"] == {"input_tokens": 7, "output_tokens": 3}


@pytest.mark.asyncio
async def test_chat_anthropic_rebuilds_params_for_fallback_candidate(monkeypatch):
    class ProviderError(Exception):
        status_code = 402

    first_create = AsyncMock(side_effect=ProviderError("billing failed"))
    second_create = AsyncMock(
        return_value=SimpleNamespace(
            content=[],
            model="deepseek-test",
            usage=SimpleNamespace(input_tokens=11, output_tokens=5),
            stop_reason="end_turn",
        )
    )

    service = object.__new__(LLMService)
    service.provider = "mimo"
    service.base_url = "https://mimo.example/anthropic"
    service.api_key = "test-key"
    service.model = "mimo-test"
    service._provider_state_lock = asyncio.Lock()
    service.anthropic_client = SimpleNamespace(messages=SimpleNamespace(create=first_create))

    def fake_load_provider_config():
        if service.provider == "deepseek":
            service.base_url = "https://deepseek.example/anthropic"
            service.api_key = "test-key"
            service.anthropic_client = SimpleNamespace(messages=SimpleNamespace(create=second_create))

    monkeypatch.setattr(LLMService, "_load_provider_config", lambda self: fake_load_provider_config())
    monkeypatch.setattr(llm_failover.settings, "llm_fallbacks", "deepseek/deepseek-test")
    monkeypatch.setattr(llm_failover.settings, "llm_failover_cooldown_seconds", 0)

    result = await service.chat_anthropic(
        messages=[
            {"role": "user", "content": "hello"},
            {"role": "system", "content": "[上下文已压缩]"},
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "internal"},
                    {"type": "text", "text": "visible"},
                ],
            },
        ],
        tools=None,
        temperature=0.3,
        system="test system",
    )

    assert result["model"] == "deepseek-test"
    assert first_create.await_count == 1
    assert second_create.await_count == 1

    first_params = first_create.await_args.kwargs
    second_params = second_create.await_args.kwargs

    assert first_params["model"] == "mimo-test"
    assert second_params["model"] == "deepseek-test"
    assert all(msg["role"] in {"user", "assistant"} for msg in second_params["messages"])
    assert all(msg["role"] != "system" for msg in second_params["messages"])
    assert second_params["thinking"] == {"type": "disabled"}
    assert "cache_control" not in str(second_params)

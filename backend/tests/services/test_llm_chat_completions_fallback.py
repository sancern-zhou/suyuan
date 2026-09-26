from types import MethodType

import pytest

from app.services import llm_failover
from app.services.llm_failover import LLMResponseRejectedError
from app.services.llm_service import LLMService


def make_service():
    service = LLMService()
    service.provider = "agnes"
    service.model = "agnes-2.0-flash"
    service.api_mode = "chat_completions"
    service.request_fallbacks = "minimax/MiniMax-M3"

    def switch(self, provider, model=None):
        self.provider = provider
        self.model = model or self.model
        self.api_mode = "chat_completions"

    service._switch_provider_for_attempt = MethodType(switch, service)
    return service


def _text_of(response):
    return "".join(
        str(block.get("text") or "")
        for block in (response.get("content") or [])
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


@pytest.mark.asyncio
async def test_non_streaming_chat_completions_uses_configured_fallback(monkeypatch):
    monkeypatch.setattr("app.services.llm_service.get_cooldown_failure", lambda provider: None)
    service = make_service()
    attempted = []

    async def create(**kwargs):
        attempted.append(service.provider)
        if service.provider == "agnes":
            raise RuntimeError("HTTP 400 Bad Request")
        return {"content": [{"type": "text", "text": "ok"}], "model": service.model}

    service._chat_completions_create = create

    result = await service.chat_anthropic(messages=[{"role": "user", "content": "hi"}])

    assert attempted == ["agnes", "minimax"]
    assert result["content"][0]["text"] == "ok"


@pytest.mark.asyncio
async def test_chat_anthropic_falls_back_when_validate_rejects_response(monkeypatch):
    monkeypatch.setattr("app.services.llm_service.get_cooldown_failure", lambda provider: None)
    monkeypatch.setattr(llm_failover.settings, "llm_failover_cooldown_seconds", 60)
    llm_failover._cooldowns.clear()
    service = make_service()
    attempted = []

    async def create(**kwargs):
        attempted.append(service.provider)
        if service.provider == "agnes":
            return {"content": [{"type": "thinking", "thinking": "reasoning only"}]}
        return {"content": [{"type": "text", "text": "通报正文"}], "model": service.model}

    service._chat_completions_create = create

    result = await service.chat_anthropic(
        messages=[{"role": "user", "content": "hi"}],
        validate=lambda response: None if _text_of(response) else "LLM 未生成告警通报正文（空响应）",
    )

    assert attempted == ["agnes", "minimax"]
    assert result["content"][0]["text"] == "通报正文"
    assert llm_failover.get_cooldown_failure("agnes") is None
    assert llm_failover.get_cooldown_failure("minimax") is None


@pytest.mark.asyncio
async def test_chat_anthropic_raises_when_all_candidates_rejected(monkeypatch):
    monkeypatch.setattr("app.services.llm_service.get_cooldown_failure", lambda provider: None)
    llm_failover._cooldowns.clear()
    service = make_service()
    attempted = []

    async def create(**kwargs):
        attempted.append(service.provider)
        return {"content": [{"type": "thinking", "thinking": "reasoning only"}]}

    service._chat_completions_create = create

    with pytest.raises(LLMResponseRejectedError) as excinfo:
        await service.chat_anthropic(
            messages=[{"role": "user", "content": "hi"}],
            validate=lambda response: None if _text_of(response) else "LLM 未生成告警通报正文（空响应）",
        )

    assert attempted == ["agnes", "minimax"]
    assert excinfo.value.reason == "LLM 未生成告警通报正文（空响应）"
    assert excinfo.value.attempts[-1]["provider"] == "minimax"
    assert excinfo.value.attempts[-1]["reason"] == "invalid_response"


@pytest.mark.asyncio
async def test_streaming_chat_completions_falls_back_before_first_event(monkeypatch):
    monkeypatch.setattr("app.services.llm_service.get_cooldown_failure", lambda provider: None)
    service = make_service()
    attempted = []

    async def stream(**kwargs):
        attempted.append(service.provider)
        if service.provider == "agnes":
            raise RuntimeError("HTTP 400 Bad Request")
        yield {"type": "message_stop", "data": {}}

    service._chat_completions_stream = stream

    events = [
        event
        async for event in service.chat_anthropic_streaming(
            messages=[{"role": "user", "content": "hi"}]
        )
    ]

    assert attempted == ["agnes", "minimax"]
    assert events == [{"type": "message_stop", "data": {}}]

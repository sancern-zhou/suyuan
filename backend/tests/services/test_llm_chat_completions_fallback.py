from types import MethodType

import pytest

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

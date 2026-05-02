from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.llm_service import LLMService


@pytest.mark.asyncio
async def test_chat_anthropic_calls_messages_create_once():
    service = object.__new__(LLMService)
    service.provider = "mimo"
    service.model = "mimo-test"
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

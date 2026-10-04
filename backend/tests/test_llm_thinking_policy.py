"""思考策略：模型档位 × 调用方类型 → 是否关闭思考。"""

import asyncio

import pytest

from app.services.llm_thinking_policy import (
    get_agent_caller_tier,
    model_tier,
    reset_agent_caller_tier,
    set_agent_caller_tier,
    should_disable_thinking,
)


def test_model_tier_by_name():
    assert model_tier("Qwen3.8-Flash") == "flash"
    assert model_tier("deepseek-v4.1-flash") == "flash"
    assert model_tier("Qwen3.8-Max") == "pro"
    assert model_tier("DeepSeek-V4.1") == "pro"
    assert model_tier("") == "pro"


def test_should_disable_thinking_matrix():
    # flash 档：无条件关闭（主/子 agent 一致）
    assert should_disable_thinking("Qwen3.8-Flash", True) == (True, "flash_tier")
    # pro 档：主 agent 保持思考，子 agent 关闭
    assert should_disable_thinking("Qwen3.8-Max", True) == (False, "pro_tier")
    token = set_agent_caller_tier("subagent")
    try:
        assert should_disable_thinking("Qwen3.8-Max", True) == (True, "subagent_auto")
        assert should_disable_thinking("Qwen3.8-Flash", True) == (True, "flash_tier")
    finally:
        reset_agent_caller_tier(token)
    # 总开关关闭：一律不干预
    assert should_disable_thinking("Qwen3.8-Flash", False) == (False, "master_switch_off")


def test_caller_tier_isolated_across_parallel_tasks():
    async def child(tag: str, delay: float) -> str:
        set_agent_caller_tier(tag)
        await asyncio.sleep(delay)
        return get_agent_caller_tier()

    async def main():
        return await asyncio.gather(child("subagent", 0.05), child("main", 0.02))

    first, second = asyncio.new_event_loop().run_until_complete(main())
    assert (first, second) == ("subagent", "main")
    assert get_agent_caller_tier() is None


def test_scnet_request_thinking_follows_policy(monkeypatch):
    from config.settings import settings
    from app.services.llm_service import LLMService

    def build(provider: str, model: str) -> dict:
        service = LLMService.__new__(LLMService)
        service.provider = provider
        service.model = model
        service.api_mode = "anthropic_messages"
        return service._build_anthropic_api_params(
            messages=[{"role": "user", "content": [{"type": "text", "text": "x"}]}],
            tools=[{"name": "t"}],
            max_tokens=1000,
            temperature=0.3,
            system="",
            streaming=True,
        )

    monkeypatch.setattr(settings, "scnet_disable_thinking", True)
    # flash 主 agent：关闭
    flash_main = build("scnet", "Qwen3.8-Flash")
    assert flash_main["extra_body"]["thinking"] == {"type": "disabled"}
    # pro + 主 agent：保留思考（不传参数，网关默认开启）
    pro_main = build("scnet", "Qwen3.8-Max")
    assert "thinking" not in pro_main.get("extra_body", {})
    # pro + 子 agent：关闭
    token = set_agent_caller_tier("subagent")
    try:
        pro_sub = build("scnet", "Qwen3.8-Max")
        assert pro_sub["extra_body"]["thinking"] == {"type": "disabled"}
    finally:
        reset_agent_caller_tier(token)
    # 总开关关闭：flash 也不干预
    monkeypatch.setattr(settings, "scnet_disable_thinking", False)
    flash_off = build("scnet", "Qwen3.8-Flash")
    assert "thinking" not in flash_off.get("extra_body", {})


def test_go_provider_payload_follows_policy(monkeypatch):
    from config.settings import settings
    from app.services.llm_service import LLMService

    def build(model: str) -> dict:
        service = LLMService.__new__(LLMService)
        service.provider = "go"
        service.model = model
        service.api_mode = "chat_completions"
        return service._build_chat_completions_payload(
            messages=[{"role": "user", "content": "x"}],
            tools=None,
            max_tokens=1000,
            temperature=0.3,
            system=None,
            stream=False,
        )

    monkeypatch.setattr(settings, "scnet_disable_thinking", True)
    # flash 档（deepseek-v4.1-flash）：关闭
    assert build("deepseek-v4.1-flash")["enable_thinking"] is False
    # pro 档 + 主 agent：不干预（网关默认开启）
    assert "enable_thinking" not in build("deepseek-v4-pro")
    # pro 档 + 子 agent：关闭
    token = set_agent_caller_tier("subagent")
    try:
        assert build("deepseek-v4-pro")["enable_thinking"] is False
    finally:
        reset_agent_caller_tier(token)

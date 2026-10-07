"""思考策略：请求挡位 × 调用方类型 → 是否关闭思考（与模型名无关）。"""

import asyncio

from app.services.llm_thinking_policy import (
    get_agent_caller_tier,
    get_request_tier,
    reset_agent_caller_tier,
    reset_request_tier,
    set_agent_caller_tier,
    set_request_tier,
    should_disable_thinking,
)


def test_request_tier_context_isolation():
    token = set_request_tier("flash")
    try:
        assert get_request_tier() == "flash"
    finally:
        reset_request_tier(token)
    assert get_request_tier() is None
    # 空值归一化为 None
    token = set_request_tier("  ")
    try:
        assert get_request_tier() is None
    finally:
        reset_request_tier(token)


def test_should_disable_thinking_matrix():
    # flash 挡：关闭
    assert should_disable_thinking(True, request_tier="flash") == (True, "flash_tier")
    # pro 挡：保持思考（网关默认开启）
    assert should_disable_thinking(True, request_tier="pro") == (False, "pro_tier")
    # auto / 未设置：主 agent 保持思考
    assert should_disable_thinking(True, request_tier="auto") == (False, "auto_tier")
    assert should_disable_thinking(True) == (False, "auto_tier")
    # 子 agent：无论挡位一律关闭（固定流程节点求快）
    assert should_disable_thinking(True, request_tier="pro", caller_tier="subagent") == (True, "subagent_auto")
    assert should_disable_thinking(True, request_tier="auto", caller_tier="subagent") == (True, "subagent_auto")
    # 总开关关闭：一律不干预
    assert should_disable_thinking(False, request_tier="flash") == (False, "master_switch_off")


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


def test_use_model_tier_binds_request_tier(monkeypatch):
    from config.settings import settings
    from app.services.llm_service import LLMService
    from app.services.llm_thinking_policy import get_request_tier

    monkeypatch.setattr(settings, "llm_flash_models", "go/deepseek-v4.1-flash")
    monkeypatch.setattr(settings, "llm_pro_models", "go/deepseek-v4.1-flash")
    service = LLMService.__new__(LLMService)
    service.provider = settings.llm_provider.lower()
    service.model = settings.scnet_model
    service.request_fallbacks = None
    service.anthropic_client = None

    base_provider, base_model = service.provider, service.model

    # flash 挡：思考关 + 模型链不变
    with service.use_model_tier("flash"):
        assert get_request_tier() == "flash"
        assert (service.provider, service.model) == (base_provider, base_model)
        assert service.request_fallbacks is None
    assert get_request_tier() is None

    # pro 挡：思考开 + 模型链不变
    with service.use_model_tier("pro"):
        assert get_request_tier() == "pro"
        assert (service.provider, service.model) == (base_provider, base_model)

    # auto：绑定 auto（策略层视同“主 agent 保持思考”）
    with service.use_model_tier("auto"):
        assert get_request_tier() == "auto"

    # 非法挡位仍拒绝
    try:
        with service.use_model_tier("turbo"):
            raise AssertionError("should reject")
    except ValueError:
        pass


def test_scnet_request_thinking_follows_policy(monkeypatch):
    from config.settings import settings
    from app.services.llm_service import LLMService
    from app.services.llm_thinking_policy import set_request_tier

    def build() -> dict:
        service = LLMService.__new__(LLMService)
        service.provider = "scnet"
        service.model = "DeepSeek-V4.1-Flash"
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
    # flash 挡：关闭
    tier_token = set_request_tier("flash")
    try:
        assert build()["extra_body"]["thinking"] == {"type": "disabled"}
    finally:
        reset_request_tier(tier_token)
    # pro 挡 + 主 agent：保留思考（不传参数，网关默认开启）
    tier_token = set_request_tier("pro")
    try:
        assert "thinking" not in build().get("extra_body", {})
    finally:
        reset_request_tier(tier_token)
    # auto + 子 agent：关闭
    tier_token = set_request_tier("auto")
    caller_token = set_agent_caller_tier("subagent")
    try:
        assert build()["extra_body"]["thinking"] == {"type": "disabled"}
    finally:
        reset_agent_caller_tier(caller_token)
        reset_request_tier(tier_token)
    # 总开关关闭：flash 也不干预
    monkeypatch.setattr(settings, "scnet_disable_thinking", False)
    tier_token = set_request_tier("flash")
    try:
        assert "thinking" not in build().get("extra_body", {})
    finally:
        reset_request_tier(tier_token)


def test_go_provider_payload_follows_policy(monkeypatch):
    from config.settings import settings
    from app.services.llm_service import LLMService
    from app.services.llm_thinking_policy import set_request_tier

    def build() -> dict:
        service = LLMService.__new__(LLMService)
        service.provider = "go"
        service.model = "deepseek-v4.1-flash"
        service.api_mode = "chat_completions"
        return service._build_chat_completions_payload(
            messages=[{"role": "user", "content": "x"}],
            tools=None,
            max_tokens=1000,
            temperature=0.3,
            system=None,
            stream=False,
        )

    monkeypatch.setattr(settings, "go_disable_thinking", True)
    # flash 挡：关闭
    tier_token = set_request_tier("flash")
    try:
        assert build()["enable_thinking"] is False
    finally:
        reset_request_tier(tier_token)
    # pro 挡：不干预（网关默认开启）
    tier_token = set_request_tier("pro")
    try:
        assert "enable_thinking" not in build()
    finally:
        reset_request_tier(tier_token)
    # 子 agent：关闭
    caller_token = set_agent_caller_tier("subagent")
    try:
        assert build()["enable_thinking"] is False
    finally:
        reset_agent_caller_tier(caller_token)

    monkeypatch.setattr(settings, "go_disable_thinking", False)
    tier_token = set_request_tier("flash")
    try:
        assert "enable_thinking" not in build()
    finally:
        reset_request_tier(tier_token)

import pytest

from app.services.llm_service import LLMService


def test_auto_multimodal_profile_selects_configured_model_chain(monkeypatch):
    service = LLMService()
    original_provider = service.provider
    original_model = service.model

    monkeypatch.setattr(
        "app.services.llm_service.settings.llm_multimodal_models",
        "mimo/mimo-v2.5,minimax/MiniMax-M3",
        raising=False,
    )

    with service.use_auto_profile("multimodal"):
        assert service.provider == "mimo"
        assert service.model == "mimo-v2.5"
        assert service.request_fallbacks == "minimax/MiniMax-M3"

    assert service.provider == original_provider
    assert service.model == original_model


def test_inherited_provider_chain_is_not_overridden_by_multimodal_profile(monkeypatch):
    service = LLMService()
    monkeypatch.setattr(service, "_load_provider_config", lambda: None)

    with service.use_provider_chain(
        "bailian",
        "qwen3.8-max-preview",
        "agnes/agnes-2.0-flash,minimax/MiniMax-M3",
    ):
        with service.use_auto_profile("multimodal"):
            assert service.provider == "bailian"
            assert service.model == "qwen3.8-max-preview"
            assert service.request_fallbacks == (
                "agnes/agnes-2.0-flash,minimax/MiniMax-M3"
            )
            assert service.resolve_model_chain("multimodal") == (
                "bailian",
                "qwen3.8-max-preview",
                "agnes/agnes-2.0-flash,minimax/MiniMax-M3",
            )


def test_resolve_model_chain_returns_complete_multimodal_priority(monkeypatch):
    service = LLMService()
    monkeypatch.setattr(
        "app.services.llm_service.settings.llm_multimodal_models",
        "bailian/qwen3.8-max-preview,agnes/agnes-2.0-flash,minimax/MiniMax-M3",
        raising=False,
    )

    assert service.resolve_model_chain("multimodal") == (
        "bailian",
        "qwen3.8-max-preview",
        "agnes/agnes-2.0-flash,minimax/MiniMax-M3",
    )


@pytest.mark.parametrize("tier", ["flash", "pro"])
def test_multimodal_profile_overrides_explicit_model_tier(monkeypatch, tier):
    service = LLMService()

    monkeypatch.setattr(
        f"app.services.llm_service.settings.llm_{tier}_models",
        "deepseek/deepseek-v4-flash",
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.llm_service.settings.llm_multimodal_models",
        "mimo/mimo-v2.5,minimax/MiniMax-M3",
        raising=False,
    )

    with service.use_model_tier(tier):
        assert service.provider == "deepseek"
        assert service.model == "deepseek-v4-flash"
        with service.use_auto_profile("multimodal"):
            assert service.provider == "mimo"
            assert service.model == "mimo-v2.5"
            assert service.request_fallbacks == "minimax/MiniMax-M3"

        assert service.provider == "deepseek"
        assert service.model == "deepseek-v4-flash"

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


def test_auto_profile_does_not_override_explicit_model_tier(monkeypatch):
    service = LLMService()

    monkeypatch.setattr(
        "app.services.llm_service.settings.llm_flash_models",
        "deepseek/deepseek-v4-flash",
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.llm_service.settings.llm_multimodal_models",
        "mimo/mimo-v2.5,minimax/MiniMax-M3",
        raising=False,
    )

    with service.use_model_tier("flash"):
        assert service.provider == "deepseek"
        assert service.model == "deepseek-v4-flash"
        with service.use_auto_profile("multimodal"):
            assert service.provider == "deepseek"
            assert service.model == "deepseek-v4-flash"

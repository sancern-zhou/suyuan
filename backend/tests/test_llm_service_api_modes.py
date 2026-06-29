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

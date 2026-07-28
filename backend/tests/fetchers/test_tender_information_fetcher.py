from app.fetchers.tenders import tender_information_fetcher as fetcher_module
from app.fetchers.tenders.tender_information_fetcher import TenderInformationFetcher
from app.services.tenders.llm import TenderLLMClientPool
from config.settings import settings


def test_default_llm_builds_agnes_primary_and_bailian_secondary_with_bailian_screening(
    monkeypatch,
):
    created = []

    class FakeLLMClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            created.append(self)

    monkeypatch.setattr(
        fetcher_module,
        "OpenAICompatibleTenderLLMClient",
        FakeLLMClient,
    )
    monkeypatch.setattr(settings, "agnes_api_key", "agnes-key")
    monkeypatch.setattr(settings, "agnes_base_url", "https://agnes.example/v1")
    monkeypatch.setattr(settings, "agnes_model", "agnes-2.0-flash")
    monkeypatch.setattr(settings, "agnes_api_mode", "chat_completions")
    monkeypatch.setattr(settings, "bailian_api_key", "bailian-key")
    monkeypatch.setattr(
        settings,
        "bailian_base_url",
        "https://bailian.example/apps/anthropic",
    )
    monkeypatch.setattr(settings, "bailian_model", "qwen3.6-flash")
    monkeypatch.setattr(settings, "bailian_api_mode", "anthropic_messages")
    monkeypatch.setattr(settings, "tender_secondary_llm_api_key", None)
    monkeypatch.setattr(settings, "tender_secondary_llm_base_url", None)
    monkeypatch.setattr(settings, "tender_secondary_llm_model", "qwen3.6-flash")
    monkeypatch.setattr(settings, "tender_llm_concurrency", 3)
    monkeypatch.setattr(settings, "tender_secondary_llm_concurrency", 2)

    pool = TenderInformationFetcher()._default_llm()

    assert isinstance(pool, TenderLLMClientPool)
    assert pool.screening_client_index == 1
    assert pool.detail_concurrency == 5
    assert len(created) == 2
    assert created[0].kwargs == {
        "api_key": "agnes-key",
        "base_url": "https://agnes.example/v1",
        "model": "agnes-2.0-flash",
        "provider": "agnes",
        "api_mode": "chat_completions",
    }
    assert created[1].kwargs == {
        "api_key": "bailian-key",
        "base_url": "https://bailian.example/apps/anthropic",
        "model": "qwen3.6-flash",
        "provider": "bailian",
        "api_mode": "anthropic_messages",
    }

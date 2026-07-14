from app.fetchers.tenders import tender_information_fetcher as fetcher_module
from app.fetchers.tenders.tender_information_fetcher import TenderInformationFetcher
from config.settings import settings


def test_default_llm_uses_configured_secondary_when_primary_is_missing(monkeypatch):
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
    monkeypatch.setattr(settings, "tender_llm_api_key", None)
    monkeypatch.setattr(settings, "tender_llm_base_url", None)
    monkeypatch.setattr(settings, "tender_llm_model", None)
    monkeypatch.setattr(settings, "tender_secondary_llm_api_key", "agnes-key")
    monkeypatch.setattr(
        settings,
        "tender_secondary_llm_base_url",
        "https://agnes.example/v1",
    )
    monkeypatch.setattr(
        settings,
        "tender_secondary_llm_model",
        "agnes-2.0-flash",
    )

    client = TenderInformationFetcher()._default_llm()

    assert client is created[0]
    assert len(created) == 1
    assert client.kwargs == {
        "api_key": "agnes-key",
        "base_url": "https://agnes.example/v1",
        "model": "agnes-2.0-flash",
    }

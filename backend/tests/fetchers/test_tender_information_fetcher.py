from datetime import date

import pytest

from app.fetchers.tenders.tender_information_fetcher import TenderInformationFetcher
from app.services.tenders.config import DEFAULT_TENDER_KEYWORDS
from app.services.tenders.llm import TenderLLMClientPool
from app.services.tenders.models import NoticeType, PipelineRunResult


class FakeRepository:
    def __init__(self):
        self.created_runs = []
        self.finished_runs = []

    async def create_run(self, target_date, keywords, notice_types):
        self.created_runs.append((target_date, keywords, notice_types))
        return 7

    async def finish_run(self, run_id, result):
        self.finished_runs.append((run_id, result))


class FakePipeline:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def run_daily(self, keywords, notice_types, publish_date, max_pages):
        self.calls.append(
            {
                "keywords": keywords,
                "notice_types": notice_types,
                "publish_date": publish_date,
                "max_pages": max_pages,
            }
        )
        return self.result


def test_fetcher_uses_approved_identity_and_schedule():
    fetcher = TenderInformationFetcher()

    assert fetcher.name == "tender_information_fetcher"
    assert fetcher.schedule == "30 2 * * *"
    assert "招投标信息" in fetcher.description
    assert fetcher.config.keywords == DEFAULT_TENDER_KEYWORDS
    assert fetcher.config.notice_types == [NoticeType.TENDER, NoticeType.WINNING_BID]


def test_fetcher_target_date_defaults_to_yesterday():
    assert TenderInformationFetcher.compute_target_date(date(2026, 7, 1)) == date(
        2026, 6, 30
    )


def test_fetcher_builds_dual_llm_pool_from_settings(monkeypatch):
    monkeypatch.setattr(
        "app.fetchers.tenders.tender_information_fetcher.settings.tender_llm_api_key",
        "primary-key",
    )
    monkeypatch.setattr(
        "app.fetchers.tenders.tender_information_fetcher.settings.tender_llm_base_url",
        "https://primary.example/v1",
    )
    monkeypatch.setattr(
        "app.fetchers.tenders.tender_information_fetcher.settings.tender_llm_model",
        "primary-model",
    )
    monkeypatch.setattr(
        "app.fetchers.tenders.tender_information_fetcher.settings.tender_llm_concurrency",
        5,
    )
    monkeypatch.setattr(
        "app.fetchers.tenders.tender_information_fetcher.settings.tender_secondary_llm_api_key",
        "secondary-key",
    )
    monkeypatch.setattr(
        "app.fetchers.tenders.tender_information_fetcher.settings.tender_secondary_llm_base_url",
        "https://apihub.agnes-ai.com/v1/chat/completions",
    )
    monkeypatch.setattr(
        "app.fetchers.tenders.tender_information_fetcher.settings.tender_secondary_llm_model",
        "agnes-2.0-flash",
    )
    monkeypatch.setattr(
        "app.fetchers.tenders.tender_information_fetcher.settings.tender_secondary_llm_concurrency",
        5,
    )

    llm = TenderInformationFetcher()._default_llm()

    assert isinstance(llm, TenderLLMClientPool)
    assert [entry.concurrency for entry in llm.entries] == [5, 5]
    assert llm.entries[1].client.base_url == "https://apihub.agnes-ai.com/v1"
    assert llm.entries[1].client.model == "agnes-2.0-flash"


def test_default_client_receives_qianlima_account_pool_from_settings(monkeypatch):
    captured_kwargs = {}

    class FakeQianlimaClient:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(
        "app.fetchers.tenders.tender_information_fetcher.QianlimaClient",
        FakeQianlimaClient,
    )
    monkeypatch.setattr(
        "app.fetchers.tenders.tender_information_fetcher.settings.qianlima_accounts",
        "account1:pass1,account2:pass2",
        raising=False,
    )

    TenderInformationFetcher()._default_client()

    assert captured_kwargs["accounts"] == "account1:pass1,account2:pass2"


@pytest.mark.asyncio
async def test_disabled_fetcher_skips_pipeline():
    pipeline = FakePipeline(PipelineRunResult())
    repository = FakeRepository()
    fetcher = TenderInformationFetcher(
        enabled=False,
        repository_factory=lambda: repository,
        pipeline_factory=lambda **_kwargs: pipeline,
    )

    result = await fetcher.fetch_and_store()

    assert result["skipped"] is True
    assert pipeline.calls == []
    assert repository.created_runs == []


@pytest.mark.asyncio
async def test_fetcher_runs_pipeline_and_finishes_summary():
    pipeline_result = PipelineRunResult(
        total_candidates=5,
        duplicate_candidates=1,
        filtered_out=2,
        detail_fetch_failures=1,
        saved_notices=1,
        errors=["detail failed"],
    )
    pipeline = FakePipeline(pipeline_result)
    repository = FakeRepository()
    fetcher = TenderInformationFetcher(
        repository_factory=lambda: repository,
        llm_factory=lambda: None,
        pipeline_factory=lambda **_kwargs: pipeline,
        today_factory=lambda: date(2026, 7, 1),
    )

    result = await fetcher.fetch_and_store()

    assert pipeline.calls == [
        {
            "keywords": DEFAULT_TENDER_KEYWORDS,
            "notice_types": [NoticeType.TENDER, NoticeType.WINNING_BID],
            "publish_date": date(2026, 6, 30),
            "max_pages": 0,
        }
    ]
    assert repository.created_runs == [
        (
            date(2026, 6, 30),
            DEFAULT_TENDER_KEYWORDS,
            [NoticeType.TENDER, NoticeType.WINNING_BID],
        )
    ]
    assert repository.finished_runs == [(7, pipeline_result)]
    assert result["target_date"] == "2026-06-30"
    assert result["saved_notices"] == 1
    assert result["errors"] == 1

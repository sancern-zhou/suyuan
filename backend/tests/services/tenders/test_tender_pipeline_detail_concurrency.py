import asyncio

import pytest

from app.services.tenders.models import (
    NoticeType,
    PipelineRunResult,
    TenderCandidate,
    TenderFilterDecision,
    TenderNotice,
)
from app.services.tenders.pipeline import TenderPipeline
from app.services.tenders.qianlima_client import QianlimaDetailAccessExhaustedError


class ConcurrentDetailClient:
    def __init__(self):
        self.active = 0
        self.max_active = 0

    async def fetch_detail(self, candidate):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.01)
            return f"详情 {candidate.title}"
        finally:
            self.active -= 1


class HangingDetailClient:
    async def fetch_detail(self, candidate):
        await asyncio.sleep(10)
        return "unreachable"


class ExhaustedDetailClient:
    def __init__(self):
        self.calls = 0

    async def fetch_detail(self, candidate):
        self.calls += 1
        raise QianlimaDetailAccessExhaustedError("千里马全部账号详情浏览额度已耗尽")


class AcceptingRepository:
    def __init__(self):
        self.saved_notices = []

    async def save_candidate(self, candidate, decision=None):
        return True

    async def update_candidate_decision(self, candidate, decision):
        pass

    async def save_notice(self, notice):
        self.saved_notices.append(notice)


class AcceptingLLM:
    def __init__(self):
        self.review_and_extract_calls = 0
        self.review_calls = 0
        self.extract_calls = 0

    async def review_candidates(self, candidates, rule_decision):
        return {
            candidate.normalized_url_key(): TenderFilterDecision(
                is_relevant=True,
                reason="batch keep",
                confidence=0.8,
                decision_source="llm",
            )
            for candidate in candidates
        }

    async def review_candidate(self, candidate, rule_decision, detail_text=""):
        self.review_calls += 1
        return TenderFilterDecision(
            is_relevant=True,
            reason="detail keep",
            confidence=0.9,
            decision_source="llm",
        )

    async def extract_notice(self, candidate, detail_text, decision):
        self.extract_calls += 1
        return TenderNotice(
            title=candidate.title,
            url=candidate.url,
            notice_type=candidate.notice_type,
            raw_content=detail_text,
            environment_relevance=True,
        )

    async def review_and_extract_notice(self, candidate, detail_text, decision):
        self.review_and_extract_calls += 1
        return TenderNotice(
            title=candidate.title,
            url=candidate.url,
            notice_type=candidate.notice_type,
            raw_content=detail_text,
            environment_relevance=True,
        )


class FailingExtractLLM(AcceptingLLM):
    async def review_and_extract_notice(self, candidate, detail_text, decision):
        raise RuntimeError("llm review/extract unavailable")


class FailingReviewLLM(AcceptingLLM):
    async def review_and_extract_notice(self, candidate, detail_text, decision):
        raise RuntimeError("llm review/extract unavailable")


class RejectingDetailLLM(AcceptingLLM):
    async def review_and_extract_notice(self, candidate, detail_text, decision):
        self.review_and_extract_calls += 1
        return TenderFilterDecision(
            is_relevant=False,
            reason="详情页是环评审批公示，不是环境业务采购公告",
            confidence=0.93,
            decision_source="llm",
            project_category="other",
        )


class PooledAcceptingLLM(AcceptingLLM):
    @property
    def detail_concurrency(self):
        return 10


@pytest.mark.asyncio
async def test_pipeline_processes_relevant_details_concurrently(monkeypatch):
    monkeypatch.setenv("TENDER_DETAIL_CONCURRENCY", "3")
    client = ConcurrentDetailClient()
    repository = AcceptingRepository()
    llm = AcceptingLLM()
    pipeline = TenderPipeline(
        client=client,
        repository=repository,
        llm_client=llm,
    )
    candidates = [
        TenderCandidate(
            title=f"环境监测服务{i}",
            url=f"https://example.test/{i}",
            notice_type=NoticeType.TENDER,
        )
        for i in range(6)
    ]
    result = PipelineRunResult()

    await pipeline._process_candidates(candidates, result)

    assert client.max_active > 1
    assert client.max_active <= 3
    assert result.saved_notices == 6
    assert len(repository.saved_notices) == 6
    assert llm.review_and_extract_calls == 6
    assert llm.review_calls == 0
    assert llm.extract_calls == 0


@pytest.mark.asyncio
async def test_pipeline_uses_llm_pool_detail_concurrency_by_default(monkeypatch):
    monkeypatch.delenv("TENDER_DETAIL_CONCURRENCY", raising=False)
    client = ConcurrentDetailClient()
    repository = AcceptingRepository()
    pipeline = TenderPipeline(
        client=client,
        repository=repository,
        llm_client=PooledAcceptingLLM(),
    )
    candidates = [
        TenderCandidate(
            title=f"环境监测服务{i}",
            url=f"https://example.test/pool/{i}",
            notice_type=NoticeType.TENDER,
        )
        for i in range(10)
    ]
    result = PipelineRunResult()

    await pipeline._process_candidates(candidates, result)

    assert client.max_active == 10
    assert result.saved_notices == 10


@pytest.mark.asyncio
async def test_candidate_processing_has_task_timeout(monkeypatch):
    monkeypatch.setenv("TENDER_DETAIL_TASK_TIMEOUT_SECONDS", "0.01")
    pipeline = TenderPipeline(
        client=HangingDetailClient(),
        repository=AcceptingRepository(),
        llm_client=AcceptingLLM(),
    )
    result = PipelineRunResult()
    candidate = TenderCandidate(
        title="污染源执法监测竞争性磋商成交候选人公示",
        url="https://example.test/hang",
        notice_type=NoticeType.WINNING_BID,
    )
    decisions = {
        candidate.normalized_url_key(): TenderFilterDecision(
            is_relevant=True,
            reason="accepted",
            confidence=0.8,
        )
    }

    await pipeline._process_candidate(candidate, decisions, result)

    assert result.detail_fetch_failures == 1
    assert result.saved_notices == 0
    assert result.errors == [
        "candidate processing timed out for https://example.test/hang after 0.01s"
    ]


@pytest.mark.asyncio
async def test_candidate_processing_defaults_task_timeout_to_240(monkeypatch):
    monkeypatch.delenv("TENDER_DETAIL_TASK_TIMEOUT_SECONDS", raising=False)
    captured = {}

    async def fake_wait_for(coro, timeout):
        captured["timeout"] = timeout
        coro.close()

    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    pipeline = TenderPipeline(
        client=ConcurrentDetailClient(),
        repository=AcceptingRepository(),
        llm_client=AcceptingLLM(),
    )
    candidate = TenderCandidate(
        title="环境监测服务采购公告",
        url="https://example.test/default-timeout",
    )

    await pipeline._process_candidate(candidate, {}, PipelineRunResult())

    assert captured["timeout"] == 240


@pytest.mark.asyncio
async def test_pipeline_stops_detail_processing_when_qianlima_access_exhausted(
    monkeypatch,
):
    monkeypatch.setenv("TENDER_DETAIL_CONCURRENCY", "1")
    client = ExhaustedDetailClient()
    repository = AcceptingRepository()
    pipeline = TenderPipeline(
        client=client,
        repository=repository,
        llm_client=AcceptingLLM(),
    )
    candidates = [
        TenderCandidate(
            title=f"环境监测服务{i}",
            url=f"https://example.test/exhausted/{i}",
            notice_type=NoticeType.TENDER,
        )
        for i in range(5)
    ]
    result = PipelineRunResult()

    await pipeline._process_candidates(candidates, result)

    assert client.calls == 1
    assert result.detail_fetch_failures == 1
    assert result.saved_notices == 0
    assert len(repository.saved_notices) == 0
    assert result.errors == [
        "detail processing stopped: 千里马全部账号详情浏览额度已耗尽"
    ]


@pytest.mark.asyncio
async def test_llm_review_extract_failure_saves_rule_extracted_fallback_notice():
    client = ConcurrentDetailClient()
    repository = AcceptingRepository()
    pipeline = TenderPipeline(
        client=client,
        repository=repository,
        llm_client=FailingExtractLLM(),
    )
    result = PipelineRunResult()
    candidate = TenderCandidate(
        title="2026年污染源执法监测竞争性磋商成交候选人公示",
        url="https://example.test/fallback",
        notice_type=NoticeType.WINNING_BID,
    )
    decisions = {
        candidate.normalized_url_key(): TenderFilterDecision(
            is_relevant=True,
            reason="accepted",
            confidence=0.8,
        )
    }

    await pipeline._process_candidate(candidate, decisions, result)

    assert result.saved_notices == 1
    assert repository.saved_notices[0].url == "https://example.test/fallback"
    assert repository.saved_notices[0].raw_content.startswith("详情")
    assert result.errors == [
        "LLM review/extract failed for https://example.test/fallback; saved fallback notice: llm review/extract unavailable"
    ]


@pytest.mark.asyncio
async def test_llm_detail_reject_updates_candidate_and_skips_notice():
    repository = AcceptingRepository()
    pipeline = TenderPipeline(
        client=ConcurrentDetailClient(),
        repository=repository,
        llm_client=RejectingDetailLLM(),
    )
    result = PipelineRunResult()
    candidate = TenderCandidate(
        title="2026年污染源执法监测竞争性磋商成交候选人公示",
        url="https://example.test/detail-reject",
        notice_type=NoticeType.WINNING_BID,
    )
    decisions = {
        candidate.normalized_url_key(): TenderFilterDecision(
            is_relevant=True,
            reason="initial accepted",
            confidence=0.8,
        )
    }

    await pipeline._process_candidate(candidate, decisions, result)

    assert result.saved_notices == 0
    assert len(repository.saved_notices) == 0
    assert result.filtered_out == 1

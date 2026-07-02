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
        return TenderFilterDecision(
            is_relevant=True,
            reason="detail keep",
            confidence=0.9,
            decision_source="llm",
        )

    async def extract_notice(self, candidate, detail_text, decision):
        return TenderNotice(
            title=candidate.title,
            url=candidate.url,
            notice_type=candidate.notice_type,
            raw_content=detail_text,
            environment_relevance=True,
        )


@pytest.mark.asyncio
async def test_pipeline_processes_relevant_details_concurrently(monkeypatch):
    monkeypatch.setenv("TENDER_DETAIL_CONCURRENCY", "3")
    client = ConcurrentDetailClient()
    repository = AcceptingRepository()
    pipeline = TenderPipeline(
        client=client,
        repository=repository,
        llm_client=AcceptingLLM(),
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

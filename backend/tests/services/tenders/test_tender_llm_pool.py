import asyncio

import pytest

from app.services.tenders.llm import TenderLLMClientPool
from app.services.tenders.models import (
    NoticeType,
    TenderCandidate,
    TenderFilterDecision,
    TenderNotice,
)


class RecordingLLM:
    def __init__(self, name, delay=0.01):
        self.name = name
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.reviewed = []
        self.extracted = []

    async def review_candidates(self, candidates, rule_decision):
        return {
            candidate.normalized_url_key(): TenderFilterDecision(
                is_relevant=True,
                reason=f"{self.name} batch keep",
                confidence=0.8,
                decision_source=self.name,
            )
            for candidate in candidates
        }

    async def review_candidate(self, candidate, rule_decision, detail_text=""):
        await self._enter()
        try:
            self.reviewed.append(candidate.url)
            return TenderFilterDecision(
                is_relevant=True,
                reason=f"{self.name} detail keep",
                confidence=0.9,
                decision_source=self.name,
            )
        finally:
            self._leave()

    async def extract_notice(self, candidate, detail_text, decision):
        await self._enter()
        try:
            self.extracted.append(candidate.url)
            return TenderNotice(
                title=candidate.title,
                url=candidate.url,
                notice_type=candidate.notice_type,
                raw_content=detail_text,
                environment_relevance=True,
            )
        finally:
            self._leave()

    async def _enter(self):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(self.delay)

    def _leave(self):
        self.active -= 1


@pytest.mark.asyncio
async def test_llm_pool_limits_each_client_concurrency():
    primary = RecordingLLM("primary")
    secondary = RecordingLLM("secondary")
    pool = TenderLLMClientPool(
        [
            (primary, 2),
            (secondary, 2),
        ]
    )
    candidates = [
        TenderCandidate(
            title=f"环境监测服务{i}",
            url=f"https://example.test/{i}",
            notice_type=NoticeType.TENDER,
        )
        for i in range(12)
    ]

    await asyncio.gather(
        *[
            pool.extract_notice(
                candidate,
                "详情正文",
                TenderFilterDecision(
                    is_relevant=True,
                    reason="detail keep",
                    confidence=0.9,
                ),
            )
            for candidate in candidates
        ]
    )

    assert primary.max_active <= 2
    assert secondary.max_active <= 2
    assert len(primary.extracted) == 6
    assert len(secondary.extracted) == 6


@pytest.mark.asyncio
async def test_llm_pool_uses_configured_screening_client_for_batch_screening():
    primary = RecordingLLM("primary")
    secondary = RecordingLLM("secondary")
    pool = TenderLLMClientPool(
        [(primary, 5), (secondary, 5)],
        screening_client_index=1,
    )
    candidates = [
        TenderCandidate(title="环境监测服务", url="https://example.test/1")
    ]

    decisions = await pool.review_candidates(
        candidates,
        TenderFilterDecision(is_relevant=True, reason="pending", confidence=0.0),
    )

    assert decisions["https://example.test/1"].decision_source == "secondary"
    assert primary.reviewed == []

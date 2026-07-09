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
        self.review_extracted = []

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

    async def review_and_extract_notice(self, candidate, detail_text, decision):
        await self._enter()
        try:
            self.review_extracted.append(candidate.url)
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


class FakeRateLimitError(Exception):
    def __init__(self, retry_after=None):
        super().__init__("429 rate limit")
        self.status_code = 429
        self.response = type(
            "Response",
            (),
            {"status_code": 429, "headers": {"retry-after": str(retry_after)} if retry_after else {}},
        )()


class RateLimitedOnceLLM:
    def __init__(self, name, retry_after=None):
        self.name = name
        self.retry_after = retry_after
        self.review_candidates_calls = 0
        self.review_extracted = []

    async def review_candidates(self, candidates, rule_decision):
        self.review_candidates_calls += 1
        raise FakeRateLimitError(self.retry_after)

    async def review_and_extract_notice(self, candidate, detail_text, decision):
        self.review_extracted.append(candidate.url)
        raise FakeRateLimitError(self.retry_after)


class HangingBatchLLM:
    def __init__(self):
        self.calls = 0
        self.stop = asyncio.Event()

    async def review_candidates(self, candidates, rule_decision):
        self.calls += 1
        await self.stop.wait()
        return {}


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
async def test_llm_pool_round_robins_combined_detail_review_and_extraction():
    primary = RecordingLLM("primary")
    secondary = RecordingLLM("secondary")
    pool = TenderLLMClientPool([(primary, 2), (secondary, 2)])
    candidates = [
        TenderCandidate(
            title=f"环境监测服务{i}",
            url=f"https://example.test/combined/{i}",
            notice_type=NoticeType.TENDER,
        )
        for i in range(8)
    ]

    await asyncio.gather(
        *[
            pool.review_and_extract_notice(
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
    assert len(primary.review_extracted) == 4
    assert len(secondary.review_extracted) == 4


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


@pytest.mark.asyncio
async def test_llm_pool_switches_to_next_client_after_rate_limit(monkeypatch):
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr("app.services.tenders.llm.asyncio.sleep", fake_sleep)
    primary = RateLimitedOnceLLM("primary", retry_after=2)
    secondary = RecordingLLM("secondary", delay=0)
    pool = TenderLLMClientPool([(primary, 1), (secondary, 1)])
    candidate = TenderCandidate(
        title="环境监测服务",
        url="https://example.test/rate-limited",
        notice_type=NoticeType.TENDER,
    )

    notice = await pool.review_and_extract_notice(
        candidate,
        "详情正文",
        TenderFilterDecision(is_relevant=True, reason="detail keep", confidence=0.9),
    )

    assert notice.url == candidate.url
    assert primary.review_extracted == [candidate.url]
    assert secondary.review_extracted == [candidate.url]
    assert sleep_calls[0] == 2.0


@pytest.mark.asyncio
async def test_llm_pool_switches_batch_screening_after_rate_limit(monkeypatch):
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr("app.services.tenders.llm.asyncio.sleep", fake_sleep)
    primary = RateLimitedOnceLLM("primary", retry_after=1)
    secondary = RecordingLLM("secondary", delay=0)
    pool = TenderLLMClientPool(
        [(primary, 1), (secondary, 1)],
        screening_client_index=0,
    )
    candidates = [
        TenderCandidate(title="环境监测服务", url="https://example.test/batch")
    ]

    decisions = await pool.review_candidates(
        candidates,
        TenderFilterDecision(is_relevant=True, reason="pending", confidence=0.0),
    )

    assert decisions["https://example.test/batch"].decision_source == "secondary"
    assert primary.review_candidates_calls == 1
    assert sleep_calls == [1.0]


@pytest.mark.asyncio
async def test_llm_pool_switches_batch_screening_after_timeout(monkeypatch):
    monkeypatch.setenv("TENDER_LLM_SCREENING_TIMEOUT_SECONDS", "0.01")
    primary = HangingBatchLLM()
    secondary = RecordingLLM("secondary", delay=0)
    pool = TenderLLMClientPool(
        [(primary, 1), (secondary, 1)],
        screening_client_index=0,
    )
    candidates = [
        TenderCandidate(title="环境监测服务", url="https://example.test/timeout")
    ]

    decisions = await pool.review_candidates(
        candidates,
        TenderFilterDecision(is_relevant=True, reason="pending", confidence=0.0),
    )

    assert decisions["https://example.test/timeout"].decision_source == "secondary"
    assert primary.calls == 1

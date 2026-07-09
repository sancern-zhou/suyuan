import pytest

from app.services.tenders.models import (
    NoticeType,
    PipelineRunResult,
    TenderCandidate,
    TenderFilterDecision,
)
from app.services.tenders.pipeline import TenderPipeline


class RecordingRepository:
    def __init__(self):
        self.decisions = {}

    async def save_candidate(self, candidate, decision=None):
        return True

    async def update_candidate_decision(self, candidate, decision):
        self.decisions[candidate.url] = decision

    async def save_notice(self, notice):
        raise AssertionError("save_notice should not be reached in this test")


class DecisionOrderingRepository:
    def __init__(self):
        self.decisions = {}

    async def save_candidate(self, candidate, decision=None):
        return True

    async def update_candidate_decision(self, candidate, decision):
        self.decisions[candidate.url] = decision

    async def save_notice(self, notice):
        pass


class BatchOnlyLLM:
    async def review_candidates(self, candidates, rule_decision):
        return {
            candidates[0].normalized_url_key(): TenderFilterDecision(
                is_relevant=True,
                reason="LLM初筛命中环境业务公告",
                confidence=0.8,
                decision_source="llm",
            )
        }

    async def review_candidate(self, candidate, rule_decision, detail_text=""):
        raise AssertionError("omitted batch candidates must not be reviewed one by one")


class ConcurrentBatchLLM:
    def __init__(self):
        self.active = 0
        self.max_active = 0

    async def review_candidates(self, candidates, rule_decision):
        import asyncio

        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return {
            candidate.normalized_url_key(): TenderFilterDecision(
                is_relevant=True,
                reason="LLM初筛命中环境业务公告",
                confidence=0.8,
                decision_source="llm",
            )
            for candidate in candidates
        }


class CancellationResistantLLM:
    def __init__(self):
        self.stop = None

    async def review_candidates(self, candidates, rule_decision):
        import asyncio

        if self.stop is None:
            self.stop = asyncio.Event()
        while not self.stop.is_set():
            try:
                await self.stop.wait()
            except asyncio.CancelledError:
                await self.stop.wait()
                return {}


class TimeoutAwarePoolLLM:
    handles_screening_timeouts = True

    def __init__(self):
        self.calls = 0

    @property
    def screening_entry_count(self):
        return 2

    async def review_candidates(self, candidates, rule_decision):
        import asyncio

        self.calls += 1
        await asyncio.sleep(0.015)
        return {
            candidate.normalized_url_key(): TenderFilterDecision(
                is_relevant=True,
                reason="fallback model keep",
                confidence=0.8,
                decision_source="llm",
            )
            for candidate in candidates
        }


class SingleAcceptedLLM:
    async def review_candidates(self, candidates, rule_decision):
        return {
            candidates[0].normalized_url_key(): TenderFilterDecision(
                is_relevant=True,
                reason="LLM初筛命中环境业务公告",
                confidence=0.8,
                decision_source="llm",
            )
        }

    async def review_candidate(self, candidate, rule_decision, detail_text=""):
        return rule_decision

    async def extract_notice(self, candidate, detail_text, decision):
        from app.services.tenders.models import TenderNotice

        return TenderNotice(
            title=candidate.title,
            url=candidate.url,
            notice_type=candidate.notice_type,
            raw_content=detail_text,
            environment_relevance=True,
        )


class DecisionAwareDetailClient:
    def __init__(self, repository, expected_decisions):
        self.repository = repository
        self.expected_decisions = expected_decisions

    async def fetch_detail(self, candidate):
        assert len(self.repository.decisions) == self.expected_decisions
        return "详情正文"


class NoticeTypeAgnosticSearchClient:
    search_ignores_notice_type = True

    def __init__(self):
        self.search_calls = []

    async def search(self, keyword, notice_type, publish_date=None, max_pages=1):
        self.search_calls.append((keyword, notice_type, publish_date, max_pages))
        return []


@pytest.mark.asyncio
async def test_notice_type_agnostic_client_searches_each_keyword_once():
    client = NoticeTypeAgnosticSearchClient()
    pipeline = TenderPipeline(
        client=client,
        repository=RecordingRepository(),
        llm_client=BatchOnlyLLM(),
    )

    await pipeline.run_daily(
        keywords=["生态环境局"],
        notice_types=[NoticeType.TENDER, NoticeType.WINNING_BID],
        publish_date=__import__("datetime").date(2026, 7, 3),
        max_pages=0,
    )

    assert client.search_calls == [
        ("生态环境局", NoticeType.OTHER, __import__("datetime").date(2026, 7, 3), 0)
    ]


@pytest.mark.asyncio
async def test_batch_screening_omissions_are_rejected_without_single_llm_review():
    repository = RecordingRepository()
    pipeline = TenderPipeline(
        client=object(),
        repository=repository,
        llm_client=BatchOnlyLLM(),
    )
    candidates = [
        TenderCandidate(
            title="环境监测服务采购公告",
            url="https://example.test/keep",
            notice_type=NoticeType.TENDER,
        ),
        TenderCandidate(
            title="办公用品采购公告",
            url="https://example.test/reject",
            notice_type=NoticeType.TENDER,
        ),
    ]
    result = PipelineRunResult()

    await pipeline._process_candidates(candidates, result)

    assert repository.decisions["https://example.test/reject"].is_relevant is False
    assert repository.decisions["https://example.test/reject"].reason in {
        "LLM初筛未命中环境业务公告",
        "规则预过滤: 办公、耗材或通用实验耗材采购，非环境业务主体项目",
    }
    assert result.filtered_out == 1


@pytest.mark.asyncio
async def test_initial_screening_reviews_batches_concurrently(monkeypatch):
    monkeypatch.setenv("TENDER_LLM_BATCH_SIZE", "10")
    monkeypatch.setenv("TENDER_LLM_SCREENING_CONCURRENCY", "3")
    llm = ConcurrentBatchLLM()
    pipeline = TenderPipeline(
        client=object(),
        repository=RecordingRepository(),
        llm_client=llm,
    )
    candidates = [
        TenderCandidate(
            title=f"环境监测服务采购公告{i}",
            url=f"https://example.test/{i}",
            notice_type=NoticeType.TENDER,
        )
        for i in range(30)
    ]

    decisions = await pipeline._initial_decisions(candidates, PipelineRunResult())

    assert len(decisions) == len(candidates)
    assert llm.max_active > 1


@pytest.mark.asyncio
async def test_initial_screening_timeout_does_not_wait_for_cancelled_llm(monkeypatch):
    monkeypatch.setenv("TENDER_LLM_BATCH_SIZE", "2")
    monkeypatch.setenv("TENDER_LLM_SCREENING_CONCURRENCY", "1")
    monkeypatch.setenv("TENDER_LLM_SCREENING_TIMEOUT_SECONDS", "0.01")
    llm = CancellationResistantLLM()
    pipeline = TenderPipeline(
        client=object(),
        repository=RecordingRepository(),
        llm_client=llm,
    )
    candidates = [
        TenderCandidate(
            title=f"环境监测服务采购公告{i}",
            url=f"https://example.test/timeout-{i}",
            notice_type=NoticeType.TENDER,
        )
        for i in range(2)
    ]
    result = PipelineRunResult()

    decisions = await pipeline._initial_decisions(candidates, result)
    llm.stop.set()
    await __import__("asyncio").sleep(0.01)

    assert len(decisions) == len(candidates)
    assert {decision.decision_source for decision in decisions.values()} == {
        "llm_error"
    }
    assert result.errors


@pytest.mark.asyncio
async def test_initial_screening_extends_timeout_for_pool_failover(monkeypatch):
    monkeypatch.setenv("TENDER_LLM_BATCH_SIZE", "2")
    monkeypatch.setenv("TENDER_LLM_SCREENING_CONCURRENCY", "1")
    monkeypatch.setenv("TENDER_LLM_SCREENING_TIMEOUT_SECONDS", "0.01")
    llm = TimeoutAwarePoolLLM()
    pipeline = TenderPipeline(
        client=object(),
        repository=RecordingRepository(),
        llm_client=llm,
    )
    candidates = [
        TenderCandidate(
            title="环境监测服务采购公告",
            url="https://example.test/pool-timeout",
            notice_type=NoticeType.TENDER,
        )
    ]

    decisions = await pipeline._initial_decisions(candidates, PipelineRunResult())

    assert decisions["https://example.test/pool-timeout"].is_relevant is True
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_pipeline_persists_all_initial_decisions_before_fetching_details():
    repository = DecisionOrderingRepository()
    candidates = [
        TenderCandidate(
            title="环境监测服务采购公告",
            url="https://example.test/keep",
            notice_type=NoticeType.TENDER,
        ),
        TenderCandidate(
            title="生态环境局车辆维修服务结果公告",
            url="https://example.test/reject-1",
            notice_type=NoticeType.TENDER,
        ),
        TenderCandidate(
            title="生态环境局复印纸采购合同公告",
            url="https://example.test/reject-2",
            notice_type=NoticeType.TENDER,
        ),
    ]
    pipeline = TenderPipeline(
        client=DecisionAwareDetailClient(repository, expected_decisions=len(candidates)),
        repository=repository,
        llm_client=SingleAcceptedLLM(),
    )
    result = PipelineRunResult()

    await pipeline._process_candidates(candidates, result)

    assert len(repository.decisions) == len(candidates)
    assert result.filtered_out == 2
    assert result.saved_notices == 1

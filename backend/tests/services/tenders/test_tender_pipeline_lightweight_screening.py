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

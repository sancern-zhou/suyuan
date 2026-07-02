import pytest

from app.services.tenders.filters import TenderRelevanceFilter
from app.services.tenders.models import NoticeType, PipelineRunResult, TenderCandidate
from app.services.tenders.pipeline import TenderPipeline


class RecordingRepository:
    def __init__(self):
        self.saved = []
        self.decisions = {}

    async def save_candidate(self, candidate, decision=None):
        self.saved.append(candidate)
        return True

    async def update_candidate_decision(self, candidate, decision):
        self.decisions[candidate.url] = decision

    async def save_notice(self, notice):
        raise AssertionError("prefiltered candidates should not reach notice saving")


class FailingBatchLLM:
    async def review_candidates(self, candidates, rule_decision):
        raise AssertionError("prefiltered or duplicate candidates should not call LLM")

    async def review_candidate(self, candidate, rule_decision, detail_text=""):
        raise AssertionError("prefiltered candidates should not call detail review")


def test_prefilter_rejects_real_noise_patterns_before_llm():
    relevance_filter = TenderRelevanceFilter()
    titles = [
        "东莞市小铸金属制品有限公司 建设项目环境影响报告表审批",
        "邵阳市生态环境局邵东分局关于其他环境治理服务的网上超市采购项目合同履约验收公告",
        "北京市顺义区生态环境局关于招募顺义区危险废物绿色低碳发展路径建设招标代理公司的公告",
        "鹤壁市生态环境局鹤壁市大气污染防治专项督导车辆保障服务项目三次招标-废标公告",
        "“环保设施设备安全生产工作资料汇编”手册印刷项目",
        "湖南湘江新区管理委员会农业农村和生态环境局2026年07月 至 2026年08月政府采购意向",
    ]

    for title in titles:
        decision = relevance_filter.prefilter_decision(
            TenderCandidate(title=title, url=f"https://example.test/{title}")
        )
        assert decision is not None, title
        assert decision.is_relevant is False


@pytest.mark.asyncio
async def test_pipeline_prefilters_noise_without_llm():
    repository = RecordingRepository()
    pipeline = TenderPipeline(
        client=object(),
        repository=repository,
        llm_client=FailingBatchLLM(),
    )
    candidates = [
        TenderCandidate(
            title="邵阳市生态环境局邵东分局关于工程设计服务的网上超市采购项目合同履约验收公告",
            url="https://example.test/rejected",
            notice_type=NoticeType.TENDER,
        )
    ]
    result = PipelineRunResult()

    await pipeline._process_candidates(candidates, result)

    assert repository.decisions["https://example.test/rejected"].is_relevant is False
    assert "规则预过滤" in repository.decisions["https://example.test/rejected"].reason
    assert result.filtered_out == 1


@pytest.mark.asyncio
async def test_pipeline_deduplicates_candidates_by_normalized_title():
    repository = RecordingRepository()
    pipeline = TenderPipeline(
        client=object(),
        repository=repository,
        llm_client=FailingBatchLLM(),
    )
    title = "关于为【赣州市上犹生态环境局】公开选取【环境影响评价文件技术评估】机构的公告"
    candidates = [
        TenderCandidate(title=title, url="https://example.test/1"),
        TenderCandidate(title=title, url="https://example.test/2"),
    ]
    result = PipelineRunResult()

    await pipeline._process_candidates(candidates, result)

    assert len(repository.saved) == 1
    assert result.duplicate_candidates == 1

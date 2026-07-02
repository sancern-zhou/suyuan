from datetime import date

import pytest

from scripts.run_qianlima_tender_workflow import (
    collect_candidates,
    split_keywords,
    workflow_stats,
)
from src.tenders.models import (
    NoticeType,
    TenderCandidate,
    TenderFilterDecision,
    TenderNotice,
)
from src.tenders.repository import SQLiteTenderRepository


class FakeCollectClient:
    async def search(self, keyword, notice_type, publish_date=None, max_pages=1):
        return [
            TenderCandidate(
                title=f"{keyword}环境监测能力建设项目采购公告",
                url=f"https://example.test/{keyword}/1",
                notice_type=notice_type,
                keyword=keyword,
                publish_date=publish_date,
            ),
            TenderCandidate(
                title=f"{keyword}环境监测能力建设项目采购公告",
                url=f"https://example.test/{keyword}/1",
                notice_type=notice_type,
                keyword=keyword,
                publish_date=publish_date,
            ),
        ]


def make_decision(is_relevant: bool = True) -> TenderFilterDecision:
    return TenderFilterDecision(
        is_relevant=is_relevant,
        reason="LLM 判断结果",
        confidence=0.9,
        decision_source="llm",
    )


def test_split_keywords_trims_empty_values():
    assert split_keywords("生态环境局, 环保局, ,") == ["生态环境局", "环保局"]


@pytest.mark.asyncio
async def test_collect_candidates_saves_new_rows_and_counts_duplicates(tmp_path):
    repository = SQLiteTenderRepository(str(tmp_path / "tenders.db"))

    result = await collect_candidates(
        client=FakeCollectClient(),
        repository=repository,
        keywords=["生态环境局"],
        notice_types=[NoticeType.TENDER],
        publish_date=date(2026, 6, 30),
        max_pages=0,
    )

    assert result.total_found == 2
    assert result.saved == 1
    assert result.duplicates == 1
    assert workflow_stats(repository.db_path)["candidates"] == 1


@pytest.mark.asyncio
async def test_workflow_stats_reports_final_counts(tmp_path):
    db_path = str(tmp_path / "tenders.db")
    repository = SQLiteTenderRepository(db_path)
    accepted = TenderCandidate(
        title="生态环境分区管控技术评估项目采购公告",
        url="https://example.test/accepted",
        notice_type=NoticeType.TENDER,
        keyword="生态环境局",
        publish_date=date(2026, 6, 30),
    )
    rejected = TenderCandidate(
        title="生态环境局车辆租赁服务采购公告",
        url="https://example.test/rejected",
        notice_type=NoticeType.TENDER,
        keyword="生态环境局",
        publish_date=date(2026, 6, 30),
    )

    await repository.save_candidate(accepted, make_decision(True))
    await repository.save_candidate(rejected, make_decision(False))
    await repository.save_notice(
        TenderNotice(
            title=accepted.title,
            url=accepted.url,
            notice_type=accepted.notice_type,
            raw_content="项目内容：开展生态环境分区管控技术评估。",
            publish_date=accepted.publish_date,
            environment_relevance=True,
        )
    )

    stats = workflow_stats(db_path)

    assert stats["candidates"] == 2
    assert stats["status"] == {"accepted": 1, "rejected": 1}
    assert stats["notices"] == 1
    assert stats["accepted_missing"] == 0
    assert stats["rejected_notice_remaining"] == 0
    assert stats["publish_dates"] == {"2026-06-30": 1}


def test_workflow_stats_handles_missing_database(tmp_path):
    stats = workflow_stats(str(tmp_path / "missing.db"))

    assert stats["exists"] is False
    assert stats["candidates"] == 0
    assert stats["notices"] == 0

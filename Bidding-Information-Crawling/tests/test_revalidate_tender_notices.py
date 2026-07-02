import sqlite3
from datetime import date

import pytest

from scripts.revalidate_tender_notices import (
    delete_notice,
    load_review_items,
    parse_date,
    parse_json,
    parse_notice_type,
)
from src.tenders.models import (
    NoticeType,
    TenderCandidate,
    TenderFilterDecision,
    TenderNotice,
)
from src.tenders.repository import SQLiteTenderRepository


def make_candidate(title: str, url: str) -> TenderCandidate:
    return TenderCandidate(
        title=title,
        url=url,
        notice_type=NoticeType.TENDER,
        keyword="生态环境局",
        publish_date=date(2026, 6, 30),
        raw_list_text=title,
        metadata={"area_name": "江苏-南京"},
    )


def make_decision() -> TenderFilterDecision:
    return TenderFilterDecision(
        is_relevant=True,
        reason="LLM 初筛判定为环境业务项目",
        confidence=0.9,
        decision_source="llm",
    )


@pytest.mark.asyncio
async def test_load_review_items_restores_notice_detail_context(tmp_path):
    db_path = str(tmp_path / "tenders.db")
    repository = SQLiteTenderRepository(db_path)
    candidate = make_candidate(
        "生态环境分区管控技术评估项目采购公告", "https://example.test/1"
    )
    decision = make_decision()
    raw_content = "项目内容：开展生态环境分区管控方案五年定期评估。"

    await repository.save_candidate(candidate, decision)
    await repository.save_notice(
        TenderNotice(
            title=candidate.title,
            url=candidate.url,
            notice_type=candidate.notice_type,
            raw_content=raw_content,
            publish_date=candidate.publish_date,
            environment_relevance=True,
        )
    )

    items = load_review_items(db_path)

    assert len(items) == 1
    assert items[0].candidate.url == candidate.url
    assert items[0].candidate.metadata["area_name"] == "江苏-南京"
    assert items[0].prior_decision.decision_source == "llm"
    assert items[0].raw_content == raw_content


@pytest.mark.asyncio
async def test_delete_notice_keeps_candidate_for_rejection_audit(tmp_path):
    db_path = str(tmp_path / "tenders.db")
    repository = SQLiteTenderRepository(db_path)
    candidate = make_candidate(
        "生态环境局物业管理服务采购公告", "https://example.test/2"
    )

    await repository.save_candidate(candidate, make_decision())
    await repository.save_notice(
        TenderNotice(
            title=candidate.title,
            url=candidate.url,
            notice_type=candidate.notice_type,
            raw_content="项目内容：物业管理服务。",
            publish_date=candidate.publish_date,
            environment_relevance=True,
        )
    )

    delete_notice(db_path, candidate.url)

    with sqlite3.connect(db_path) as conn:
        candidate_count = conn.execute(
            "SELECT COUNT(*) FROM tender_candidates"
        ).fetchone()[0]
        notice_count = conn.execute("SELECT COUNT(*) FROM tender_notices").fetchone()[0]

    assert candidate_count == 1
    assert notice_count == 0


def test_revalidate_helpers_tolerate_invalid_values():
    assert parse_notice_type("bad") == NoticeType.OTHER
    assert parse_date("bad-date") is None
    assert parse_json("{bad json") == {}

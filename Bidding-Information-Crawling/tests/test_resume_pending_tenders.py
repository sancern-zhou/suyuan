import sqlite3
from datetime import date

import pytest

from scripts.resume_pending_tenders import (
    candidate_from_row,
    load_accepted_missing_candidates,
    load_pending_candidates,
    parse_date,
    parse_json,
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
        metadata={"area_name": "广东-东莞"},
    )


def make_decision() -> TenderFilterDecision:
    return TenderFilterDecision(
        is_relevant=True,
        reason="LLM 判断为环境业务项目",
        confidence=0.91,
        decision_source="llm",
    )


@pytest.mark.asyncio
async def test_load_pending_candidates_restores_candidate_fields(tmp_path):
    db_path = str(tmp_path / "tenders.db")
    repository = SQLiteTenderRepository(db_path)
    candidate = make_candidate(
        "东莞市生态环境监测项目采购公告", "https://example.test/1"
    )

    await repository.save_candidate(candidate)

    pending = load_pending_candidates(db_path)

    assert len(pending) == 1
    assert pending[0].title == candidate.title
    assert pending[0].publish_date == date(2026, 6, 30)
    assert pending[0].metadata["area_name"] == "广东-东莞"


@pytest.mark.asyncio
async def test_load_accepted_missing_candidates_excludes_existing_notice(tmp_path):
    db_path = str(tmp_path / "tenders.db")
    repository = SQLiteTenderRepository(db_path)
    missing = make_candidate(
        "生态环境执法能力建设项目采购公告", "https://example.test/missing"
    )
    stored = make_candidate(
        "水质自动监测站运维项目采购公告", "https://example.test/stored"
    )
    decision = make_decision()

    await repository.save_candidate(missing, decision)
    await repository.save_candidate(stored, decision)
    await repository.save_notice(
        TenderNotice(
            title=stored.title,
            url=stored.url,
            notice_type=stored.notice_type,
            raw_content="项目内容：水质自动监测站运维。",
            publish_date=stored.publish_date,
            environment_relevance=True,
        )
    )

    accepted_missing = load_accepted_missing_candidates(db_path)

    assert len(accepted_missing) == 1
    assert accepted_missing[0][0].url == missing.url
    assert accepted_missing[0][1].decision_source == "llm"


def test_resume_helpers_tolerate_invalid_source_values():
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT
                '坏类型公告' AS title,
                'https://example.test/bad' AS url,
                'unknown' AS notice_type,
                NULL AS keyword,
                NULL AS source,
                'not-a-date' AS publish_date,
                NULL AS raw_list_text,
                '{bad json' AS metadata
            """).fetchone()

    candidate = candidate_from_row(row)

    assert parse_date("bad") is None
    assert parse_json("{bad") == {}
    assert candidate.notice_type == NoticeType.OTHER
    assert candidate.publish_date is None
    assert candidate.metadata == {}

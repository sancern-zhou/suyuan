from __future__ import annotations

import json
import os
import sqlite3
from typing import Dict, List, Optional

from .models import TenderCandidate, TenderFilterDecision, TenderNotice


class InMemoryTenderRepository:
    def __init__(self):
        self.candidates: Dict[
            str, tuple[TenderCandidate, Optional[TenderFilterDecision]]
        ] = {}
        self.notices: List[TenderNotice] = []

    async def candidate_exists(self, url: str) -> bool:
        return url.strip().lower() in self.candidates

    async def save_candidate(
        self, candidate: TenderCandidate, decision: TenderFilterDecision | None = None
    ) -> bool:
        key = candidate.normalized_url_key()
        if key in self.candidates:
            return False
        self.candidates[key] = (candidate, decision)
        return True

    async def update_candidate_decision(
        self, candidate: TenderCandidate, decision: TenderFilterDecision
    ) -> None:
        self.candidates[candidate.normalized_url_key()] = (candidate, decision)

    async def save_notice(self, notice: TenderNotice) -> None:
        self.notices.append(notice)


class AsyncpgTenderRepository:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.getenv("TENDER_DATABASE_DSN") or os.getenv("DATABASE_URL")
        if not self.dsn:
            raise RuntimeError("TENDER_DATABASE_DSN or DATABASE_URL must be set")

    async def _connect(self):
        import asyncpg

        return await asyncpg.connect(self.dsn)

    async def candidate_exists(self, url: str) -> bool:
        conn = await self._connect()
        try:
            row = await conn.fetchrow(
                "SELECT 1 FROM tender_candidates WHERE url = $1", url
            )
            return row is not None
        finally:
            await conn.close()

    async def save_candidate(
        self, candidate: TenderCandidate, decision: TenderFilterDecision | None = None
    ) -> bool:
        conn = await self._connect()
        try:
            result = await conn.execute(
                """
                INSERT INTO tender_candidates (
                    title, url, notice_type, keyword, source, publish_date, raw_list_text, metadata,
                    filter_status, filter_reason, filter_confidence, decision_source
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10,$11,$12)
                ON CONFLICT (url) DO NOTHING
                """,
                candidate.title,
                candidate.url,
                candidate.notice_type.value,
                candidate.keyword,
                candidate.source,
                candidate.publish_date,
                candidate.raw_list_text,
                json.dumps(candidate.metadata, ensure_ascii=False),
                self._status_from_decision(decision),
                decision.reason if decision else None,
                decision.confidence if decision else None,
                decision.decision_source if decision else None,
            )
            return result.endswith("1")
        finally:
            await conn.close()

    async def update_candidate_decision(
        self, candidate: TenderCandidate, decision: TenderFilterDecision
    ) -> None:
        conn = await self._connect()
        try:
            await conn.execute(
                """
                UPDATE tender_candidates
                SET filter_status=$2, filter_reason=$3, filter_confidence=$4, decision_source=$5, updated_at=now()
                WHERE url=$1
                """,
                candidate.url,
                self._status_from_decision(decision),
                decision.reason,
                decision.confidence,
                decision.decision_source,
            )
        finally:
            await conn.close()

    async def save_notice(self, notice: TenderNotice) -> None:
        conn = await self._connect()
        try:
            await conn.execute(
                """
                INSERT INTO tender_notices (
                    title, url, notice_type, project_name, purchaser, agency, winning_bidder,
                    budget_amount, budget_amount_wan_yuan, winning_amount, winning_amount_wan_yuan,
                    province, city, publish_date, bid_open_date, deadline, industry_category,
                    environment_relevance, filter_reason, filter_confidence, raw_content, summary,
                    key_requirements, attachment_urls, structured_json
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23::jsonb,$24::jsonb,$25::jsonb)
                ON CONFLICT (url) DO UPDATE SET
                    title=EXCLUDED.title,
                    project_name=EXCLUDED.project_name,
                    purchaser=EXCLUDED.purchaser,
                    agency=EXCLUDED.agency,
                    winning_bidder=EXCLUDED.winning_bidder,
                    budget_amount=EXCLUDED.budget_amount,
                    budget_amount_wan_yuan=EXCLUDED.budget_amount_wan_yuan,
                    winning_amount=EXCLUDED.winning_amount,
                    winning_amount_wan_yuan=EXCLUDED.winning_amount_wan_yuan,
                    raw_content=EXCLUDED.raw_content,
                    summary=EXCLUDED.summary,
                    key_requirements=EXCLUDED.key_requirements,
                    attachment_urls=EXCLUDED.attachment_urls,
                    structured_json=EXCLUDED.structured_json,
                    updated_at=now()
                """,
                notice.title,
                notice.url,
                notice.notice_type.value,
                notice.project_name,
                notice.purchaser,
                notice.agency,
                notice.winning_bidder,
                notice.budget_amount,
                notice.budget_amount_wan_yuan,
                notice.winning_amount,
                notice.winning_amount_wan_yuan,
                notice.province,
                notice.city,
                notice.publish_date,
                notice.bid_open_date,
                notice.deadline,
                notice.industry_category,
                notice.environment_relevance,
                notice.filter_reason,
                notice.filter_confidence,
                notice.raw_content,
                notice.summary,
                json.dumps(notice.key_requirements, ensure_ascii=False),
                json.dumps(notice.attachment_urls, ensure_ascii=False),
                json.dumps(notice.structured_json, ensure_ascii=False, default=str),
            )
        finally:
            await conn.close()

    def _status_from_decision(self, decision: TenderFilterDecision | None) -> str:
        if decision is None:
            return "pending"
        return "accepted" if decision.is_relevant else "rejected"


class SQLiteTenderRepository:
    def __init__(self, db_path: str = "data/tenders.db"):
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tender_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    notice_type TEXT NOT NULL,
                    keyword TEXT,
                    source TEXT NOT NULL DEFAULT 'qianlima',
                    publish_date TEXT,
                    raw_list_text TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    filter_status TEXT NOT NULL DEFAULT 'pending',
                    filter_reason TEXT,
                    filter_confidence REAL,
                    decision_source TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tender_notices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    notice_type TEXT NOT NULL,
                    project_name TEXT,
                    purchaser TEXT,
                    agency TEXT,
                    winning_bidder TEXT,
                    budget_amount TEXT,
                    budget_amount_wan_yuan REAL,
                    winning_amount TEXT,
                    winning_amount_wan_yuan REAL,
                    province TEXT,
                    city TEXT,
                    publish_date TEXT,
                    bid_open_date TEXT,
                    deadline TEXT,
                    industry_category TEXT,
                    environment_relevance INTEGER NOT NULL DEFAULT 0,
                    filter_reason TEXT,
                    filter_confidence REAL,
                    raw_content TEXT NOT NULL,
                    summary TEXT,
                    key_requirements TEXT NOT NULL DEFAULT '[]',
                    attachment_urls TEXT NOT NULL DEFAULT '[]',
                    structured_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_sqlite_tender_candidates_status ON tender_candidates(filter_status);
                CREATE INDEX IF NOT EXISTS idx_sqlite_tender_candidates_keyword ON tender_candidates(keyword);
                CREATE INDEX IF NOT EXISTS idx_sqlite_tender_notices_publish_date ON tender_notices(publish_date);
                CREATE INDEX IF NOT EXISTS idx_sqlite_tender_notices_purchaser ON tender_notices(purchaser);
                """)

    async def candidate_exists(self, url: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM tender_candidates WHERE url = ?", (url,)
            ).fetchone()
            return row is not None

    async def save_candidate(
        self, candidate: TenderCandidate, decision: TenderFilterDecision | None = None
    ) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO tender_candidates (
                    title, url, notice_type, keyword, source, publish_date, raw_list_text, metadata,
                    filter_status, filter_reason, filter_confidence, decision_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.title,
                    candidate.url,
                    candidate.notice_type.value,
                    candidate.keyword,
                    candidate.source,
                    (
                        candidate.publish_date.isoformat()
                        if candidate.publish_date
                        else None
                    ),
                    candidate.raw_list_text,
                    json.dumps(candidate.metadata, ensure_ascii=False),
                    self._status_from_decision(decision),
                    decision.reason if decision else None,
                    decision.confidence if decision else None,
                    decision.decision_source if decision else None,
                ),
            )
            return cursor.rowcount == 1

    async def update_candidate_decision(
        self, candidate: TenderCandidate, decision: TenderFilterDecision
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tender_candidates
                SET filter_status = ?, filter_reason = ?, filter_confidence = ?, decision_source = ?, updated_at = CURRENT_TIMESTAMP
                WHERE url = ?
                """,
                (
                    self._status_from_decision(decision),
                    decision.reason,
                    decision.confidence,
                    decision.decision_source,
                    candidate.url,
                ),
            )

    async def save_notice(self, notice: TenderNotice) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tender_notices (
                    title, url, notice_type, project_name, purchaser, agency, winning_bidder,
                    budget_amount, budget_amount_wan_yuan, winning_amount, winning_amount_wan_yuan,
                    province, city, publish_date, bid_open_date, deadline, industry_category,
                    environment_relevance, filter_reason, filter_confidence, raw_content, summary,
                    key_requirements, attachment_urls, structured_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    project_name = excluded.project_name,
                    purchaser = excluded.purchaser,
                    agency = excluded.agency,
                    winning_bidder = excluded.winning_bidder,
                    budget_amount = excluded.budget_amount,
                    budget_amount_wan_yuan = excluded.budget_amount_wan_yuan,
                    winning_amount = excluded.winning_amount,
                    winning_amount_wan_yuan = excluded.winning_amount_wan_yuan,
                    raw_content = excluded.raw_content,
                    summary = excluded.summary,
                    key_requirements = excluded.key_requirements,
                    attachment_urls = excluded.attachment_urls,
                    structured_json = excluded.structured_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    notice.title,
                    notice.url,
                    notice.notice_type.value,
                    notice.project_name,
                    notice.purchaser,
                    notice.agency,
                    notice.winning_bidder,
                    notice.budget_amount,
                    notice.budget_amount_wan_yuan,
                    notice.winning_amount,
                    notice.winning_amount_wan_yuan,
                    notice.province,
                    notice.city,
                    notice.publish_date.isoformat() if notice.publish_date else None,
                    notice.bid_open_date,
                    notice.deadline,
                    notice.industry_category,
                    1 if notice.environment_relevance else 0,
                    notice.filter_reason,
                    notice.filter_confidence,
                    notice.raw_content,
                    notice.summary,
                    json.dumps(notice.key_requirements, ensure_ascii=False),
                    json.dumps(notice.attachment_urls, ensure_ascii=False),
                    json.dumps(notice.structured_json, ensure_ascii=False, default=str),
                ),
            )

    def _status_from_decision(self, decision: TenderFilterDecision | None) -> str:
        if decision is None:
            return "pending"
        return "accepted" if decision.is_relevant else "rejected"

from __future__ import annotations

import json
from datetime import date
from typing import Sequence

import pyodbc

from config.settings import settings
from app.services.tenders.models import (
    NoticeType,
    PipelineRunResult,
    TenderCandidate,
    TenderFilterDecision,
    TenderNotice,
)


class SQLServerTenderRepository:
    def __init__(self, connection_string: str | None = None):
        self.connection_string = connection_string or settings.sqlserver_connection_string

    def _connect(self):
        return pyodbc.connect(self.connection_string, timeout=30)

    async def candidate_exists(self, url: str) -> bool:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM tender_candidates WHERE url = ?",
                url,
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()

    async def save_candidate(
        self, candidate: TenderCandidate, decision: TenderFilterDecision | None = None
    ) -> bool:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tender_candidates (
                    title, url, notice_type, keyword, source, publish_date,
                    raw_list_text, metadata_json, filter_status, filter_reason,
                    filter_confidence, decision_source
                )
                SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM tender_candidates WHERE url = ?
                )
                """,
                (
                    candidate.title,
                    candidate.url,
                    candidate.notice_type.value,
                    candidate.keyword,
                    candidate.source,
                    candidate.publish_date,
                    candidate.raw_list_text,
                    json.dumps(candidate.metadata, ensure_ascii=False, default=str),
                    self._status_from_decision(decision),
                    decision.reason if decision else None,
                    decision.confidence if decision else None,
                    decision.decision_source if decision else None,
                    candidate.url,
                ),
            )
            conn.commit()
            return cursor.rowcount == 1
        finally:
            conn.close()

    async def update_candidate_decision(
        self, candidate: TenderCandidate, decision: TenderFilterDecision
    ) -> None:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tender_candidates
                SET filter_status = ?,
                    filter_reason = ?,
                    filter_confidence = ?,
                    decision_source = ?,
                    updated_at = sysdatetime()
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
            conn.commit()
        finally:
            conn.close()

    async def save_notice(self, notice: TenderNotice) -> None:
        values = self._notice_values(notice)
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tender_notices
                SET title = ?,
                    notice_type = ?,
                    project_name = ?,
                    purchaser = ?,
                    agency = ?,
                    winning_bidder = ?,
                    budget_amount = ?,
                    budget_amount_wan_yuan = ?,
                    winning_amount = ?,
                    winning_amount_wan_yuan = ?,
                    province = ?,
                    city = ?,
                    publish_date = ?,
                    bid_open_date = ?,
                    deadline = ?,
                    industry_category = ?,
                    environment_relevance = ?,
                    filter_reason = ?,
                    filter_confidence = ?,
                    raw_content = ?,
                    summary = ?,
                    key_requirements_json = ?,
                    attachment_urls_json = ?,
                    structured_json = ?,
                    updated_at = sysdatetime()
                WHERE url = ?
                """,
                values[0:1] + values[2:] + (notice.url,),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    INSERT INTO tender_notices (
                        title, url, notice_type, project_name, purchaser, agency,
                        winning_bidder, budget_amount, budget_amount_wan_yuan,
                        winning_amount, winning_amount_wan_yuan, province, city,
                        publish_date, bid_open_date, deadline, industry_category,
                        environment_relevance, filter_reason, filter_confidence,
                        raw_content, summary, key_requirements_json,
                        attachment_urls_json, structured_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
            conn.commit()
        finally:
            conn.close()

    async def create_run(
        self,
        target_date: date,
        keywords: Sequence[str],
        notice_types: Sequence[NoticeType],
    ) -> int:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tender_fetch_runs (
                    target_date, keywords_json, notice_types_json, status
                )
                OUTPUT INSERTED.id
                VALUES (?, ?, ?, ?)
                """,
                (
                    target_date,
                    json.dumps(list(keywords), ensure_ascii=False),
                    json.dumps([item.value for item in notice_types], ensure_ascii=False),
                    "running",
                ),
            )
            row = cursor.fetchone()
            conn.commit()
            return int(row[0])
        finally:
            conn.close()

    async def finish_run(self, run_id: int, result: PipelineRunResult) -> None:
        status = "success"
        if result.errors:
            status = "partial_failed" if result.saved_notices else "failed"
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tender_fetch_runs
                SET total_candidates = ?,
                    duplicate_candidates = ?,
                    filtered_out = ?,
                    detail_fetch_failures = ?,
                    saved_notices = ?,
                    errors_json = ?,
                    status = ?,
                    finished_at = sysdatetime()
                WHERE id = ?
                """,
                (
                    result.total_candidates,
                    result.duplicate_candidates,
                    result.filtered_out,
                    result.detail_fetch_failures,
                    result.saved_notices,
                    json.dumps(result.errors, ensure_ascii=False),
                    status,
                    run_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _notice_values(self, notice: TenderNotice) -> tuple:
        return (
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
            1 if notice.environment_relevance else 0,
            notice.filter_reason,
            notice.filter_confidence,
            notice.raw_content,
            notice.summary,
            json.dumps(notice.key_requirements, ensure_ascii=False),
            json.dumps(notice.attachment_urls, ensure_ascii=False),
            json.dumps(notice.structured_json, ensure_ascii=False, default=str),
        )

    def _status_from_decision(self, decision: TenderFilterDecision | None) -> str:
        if decision is None:
            return "pending"
        return "accepted" if decision.is_relevant else "rejected"

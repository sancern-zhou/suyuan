from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable, Sequence

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
    _AMOUNT_TEXT_MAX_LENGTH = 100
    _AMOUNT_DECIMAL_MAX_ABS = Decimal("100000000000000")

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

    async def save_candidates(
        self, candidates: Sequence[TenderCandidate]
    ) -> dict[str, bool]:
        if not candidates:
            return {}

        urls = [candidate.url for candidate in candidates]
        existing_urls = set()
        conn = self._connect()
        try:
            cursor = conn.cursor()
            existing_statuses = {}
            for chunk in self._chunks(urls, 500):
                placeholders = ", ".join("?" for _ in chunk)
                cursor.execute(
                    f"SELECT url, filter_status FROM tender_candidates WHERE url IN ({placeholders})",
                    tuple(chunk),
                )
                for row in cursor.fetchall():
                    existing_urls.add(row[0])
                    existing_statuses[row[0]] = row[1]

            new_candidates = [
                candidate for candidate in candidates if candidate.url not in existing_urls
            ]
            if new_candidates:
                cursor.executemany(
                    """
                    INSERT INTO tender_candidates (
                        title, url, notice_type, keyword, source, publish_date,
                        raw_list_text, metadata_json, filter_status, filter_reason,
                        filter_confidence, decision_source
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [self._candidate_values(candidate, None) for candidate in new_candidates],
                )
            conn.commit()
            new_urls = {candidate.url for candidate in new_candidates}
            return {
                candidate.url: (
                    candidate.url in new_urls
                    or existing_statuses.get(candidate.url) == "pending"
                )
                for candidate in candidates
            }
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

    async def update_candidate_decisions(
        self, decisions: Sequence[tuple[TenderCandidate, TenderFilterDecision]]
    ) -> None:
        if not decisions:
            return
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.executemany(
                """
                UPDATE tender_candidates
                SET filter_status = ?,
                    filter_reason = ?,
                    filter_confidence = ?,
                    decision_source = ?,
                    updated_at = sysdatetime()
                WHERE url = ?
                """,
                [
                    (
                        self._status_from_decision(decision),
                        decision.reason,
                        decision.confidence,
                        decision.decision_source,
                        candidate.url,
                    )
                    for candidate, decision in decisions
                ],
            )
            conn.commit()
        finally:
            conn.close()

    async def save_notice(self, notice: TenderNotice) -> None:
        values = self._notice_values(notice)
        content_values = self._notice_content_values(notice)
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
                    project_category = ?,
                    summary = ?,
                    key_requirements_json = ?,
                    extraction_meta_json = ?,
                    updated_at = sysdatetime()
                WHERE url = ?
                """,
                values[0:1] + values[2:] + (notice.url,),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    INSERT INTO tender_notices (
                        title, url, notice_type, project_name, purchaser,
                        winning_bidder, budget_amount, budget_amount_wan_yuan,
                        winning_amount, winning_amount_wan_yuan, province, city,
                        publish_date, bid_open_date, deadline, project_category,
                        summary, key_requirements_json, extraction_meta_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
            cursor.execute(
                """
                UPDATE tender_notice_contents
                SET raw_content = ?,
                    updated_at = sysdatetime()
                WHERE url = ?
                """,
                content_values,
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    INSERT INTO tender_notice_contents (url, raw_content)
                    VALUES (?, ?)
                    """,
                    (notice.url, notice.raw_content),
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
            notice.winning_bidder,
            self._clamp_text(notice.budget_amount, self._AMOUNT_TEXT_MAX_LENGTH),
            self._safe_decimal_amount(notice.budget_amount_wan_yuan),
            self._clamp_text(notice.winning_amount, self._AMOUNT_TEXT_MAX_LENGTH),
            self._safe_decimal_amount(notice.winning_amount_wan_yuan),
            notice.province,
            notice.city,
            notice.publish_date,
            notice.bid_open_date,
            notice.deadline,
            notice.industry_category,
            notice.summary,
            json.dumps(notice.key_requirements, ensure_ascii=False),
            json.dumps(self._extraction_meta(notice), ensure_ascii=False, default=str),
        )

    def _clamp_text(self, value: str | None, max_length: int) -> str | None:
        if value is None:
            return None
        return value[:max_length]

    def _safe_decimal_amount(self, value: float | int | None) -> float | None:
        if value is None:
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        if abs(amount) >= self._AMOUNT_DECIMAL_MAX_ABS:
            return None
        return float(amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

    def _notice_content_values(self, notice: TenderNotice) -> tuple:
        return (
            notice.raw_content,
            notice.url,
        )

    def _extraction_meta(self, notice: TenderNotice) -> dict:
        return {
            "agency": notice.agency,
            "environment_relevance": notice.environment_relevance,
            "filter_reason": notice.filter_reason,
            "filter_confidence": notice.filter_confidence,
            "attachment_urls": notice.attachment_urls,
        }

    def _candidate_values(
        self, candidate: TenderCandidate, decision: TenderFilterDecision | None
    ) -> tuple:
        return (
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
        )

    def _status_from_decision(self, decision: TenderFilterDecision | None) -> str:
        if decision is None:
            return "pending"
        return "accepted" if decision.is_relevant else "rejected"

    def _chunks(self, values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
        for start in range(0, len(values), size):
            yield values[start : start + size]

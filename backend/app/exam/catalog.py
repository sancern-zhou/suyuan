"""Question-bank catalog helpers for the enforcement-exam runtime."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.models import KnowledgeBase, KnowledgeBaseStatus
from app.knowledge_base.permissions import local_visibility_filter

from .models import ExamQuestion
from .outline import build_question_bank_outline


ENFORCEMENT_EXAM_KNOWLEDGE_BASE_NAME = "执法知识"


async def enforcement_exam_knowledge_base_ids(session: AsyncSession) -> list[str]:
    """Return active, locally visible knowledge bases used by exam mode."""
    rows = await session.scalars(
        select(KnowledgeBase.id).where(
            KnowledgeBase.name == ENFORCEMENT_EXAM_KNOWLEDGE_BASE_NAME,
            KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE,
            local_visibility_filter(),
        )
    )
    return [str(item) for item in rows]


def _source_ref(question: ExamQuestion, allowed_kb_ids: set[str]) -> dict[str, Any] | None:
    for ref in question.source_refs or []:
        if not isinstance(ref, dict):
            continue
        kb_id = str(ref.get("knowledge_base_id") or "")
        document_id = str(ref.get("document_id") or "")
        if kb_id in allowed_kb_ids and document_id:
            return ref
    return None


async def list_exam_question_banks(
    session: AsyncSession,
    *,
    include_drafts: bool = False,
) -> list[dict[str, Any]]:
    """Group generated questions by source document (the user-facing bank)."""
    allowed_kb_ids = set(await enforcement_exam_knowledge_base_ids(session))
    if not allowed_kb_ids:
        return []

    statuses = {"published", "draft"} if include_drafts else {"published"}
    questions = (
        await session.scalars(
            select(ExamQuestion).where(
                ExamQuestion.enabled.is_(True),
                ExamQuestion.review_status.in_(statuses),
            )
        )
    ).all()
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for question in questions:
        ref = _source_ref(question, allowed_kb_ids)
        if not ref:
            continue
        key = (str(ref["knowledge_base_id"]), str(ref["document_id"]))
        bank = grouped.setdefault(
            key,
            {
                "bank_id": key[1],
                "knowledge_base_id": key[0],
                "name": str(ref.get("document_title") or key[1]),
                "question_count": 0,
                "question_type_counts": Counter(),
                "source_versions": set(),
                "status_counts": Counter(),
                "questions": [],
            },
        )
        bank["question_count"] += 1
        bank["question_type_counts"][question.question_type] += 1
        bank["status_counts"][question.review_status] += 1
        bank["questions"].append(question)
        if question.source_version:
            bank["source_versions"].add(question.source_version)

    result: list[dict[str, Any]] = []
    for bank in grouped.values():
        result.append(
            {
                "bank_id": bank["bank_id"],
                "knowledge_base_id": bank["knowledge_base_id"],
                "name": bank["name"],
                "question_count": bank["question_count"],
                "question_type_counts": dict(sorted(bank["question_type_counts"].items())),
                "source_versions": sorted(bank["source_versions"]),
                "published_question_count": bank["status_counts"].get("published", 0),
                "draft_question_count": bank["status_counts"].get("draft", 0),
                "selectable": bank["status_counts"].get("published", 0) > 0,
                "review_status": "published" if bank["status_counts"].get("published", 0) > 0 else "draft",
                "outline": build_question_bank_outline(
                    bank["questions"],
                    title=f"{bank['name']}题库大纲",
                ),
            }
        )
    return sorted(result, key=lambda item: (item["name"], item["bank_id"]))

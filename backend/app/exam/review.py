"""Question-bank publication checks and state transitions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .bank_generation import validate_candidate
from .models import ExamQuestion
from .outline import build_question_bank_outline


def publication_errors(question: ExamQuestion) -> list[str]:
    """Return structural/source errors that prevent a question from publishing."""
    source_refs = question.source_refs or []
    try:
        evidence_indices = {
            int(index)
            for ref in source_refs
            if isinstance(ref, dict)
            for index in (ref.get("chunk_indices") or [])
        }
    except (TypeError, ValueError):
        evidence_indices = set()
    candidate = {
        "question_type": question.question_type,
        "stem": question.stem,
        "options": question.options,
        "correct_answer": question.correct_answer,
        "scoring_points": question.scoring_points,
        "evidence_chunk_indices": sorted(evidence_indices),
    }
    errors = validate_candidate(candidate, evidence_indices)
    if not source_refs:
        errors.append("missing_source_refs")
    return list(dict.fromkeys(errors))


def _question_source(question: ExamQuestion, allowed_kb_ids: set[str]) -> tuple[str, str] | None:
    for ref in question.source_refs or []:
        if not isinstance(ref, dict):
            continue
        knowledge_base_id = str(ref.get("knowledge_base_id") or "")
        document_id = str(ref.get("document_id") or "")
        if knowledge_base_id in allowed_kb_ids and document_id:
            return knowledge_base_id, document_id
    return None


async def publish_question_bank(
    session: AsyncSession,
    *,
    bank_id: str,
    allowed_kb_ids: set[str],
) -> dict[str, Any]:
    """Publish every valid draft question belonging to a source-document bank."""
    questions = (
        await session.scalars(
            select(ExamQuestion).where(
                ExamQuestion.enabled.is_(True),
                ExamQuestion.review_status == "draft",
            )
        )
    ).all()
    bank_questions = [
        question
        for question in questions
        if (source := _question_source(question, allowed_kb_ids))
        and source[1] == str(bank_id)
    ]
    if not bank_questions:
        raise ValueError("未找到可发布的题库草稿")

    validation_errors = {
        question.id: publication_errors(question)
        for question in bank_questions
    }
    invalid = {question_id: errors for question_id, errors in validation_errors.items() if errors}
    if invalid:
        raise ValueError(
            f"题库包含 {len(invalid)} 道不满足发布条件的题目，未发布任何题目: "
            + ", ".join(f"{question_id}({','.join(errors)})" for question_id, errors in invalid.items())
        )

    for question in bank_questions:
        question.review_status = "published"
    await session.flush()
    return {
        "bank_id": str(bank_id),
        "published_question_count": len(bank_questions),
        "question_ids": [question.id for question in bank_questions],
        "outline": build_question_bank_outline(
            bank_questions,
            title="题库大纲",
        ),
    }

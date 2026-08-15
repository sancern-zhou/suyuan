"""Minimal administrator API for reviewing and publishing generated exam questions."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.db.database import get_db
from app.exam.review import publication_errors as _publication_errors
from app.exam.models import ExamQuestion

router = APIRouter(prefix="/api/exam", tags=["exam-bank"])


class QuestionPatch(BaseModel):
    stem: str | None = None
    options: dict[str, str] | None = None
    correct_answer: Any | None = None
    scoring_points: list[dict[str, Any]] | None = None
    topic: str | None = None
    difficulty: Literal["easy", "medium", "hard"] | None = None
    explanation_hint: str | None = None
    review_status: Literal["draft", "published", "retired"] | None = None
    enabled: bool | None = None


def _require_admin(user: CurrentUser) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin_required")


def _dto(question: ExamQuestion) -> dict[str, Any]:
    return {
        "id": question.id,
        "question_type": question.question_type,
        "topic": question.topic,
        "knowledge_point_id": question.knowledge_point_id,
        "stem": question.stem,
        "options": question.options,
        "correct_answer": question.correct_answer,
        "scoring_points": question.scoring_points,
        "source_refs": question.source_refs,
        "source_snapshot": question.source_snapshot,
        "source_version": question.source_version,
        "explanation_hint": question.explanation_hint,
        "difficulty": question.difficulty,
        "review_status": question.review_status,
        "enabled": question.enabled,
        "generated_by": question.generated_by,
        "created_at": question.created_at,
        "updated_at": question.updated_at,
    }


@router.get("/questions")
async def list_questions(
    review_status: Literal["draft", "published", "retired"] | None = None,
    question_type: str | None = None,
    topic: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_current_user),
):
    _require_admin(user)
    filters = []
    if review_status:
        filters.append(ExamQuestion.review_status == review_status)
    if question_type:
        filters.append(ExamQuestion.question_type == question_type)
    if topic:
        filters.append(ExamQuestion.topic == topic)
    total = await db.scalar(select(func.count(ExamQuestion.id)).where(*filters))
    questions = (
        await db.scalars(
            select(ExamQuestion)
            .where(*filters)
            .order_by(ExamQuestion.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {"questions": [_dto(item) for item in questions], "total": int(total or 0)}


@router.patch("/questions/{question_id}")
async def update_question(
    question_id: str,
    patch: QuestionPatch,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_current_user),
):
    _require_admin(user)
    question = await db.get(ExamQuestion, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="exam_question_not_found")
    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(question, field, value)
    if question.review_status == "published":
        errors = _publication_errors(question)
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "question_not_publishable", "errors": errors},
            )
    await db.flush()
    return _dto(question)

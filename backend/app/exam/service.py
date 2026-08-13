"""Deterministic practice state and grading behind the agent-facing tool."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ExamAttempt, ExamPracticeRun, ExamQuestion


QUESTION_TYPES = {"single_choice", "multiple_choice", "judgment", "short_answer"}
PRACTICE_MODES = {"random", "daily", "wrong_review", "unseen", "mock_exam"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_answer(question_type: str, answer: Any) -> Any:
    """Normalize common WeChat answer forms without deciding free-text semantics."""
    if question_type in {"single_choice", "multiple_choice"}:
        if isinstance(answer, list):
            tokens = [str(item).strip().upper() for item in answer]
        else:
            text = str(answer or "").upper()
            tokens = re.findall(r"(?<![A-Z])[A-D](?![A-Z])", text)
            if not tokens:
                compact = re.sub(r"[^A-D]", "", text)
                tokens = list(compact)
        normalized = sorted(set(token for token in tokens if token in {"A", "B", "C", "D"}))
        if question_type == "single_choice":
            return normalized[0] if len(normalized) == 1 else normalized
        return normalized

    if question_type == "judgment":
        if isinstance(answer, bool):
            return answer
        text = str(answer or "").strip().lower()
        if text in {"true", "t", "1", "对", "正确", "是", "√", "yes"}:
            return True
        if text in {"false", "f", "0", "错", "错误", "否", "×", "x", "no"}:
            return False
        return text

    return str(answer or "").strip()


class ExamPracticeError(ValueError):
    """A user-correctable practice state or parameter error."""


class ExamPracticeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(
        self,
        *,
        user_id: str,
        action: str,
        practice_mode: str | None = None,
        question_types: list[str] | None = None,
        topics: list[str] | None = None,
        count: int | None = None,
        answer: Any = None,
        run_id: str | None = None,
        question_id: str | None = None,
        is_correct: bool | None = None,
        score: float | None = None,
        evaluation: dict | None = None,
    ) -> dict[str, Any]:
        action = str(action or "").strip().lower()
        if action == "start":
            return await self.start(
                user_id=user_id,
                practice_mode=practice_mode or "unseen",
                question_types=question_types or [],
                topics=topics or [],
                count=count or 10,
            )
        if action == "current":
            return await self.current(user_id=user_id, run_id=run_id)
        if action == "submit":
            return await self.submit(
                user_id=user_id, run_id=run_id, question_id=question_id, answer=answer
            )
        if action == "submit_and_next":
            submitted = await self.submit(
                user_id=user_id, run_id=run_id, question_id=question_id, answer=answer
            )
            if submitted.get("stage") == "awaiting_grade":
                raise ExamPracticeError("简答题请先 submit 获取评分点，再调用 grade_and_next")
            return await self.next(user_id=user_id, run_id=run_id)
        if action == "grade":
            return await self.grade_short_answer(
                user_id=user_id,
                run_id=run_id,
                question_id=question_id,
                is_correct=is_correct,
                score=score,
                evaluation=evaluation or {},
            )
        if action == "grade_and_next":
            await self.grade_short_answer(
                user_id=user_id,
                run_id=run_id,
                question_id=question_id,
                is_correct=is_correct,
                score=score,
                evaluation=evaluation or {},
            )
            return await self.next(user_id=user_id, run_id=run_id)
        if action == "next":
            return await self.next(user_id=user_id, run_id=run_id)
        if action == "skip":
            return await self.skip(user_id=user_id, run_id=run_id, question_id=question_id)
        if action == "finish":
            return await self.finish(user_id=user_id, run_id=run_id)
        if action == "progress":
            return await self.progress(user_id=user_id)
        raise ExamPracticeError(f"不支持的 action: {action}")

    async def start(
        self,
        *,
        user_id: str,
        practice_mode: str,
        question_types: list[str],
        topics: list[str],
        count: int,
    ) -> dict[str, Any]:
        if practice_mode not in PRACTICE_MODES:
            raise ExamPracticeError(f"不支持的练习模式: {practice_mode}")
        invalid_types = sorted(set(question_types) - QUESTION_TYPES)
        if invalid_types:
            raise ExamPracticeError(f"不支持的题型: {', '.join(invalid_types)}")
        if count < 1 or count > 62:
            raise ExamPracticeError("count 必须在 1 到 62 之间")

        await self.session.execute(
            update(ExamPracticeRun)
            .where(ExamPracticeRun.user_id == user_id, ExamPracticeRun.status == "active")
            .values(status="abandoned", completed_at=_now())
        )

        question_ids = await self._select_question_ids(
            user_id=user_id,
            practice_mode=practice_mode,
            question_types=question_types,
            topics=topics,
            count=count,
        )
        if not question_ids:
            raise ExamPracticeError("当前条件下没有可用的已发布题目")

        run = ExamPracticeRun(
            id=str(uuid.uuid4()),
            user_id=user_id,
            practice_mode=practice_mode,
            question_types=question_types,
            topics=topics,
            question_ids=question_ids,
            target_count=len(question_ids),
            current_index=0,
            status="active",
        )
        self.session.add(run)
        await self.session.flush()
        return await self._deliver(run)

    async def current(self, *, user_id: str, run_id: str | None = None) -> dict[str, Any]:
        run = await self._get_run(user_id, run_id)
        if not run:
            return {"stage": "idle", "active": False, "summary": "当前没有进行中的练习"}
        if run.status != "active":
            return await self._run_summary(run)

        result = await self._deliver(run)
        last_attempt = await self.session.scalar(
            select(ExamAttempt)
            .where(ExamAttempt.run_id == run.id, ExamAttempt.status.in_(["answered", "graded"]))
            .order_by(ExamAttempt.sequence.desc())
            .limit(1)
        )
        if last_attempt and last_attempt.sequence != run.current_index + 1:
            result["last_result"] = await self._attempt_result(last_attempt)
        return result

    async def submit(
        self,
        *,
        user_id: str,
        run_id: str | None,
        question_id: str | None,
        answer: Any,
    ) -> dict[str, Any]:
        run = await self._require_active_run(user_id, run_id)
        current_question_id = self._current_question_id(run)
        if question_id and question_id != current_question_id:
            raise ExamPracticeError("提交的题目不是当前待答题目，请先调用 current")
        attempt = await self._get_or_create_attempt(run, current_question_id)
        if attempt.status in {"answered", "graded"}:
            return await self._attempt_result(attempt, duplicate=True)

        question = await self._get_question(current_question_id)
        normalized = normalize_answer(question.question_type, answer)
        answered_at = _now()
        # Objective answers are useful for wrong-answer review and statistics.
        # Short-answer text is already present in conversation history and can
        # contain long or sensitive free text, so it is not duplicated here.
        attempt.submitted_answer = (
            None if question.question_type == "short_answer" else normalized
        )
        attempt.answered_at = answered_at
        attempt.duration_seconds = max(
            0.0, (_as_utc(answered_at) - _as_utc(attempt.delivered_at)).total_seconds()
        )

        if question.question_type == "short_answer":
            attempt.status = "awaiting_grade"
            attempt.is_correct = None
        else:
            correct = normalize_answer(question.question_type, question.correct_answer)
            attempt.is_correct = normalized == correct
            attempt.score = 100.0 if attempt.is_correct else 0.0
            attempt.status = "answered"
        await self.session.flush()
        result = await self._attempt_result(attempt)
        if question.question_type == "short_answer":
            # The current call still needs the answer for immediate model
            # grading, but the database record deliberately leaves it empty.
            result["submitted_answer"] = normalized
        return result

    async def grade_short_answer(
        self,
        *,
        user_id: str,
        run_id: str | None,
        question_id: str | None,
        is_correct: bool | None,
        score: float | None,
        evaluation: dict,
    ) -> dict[str, Any]:
        run = await self._require_active_run(user_id, run_id)
        current_question_id = self._current_question_id(run)
        if question_id and question_id != current_question_id:
            raise ExamPracticeError("评分题目不是当前题目")
        attempt = await self._get_or_create_attempt(run, current_question_id)
        question = await self._get_question(current_question_id)
        if question.question_type != "short_answer" or attempt.status != "awaiting_grade":
            raise ExamPracticeError("当前没有等待评分的简答题")
        if score is None or not 0 <= float(score) <= 100:
            raise ExamPracticeError("简答题 score 必须在 0 到 100 之间")
        attempt.score = float(score)
        attempt.is_correct = bool(is_correct) if is_correct is not None else float(score) >= 60
        attempt.evaluation = evaluation
        attempt.status = "graded"
        await self.session.flush()
        return await self._attempt_result(attempt)

    async def next(self, *, user_id: str, run_id: str | None) -> dict[str, Any]:
        run = await self._require_active_run(user_id, run_id)
        current_id = self._current_question_id(run)
        attempt = await self._get_or_create_attempt(run, current_id)
        if attempt.status not in {"answered", "graded", "skipped"}:
            return {
                "stage": "question",
                "requires_answer": True,
                "summary": "当前题目尚未完成",
                **await self._public_question_payload(run, await self._get_question(current_id)),
            }
        last_result = await self._attempt_result(attempt)
        if run.current_index + 1 >= len(run.question_ids):
            run.status = "completed"
            run.completed_at = _now()
            await self.session.flush()
            result = await self._run_summary(run)
            result["last_result"] = last_result
            return result
        run.current_index += 1
        await self.session.flush()
        result = await self._deliver(run)
        # Keep the completed answer beside the next question in the latest tool
        # result. The agent can then render "解析 + 下一题" in one final reply
        # without recovering the previous result from older tool messages.
        result["last_result"] = last_result
        return result

    async def skip(
        self, *, user_id: str, run_id: str | None, question_id: str | None
    ) -> dict[str, Any]:
        run = await self._require_active_run(user_id, run_id)
        current_id = self._current_question_id(run)
        if question_id and question_id != current_id:
            raise ExamPracticeError("跳过的题目不是当前题目")
        attempt = await self._get_or_create_attempt(run, current_id)
        if attempt.status == "delivered":
            attempt.status = "skipped"
            attempt.skipped_at = _now()
            await self.session.flush()
        return await self.next(user_id=user_id, run_id=run.id)

    async def finish(self, *, user_id: str, run_id: str | None) -> dict[str, Any]:
        run = await self._get_run(user_id, run_id)
        if not run:
            return {"stage": "idle", "active": False, "summary": "当前没有进行中的练习"}
        if run.status == "active":
            run.status = "completed"
            run.completed_at = _now()
            await self.session.flush()
        return await self._run_summary(run)

    async def progress(self, *, user_id: str) -> dict[str, Any]:
        total, answered, correct, skipped, avg_duration = (
            await self.session.execute(
                select(
                    func.count(ExamAttempt.id),
                    func.sum(case((ExamAttempt.status.in_(["answered", "graded"]), 1), else_=0)),
                    func.sum(case((ExamAttempt.is_correct.is_(True), 1), else_=0)),
                    func.sum(case((ExamAttempt.status == "skipped", 1), else_=0)),
                    func.avg(ExamAttempt.duration_seconds),
                ).where(ExamAttempt.user_id == user_id)
            )
        ).one()
        topic_rows = (
            await self.session.execute(
                select(
                    ExamQuestion.topic,
                    func.count(ExamAttempt.id),
                    func.sum(case((ExamAttempt.is_correct.is_(True), 1), else_=0)),
                )
                .join(ExamQuestion, ExamQuestion.id == ExamAttempt.question_id)
                .where(
                    ExamAttempt.user_id == user_id,
                    ExamAttempt.status.in_(["answered", "graded"]),
                )
                .group_by(ExamQuestion.topic)
            )
        ).all()
        weak_topics = [
            {"topic": topic or "未分类", "answered": int(n), "correct": int(c or 0), "accuracy": round((c or 0) / n, 4)}
            for topic, n, c in topic_rows
            if n and (c or 0) / n < 0.6
        ]
        answered_n = int(answered or 0)
        correct_n = int(correct or 0)
        return {
            "stage": "progress",
            "seen": int(total or 0),
            "answered": answered_n,
            "correct": correct_n,
            "skipped": int(skipped or 0),
            "accuracy": round(correct_n / answered_n, 4) if answered_n else None,
            "average_duration_seconds": round(float(avg_duration), 1) if avg_duration is not None else None,
            "weak_topics": sorted(weak_topics, key=lambda item: item["accuracy"]),
        }

    async def _select_question_ids(
        self,
        *,
        user_id: str,
        practice_mode: str,
        question_types: list[str],
        topics: list[str],
        count: int,
    ) -> list[str]:
        stmt = select(ExamQuestion.id).where(
            ExamQuestion.enabled.is_(True), ExamQuestion.review_status == "published"
        )
        if question_types:
            stmt = stmt.where(ExamQuestion.question_type.in_(question_types))
        if topics:
            stmt = stmt.where(ExamQuestion.topic.in_(topics))

        answered_ids = select(ExamAttempt.question_id).where(
            ExamAttempt.user_id == user_id,
            ExamAttempt.status.in_(["answered", "graded"]),
        )
        correct_ids = select(ExamAttempt.question_id).where(
            ExamAttempt.user_id == user_id, ExamAttempt.is_correct.is_(True)
        )
        if practice_mode in {"unseen", "daily"}:
            stmt = stmt.where(ExamQuestion.id.not_in(answered_ids))
        elif practice_mode == "wrong_review":
            stmt = stmt.where(ExamQuestion.id.in_(answered_ids), ExamQuestion.id.not_in(correct_ids))

        rows = await self.session.scalars(stmt.order_by(func.random()).limit(count))
        return list(rows)

    async def _get_run(self, user_id: str, run_id: str | None) -> ExamPracticeRun | None:
        stmt = select(ExamPracticeRun).where(ExamPracticeRun.user_id == user_id)
        if run_id:
            stmt = stmt.where(ExamPracticeRun.id == run_id)
        else:
            stmt = stmt.where(ExamPracticeRun.status == "active").order_by(ExamPracticeRun.started_at.desc())
        return await self.session.scalar(stmt.limit(1))

    async def _require_active_run(self, user_id: str, run_id: str | None) -> ExamPracticeRun:
        run = await self._get_run(user_id, run_id)
        if not run or run.status != "active":
            raise ExamPracticeError("当前没有进行中的练习，请先开始刷题")
        return run

    @staticmethod
    def _current_question_id(run: ExamPracticeRun) -> str:
        if run.current_index < 0 or run.current_index >= len(run.question_ids):
            raise ExamPracticeError("练习进度异常，没有当前题目")
        return str(run.question_ids[run.current_index])

    async def _get_question(self, question_id: str) -> ExamQuestion:
        question = await self.session.get(ExamQuestion, question_id)
        if not question:
            raise ExamPracticeError("题目不存在或已被删除")
        return question

    async def _get_or_create_attempt(self, run: ExamPracticeRun, question_id: str) -> ExamAttempt:
        sequence = run.current_index + 1
        attempt = await self.session.scalar(
            select(ExamAttempt).where(
                ExamAttempt.run_id == run.id, ExamAttempt.sequence == sequence
            )
        )
        if attempt:
            return attempt
        attempt = ExamAttempt(
            id=str(uuid.uuid4()),
            run_id=run.id,
            user_id=run.user_id,
            question_id=question_id,
            sequence=sequence,
            status="delivered",
            delivered_at=_now(),
        )
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def _deliver(self, run: ExamPracticeRun) -> dict[str, Any]:
        question = await self._get_question(self._current_question_id(run))
        attempt = await self._get_or_create_attempt(run, question.id)
        if attempt.status in {"answered", "graded"}:
            return await self._attempt_result(attempt)
        return {
            "stage": "question",
            "requires_answer": True,
            **await self._public_question_payload(run, question),
        }

    async def _public_question_payload(
        self, run: ExamPracticeRun, question: ExamQuestion
    ) -> dict[str, Any]:
        return {
            "run_id": run.id,
            "question": {
                "question_id": question.id,
                "sequence": run.current_index + 1,
                "total": len(run.question_ids),
                "type": question.question_type,
                "topic": question.topic,
                "stem": question.stem,
                "options": question.options or {},
                "difficulty": question.difficulty,
            },
        }

    async def _attempt_result(self, attempt: ExamAttempt, duplicate: bool = False) -> dict[str, Any]:
        question = await self._get_question(attempt.question_id)
        payload = {
            "stage": "result" if attempt.status != "awaiting_grade" else "awaiting_grade",
            "run_id": attempt.run_id,
            "question_id": question.id,
            "question_type": question.question_type,
            "topic": question.topic,
            "submitted_answer": attempt.submitted_answer,
            "correct_answer": question.correct_answer,
            "is_correct": attempt.is_correct,
            "score": attempt.score,
            "duration_seconds": round(attempt.duration_seconds or 0.0, 1),
            "answered_at": attempt.answered_at.isoformat() if attempt.answered_at else None,
            "source_refs": question.source_refs or [],
            "source_version": question.source_version,
            "source_snapshot": question.source_snapshot,
            "explanation_hint": question.explanation_hint,
            "evaluation": attempt.evaluation or {},
            "duplicate_submission": duplicate,
        }
        if question.question_type == "short_answer":
            payload["scoring_points"] = question.scoring_points or []
            payload["requires_model_grade"] = attempt.status == "awaiting_grade"
        return payload

    async def _run_summary(self, run: ExamPracticeRun) -> dict[str, Any]:
        attempts = (
            await self.session.scalars(
                select(ExamAttempt).where(ExamAttempt.run_id == run.id).order_by(ExamAttempt.sequence)
            )
        ).all()
        answered = [item for item in attempts if item.status in {"answered", "graded"}]
        correct = [item for item in answered if item.is_correct]
        return {
            "stage": "completed",
            "active": False,
            "run_id": run.id,
            "practice_mode": run.practice_mode,
            "total": run.target_count,
            "seen": len(attempts),
            "answered": len(answered),
            "correct": len(correct),
            "accuracy": round(len(correct) / len(answered), 4) if answered else None,
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

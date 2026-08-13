from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.exam.models import ExamAttempt, ExamPracticeRun, ExamQuestion
from app.exam.service import ExamPracticeService, normalize_answer


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[ExamQuestion.__table__, ExamPracticeRun.__table__, ExamAttempt.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed(factory):
    questions = [
        ExamQuestion(
            id="q-single",
            question_type="single_choice",
            topic="行政处罚程序",
            stem="作出处罚决定前应当履行什么程序？",
            options={"A": "告知", "B": "直接处罚", "C": "先收费", "D": "先公示"},
            correct_answer="A",
            source_refs=[{
                "knowledge_base_id": "kb-exam",
                "document_id": "doc-law",
                "chunk_indices": [10, 11],
                "article": "第四十四条",
            }],
            source_version="2021-07-15",
            review_status="published",
        ),
        ExamQuestion(
            id="q-multiple",
            question_type="multiple_choice",
            topic="自动监控",
            stem="自动监测设备运行应当做到哪些要求？",
            options={"A": "正常运行", "B": "保存记录", "C": "保证数据真实", "D": "可任意修改"},
            correct_answer=["A", "B", "C"],
            source_refs=[{
                "knowledge_base_id": "kb-exam",
                "document_id": "doc-auto",
                "chunk_indices": [3],
            }],
            review_status="published",
        ),
        ExamQuestion(
            id="q-draft",
            question_type="judgment",
            topic="未审核",
            stem="草稿题不得出现。",
            options={},
            correct_answer=False,
            review_status="draft",
        ),
        ExamQuestion(
            id="q-short",
            question_type="short_answer",
            topic="简答程序",
            stem="简述行政处罚告知程序。",
            options={},
            correct_answer="作出行政处罚决定前，应当告知当事人拟作出的内容及事实、理由、依据和权利。",
            scoring_points=[
                {"point": "告知处罚内容及事实、理由、依据", "score": 60},
                {"point": "告知陈述、申辩等权利", "score": 40},
            ],
            source_refs=[{
                "knowledge_base_id": "kb-exam",
                "document_id": "doc-law",
                "chunk_indices": [10, 11],
                "article": "第四十四条",
            }],
            explanation_hint="重点包括拟处罚内容、事实理由依据和救济权利。",
            review_status="published",
        ),
    ]
    async with factory() as session:
        async with session.begin():
            session.add_all(questions)


@pytest.mark.asyncio
async def test_practice_hides_answer_until_submit_and_records_server_duration(session_factory):
    await _seed(session_factory)
    async with session_factory() as session:
        async with session.begin():
            service = ExamPracticeService(session)
            started = await service.start(
                user_id="user-1",
                practice_mode="unseen",
                question_types=["single_choice"],
                topics=[],
                count=10,
            )

            assert started["stage"] == "question"
            assert started["question"]["question_id"] == "q-single"
            assert "correct_answer" not in started["question"]
            assert "source_refs" not in started["question"]

            result = await service.submit(
                user_id="user-1",
                run_id=started["run_id"],
                question_id="q-single",
                answer="我选A",
            )

            assert result["stage"] == "result"
            assert result["is_correct"] is True
            assert result["correct_answer"] == "A"
            assert result["source_refs"][0]["article"] == "第四十四条"
            assert result["duration_seconds"] >= 0

            completed = await service.next(user_id="user-1", run_id=started["run_id"])
            assert completed["stage"] == "completed"
            assert completed["accuracy"] == 1.0
            assert completed["last_result"]["question_id"] == "q-single"
            assert completed["last_result"]["is_correct"] is True


@pytest.mark.asyncio
async def test_next_returns_last_result_together_with_next_question(session_factory):
    await _seed(session_factory)
    async with session_factory() as session:
        async with session.begin():
            service = ExamPracticeService(session)
            started = await service.start(
                user_id="user-next",
                practice_mode="random",
                question_types=["single_choice", "multiple_choice"],
                topics=[],
                count=2,
            )
            first = started["question"]
            wrong_answer = "B" if first["question_id"] == "q-single" else "D"
            submitted = await service.submit(
                user_id="user-next",
                run_id=started["run_id"],
                question_id=first["question_id"],
                answer=wrong_answer,
            )
            assert submitted["is_correct"] is False

            following = await service.next(
                user_id="user-next",
                run_id=started["run_id"],
            )

            assert following["stage"] == "question"
            assert following["question"]["sequence"] == 2
            assert following["last_result"]["question_id"] == first["question_id"]
            assert following["last_result"]["submitted_answer"] == submitted["submitted_answer"]
            assert following["last_result"]["is_correct"] is False
            assert following["last_result"]["score"] == 0.0


@pytest.mark.asyncio
async def test_submit_and_next_grades_objective_question_in_one_action(session_factory):
    await _seed(session_factory)
    async with session_factory() as session:
        async with session.begin():
            service = ExamPracticeService(session)
            started = await service.start(
                user_id="user-combined",
                practice_mode="random",
                question_types=["single_choice"],
                topics=[],
                count=1,
            )

            completed = await service.execute(
                user_id="user-combined",
                action="submit_and_next",
                run_id=started["run_id"],
                question_id="q-single",
                answer="B",
            )

            assert completed["stage"] == "completed"
            assert completed["last_result"]["submitted_answer"] == "B"
            assert completed["last_result"]["correct_answer"] == "A"
            assert completed["last_result"]["is_correct"] is False
            assert completed["last_result"]["source_refs"][0]["article"] == "第四十四条"


@pytest.mark.asyncio
async def test_short_answer_is_not_persisted_and_grade_and_next_advances(session_factory):
    await _seed(session_factory)
    async with session_factory() as session:
        async with session.begin():
            service = ExamPracticeService(session)
            started = await service.start(
                user_id="user-short",
                practice_mode="random",
                question_types=["short_answer"],
                topics=[],
                count=1,
            )
            answer = "应告知事实理由依据，并告知陈述申辩权。"

            awaiting = await service.submit(
                user_id="user-short",
                run_id=started["run_id"],
                question_id="q-short",
                answer=answer,
            )
            assert awaiting["stage"] == "awaiting_grade"
            assert awaiting["submitted_answer"] == answer
            assert awaiting["scoring_points"]

            attempt = await session.scalar(
                select(ExamAttempt).where(ExamAttempt.run_id == started["run_id"])
            )
            assert attempt is not None
            assert attempt.submitted_answer is None

            completed = await service.execute(
                user_id="user-short",
                action="grade_and_next",
                run_id=started["run_id"],
                question_id="q-short",
                is_correct=True,
                score=100,
                evaluation={"hit_points": ["告知内容", "告知权利"]},
            )
            assert completed["stage"] == "completed"
            assert completed["last_result"]["is_correct"] is True
            assert completed["last_result"]["score"] == 100.0
            assert completed["last_result"]["submitted_answer"] is None


@pytest.mark.asyncio
async def test_wrong_review_selects_answered_but_not_correct_questions(session_factory):
    await _seed(session_factory)
    async with session_factory() as session:
        async with session.begin():
            service = ExamPracticeService(session)
            started = await service.start(
                user_id="user-2",
                practice_mode="random",
                question_types=["single_choice"],
                topics=[],
                count=1,
            )
            result = await service.submit(
                user_id="user-2",
                run_id=started["run_id"],
                question_id="q-single",
                answer="B",
            )
            assert result["is_correct"] is False
            await service.finish(user_id="user-2", run_id=started["run_id"])

            retry = await service.start(
                user_id="user-2",
                practice_mode="wrong_review",
                question_types=[],
                topics=[],
                count=10,
            )
            assert retry["question"]["question_id"] == "q-single"


@pytest.mark.parametrize(
    ("question_type", "raw", "expected"),
    [
        ("single_choice", "我选择 b", "B"),
        ("multiple_choice", "A、C、D", ["A", "C", "D"]),
        ("multiple_choice", ["c", "a", "c"], ["A", "C"]),
        ("judgment", "正确", True),
        ("judgment", "×", False),
    ],
)
def test_normalize_wechat_answers(question_type, raw, expected):
    assert normalize_answer(question_type, raw) == expected

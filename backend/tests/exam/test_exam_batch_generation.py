from collections import Counter
from contextlib import contextmanager

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.exam.bank_generation import ExamBankGenerationService, SourceBatch
from app.exam.batch_generation import (
    DEFAULT_SOURCE_GROUPS,
    ChunkCandidate,
    allocate_question_types,
    deduplicate_chunk_candidates,
    load_generation_job,
    save_generation_job,
)
from app.exam.models import ExamQuestion
from app.knowledge_base.models import Document, KnowledgeBase


def _candidate(index: int, text: str) -> ChunkCandidate:
    return ChunkCandidate(
        document_id="doc",
        filename="法典.pdf",
        chunk_index=index,
        text=text,
        normalized_text=text,
    )


def test_chunk_deduplication_keeps_one_representative_per_near_duplicate_group():
    unique, stats = deduplicate_chunk_candidates(
        [
            _candidate(1, "行政机关作出行政处罚决定前应当告知当事人依法享有的权利"),
            _candidate(2, "行政机关作出行政处罚决定前应当告知当事人依法享有的权利。"),
            _candidate(3, "执法人员进行调查取证时不得少于二人"),
        ],
        threshold=0.90,
    )

    assert len(unique) == 2
    assert stats == {"groups": 1, "removed": 1, "largest_group": 2}


def test_default_plan_has_requested_candidate_margin_and_question_mix():
    assert sum(item.primary_quota for item in DEFAULT_SOURCE_GROUPS) == 320
    assert sum(item.reserve_quota for item in DEFAULT_SOURCE_GROUPS) == 80
    assert Counter(allocate_question_types(320)) == {
        "single_choice": 128,
        "multiple_choice": 80,
        "judgment": 80,
        "short_answer": 32,
    }


def test_generation_checkpoint_is_written_atomically_and_reloadable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.exam.batch_generation.get_data_registry",
        lambda: tmp_path,
    )
    job = {"job_id": "exam-test", "status": "planned", "chunks": []}

    path = save_generation_job(job)

    assert path == tmp_path / "exam_generation" / "exam-test.json"
    assert load_generation_job("exam-test")["status"] == "planned"
    assert not path.with_suffix(".json.tmp").exists()


@pytest.mark.asyncio
async def test_auto_generation_enforces_one_question_per_anchor_chunk():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[KnowledgeBase.__table__, Document.__table__, ExamQuestion.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    class FakeLLM:
        model = "auto-test-model"

        def __init__(self):
            self.selected_tiers = []

        @contextmanager
        def use_model_tier(self, tier):
            self.selected_tiers.append(tier)
            yield

        async def call_llm_with_json_response(self, prompt, max_retries=2):
            if "独立题库复核员" in prompt:
                return {
                    "verdicts": [
                        {
                            "candidate_id": "q1",
                            "answer_supported": True,
                            "unambiguous": True,
                            "source_match": True,
                            "worth_testing": True,
                            "risk_flags": [],
                        }
                    ]
                }
            base = {
                "question_type": "single_choice",
                "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                "correct_answer": "A",
                "evidence_chunk_indices": [3],
                "evidence_quote": "行政机关应当告知当事人",
                "topic": "行政处罚",
                "outline_category": "法学基础和法律法规",
                "importance_level": "core",
                "importance_reasons": ["属于核心执法程序"],
            }
            return {
                "questions": [
                    {
                        **base,
                        "candidate_id": "q1",
                        "stem": "作出行政处罚决定前，行政机关应当履行什么程序？",
                        "knowledge_point": "行政处罚事先告知",
                    },
                    {
                        **base,
                        "candidate_id": "q2",
                        "stem": "行政处罚决定前需要如何保障当事人权利？",
                        "knowledge_point": "当事人权利保障",
                    },
                ]
            }

    try:
        async with factory() as session:
            async with session.begin():
                document = Document(
                    id="doc",
                    knowledge_base_id="kb",
                    filename="行政处罚法.pdf",
                )
                session.add(document)
            async with session.begin():
                llm = FakeLLM()
                result = await ExamBankGenerationService(
                    session,
                    llm=llm,
                    model_tier="auto",
                    generation_job_id="job-1",
                )._generate_batch(
                    SourceBatch(
                        "doc",
                        "行政处罚法.pdf",
                        (3,),
                        "[chunk_index=3]\n行政机关应当告知当事人",
                    ),
                    document,
                    requested_counts={"single_choice": 2},
                    one_question_per_chunk=True,
                )

        assert result["created"] == 1
        assert result["rejected"] == 1
        assert result["rejections"][0]["errors"] == ["anchor_chunk_already_used"]
        assert llm.selected_tiers == ["auto", "auto"]
        outline = result["questions"][0]["source_refs"][0]["exam_outline"]
        assert outline["model_tier"] == "auto"
        assert outline["generation_job_id"] == "job-1"
    finally:
        await engine.dispose()

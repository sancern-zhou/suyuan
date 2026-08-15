from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

from app.exam.bank_generation import (
    ExamBankGenerationService,
    SourceBatch,
    build_source_batches,
    allocate_batch_question_counts,
    evidence_quote_is_in_cited_chunks,
    normalize_question_counts,
    select_coverage_batches,
    validate_candidate,
    validate_exam_priority,
)
from app.exam.outline import build_question_bank_outline
from app.exam.source_policy import evaluate_exam_source
from app.exam.models import ExamQuestion
from app.db.database import Base
from app.knowledge_base.models import (
    Document,
    DocumentStatus,
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeBaseStorageScope,
    KnowledgeBaseType,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import pytest


def test_source_batches_preserve_document_chunk_indices():
    batches = build_source_batches(
        "doc-1",
        "行政处罚法.pdf",
        [
            {"chunk_index": 3, "content": "第一段" * 10},
            {"chunk_index": 4, "content": "第二段" * 10},
        ],
        max_chars=50,
    )

    assert [batch.chunk_indices for batch in batches] == [(3,), (4,)]
    assert "[chunk_index=3]" in batches[0].text


def test_evidence_quote_must_exist_in_the_specifically_cited_chunk():
    batch = SourceBatch(
        "doc-1",
        "行政处罚法.pdf",
        (3, 4),
        "[chunk_index=3]\n第一段原文\n\n[chunk_index=4]\n第二段原文",
    )

    assert evidence_quote_is_in_cited_chunks(batch, [3], "第一段原文") is True
    assert evidence_quote_is_in_cited_chunks(batch, [4], "第一段原文") is False


def test_coverage_batches_span_large_document_without_one_call_per_question():
    batches = [SourceBatch("doc", "法典.pdf", (index,), str(index)) for index in range(20)]

    selected = select_coverage_batches(batches, {"single_choice": 5, "judgment": 4})

    assert [batch.chunk_indices[0] for batch in selected] == [0, 10, 19]


def test_batch_question_allocation_preserves_total_and_bounds_current_batch():
    allocated = allocate_batch_question_counts(
        {"single_choice": 5, "multiple_choice": 3, "judgment": 4, "short_answer": 3},
        remaining_batches=5,
    )

    assert sum(allocated.values()) == 3
    assert allocated == {"single_choice": 2, "judgment": 1}


def test_exam_source_requires_current_complete_official_metadata():
    eligible, reason = evaluate_exam_source(
        SimpleNamespace(extra_metadata={"exam_generation_eligible": True}),
        as_of=date(2026, 8, 15),
    )
    assert eligible is False
    assert "现行有效" in reason

    eligible, reason = evaluate_exam_source(
        SimpleNamespace(extra_metadata={
            "exam_generation_eligible": True,
            "validity_status": "effective",
            "issuer": "全国人民代表大会",
            "effective_date": "2026-08-15",
            "official_source_url": "https://example.test/current-law",
        }),
        as_of=date(2026, 8, 15),
    )
    assert eligible is True
    assert reason == "现行有效且来源信息完整"


def test_candidate_validation_rejects_unsupported_or_ambiguous_choice_question():
    errors = validate_candidate(
        {
            "question_type": "single_choice",
            "stem": "哪一项正确？",
            "options": {"A": "甲", "B": "乙", "C": "丙"},
            "correct_answer": ["A", "B"],
            "evidence_chunk_indices": [99],
        },
        {1, 2},
    )

    assert "evidence_outside_source_batch" in errors
    assert "choice_options_must_be_abcd" in errors
    assert "single_choice_requires_one_answer" in errors


def test_candidate_validation_accepts_grounded_multiple_choice():
    errors = validate_candidate(
        {
            "question_type": "multiple_choice",
            "stem": "哪些属于法定要求？",
            "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
            "correct_answer": ["A", "C"],
            "evidence_chunk_indices": [1, 2],
        },
        {1, 2, 3},
    )
    assert errors == []


def test_short_answer_scoring_points_follow_hundred_point_rule():
    errors = validate_candidate(
        {
            "question_type": "short_answer",
            "stem": "请简述程序要求。",
            "correct_answer": "应当依法履行告知程序。",
            "scoring_points": [{"point": "说明告知义务", "score": 60}],
            "evidence_chunk_indices": [1],
        },
        {1},
    )

    assert "short_answer_scoring_points_must_sum_100" in errors


def test_generation_prompt_requires_exact_machine_readable_field_names():
    prompt = ExamBankGenerationService._generation_prompt(
        SourceBatch("doc-1", "行政处罚法.pdf", (3,), "[chunk_index=3]\n原文")
    )

    assert '"question_type": "single_choice"' in prompt
    assert '"stem": "题干"' in prompt
    assert "不得改名、翻译字段名" in prompt


def test_generation_prompt_contains_requested_question_mix():
    prompt = ExamBankGenerationService._generation_prompt(
        SourceBatch("doc-1", "行政处罚法.pdf", (3,), "[chunk_index=3]\n原文"),
        requested_counts={
            "single_choice": 2,
            "multiple_choice": 1,
            "judgment": 1,
            "short_answer": 1,
        },
    )

    assert '"single_choice": 2' in prompt
    assert '"short_answer": 1' in prompt


def test_question_count_validation_keeps_four_question_types_bounded():
    assert normalize_question_counts({
        "single_choice": 2,
        "multiple_choice": 1,
        "judgment": 1,
        "short_answer": 1,
    })["short_answer"] == 1


def test_low_value_or_unclassified_knowledge_point_is_rejected():
    errors = validate_exam_priority({
        "knowledge_point": "立法背景",
        "outline_category": "法学基础和法律法规",
        "importance_level": "skip",
        "importance_reasons": ["仅为背景介绍"],
    })

    assert "low_value_knowledge_point" in errors


def test_question_bank_outline_groups_categories_topics_and_knowledge_points():
    outline = build_question_bank_outline(
        [{
            "question_type": "single_choice",
            "topic": "行政处罚程序",
            "source_refs": [{
                "exam_outline": {
                    "category": "法学基础和法律法规",
                    "knowledge_point": "事先告知",
                    "importance_level": "core",
                }
            }],
        }],
        title="测试题库大纲",
    )

    assert outline["title"] == "测试题库大纲"
    assert outline["categories"][0]["name"] == "法学基础和法律法规"
    assert outline["categories"][0]["topics"][0]["knowledge_points"] == ["事先告知"]


@pytest.mark.asyncio
async def test_generation_returns_all_requested_question_types_with_answers():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[KnowledgeBase.__table__, Document.__table__, ExamQuestion.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    class FakeLLM:
        model = "test-model"

        def __init__(self):
            self.selected_tiers = []

        @contextmanager
        def use_model_tier(self, tier):
            self.selected_tiers.append(tier)
            yield

        async def call_llm_with_json_response(self, prompt, max_retries=2):
            if "独立题库复核员" in prompt:
                return {"verdicts": [
                    {
                        "candidate_id": f"q-{kind}",
                        "answer_supported": True,
                        "unambiguous": True,
                        "source_match": True,
                        "worth_testing": True,
                    }
                    for kind in ("single", "multiple", "judgment", "short")
                ]}
            return {"questions": [
                {
                    "candidate_id": "q-single",
                    "question_type": "single_choice",
                    "stem": "单选题",
                    "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                    "correct_answer": "A",
                    "evidence_chunk_indices": [0],
                    "evidence_quote": "原文",
                    "topic": "行政处罚",
                    "knowledge_point": "单选考点",
                    "outline_category": "法学基础和法律法规",
                    "importance_level": "core",
                    "importance_reasons": ["属于核心法律程序"],
                },
                {
                    "candidate_id": "q-multiple",
                    "question_type": "multiple_choice",
                    "stem": "多选题",
                    "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                    "correct_answer": ["A", "B"],
                    "evidence_chunk_indices": [0],
                    "evidence_quote": "原文",
                    "topic": "行政处罚",
                    "knowledge_point": "多选考点",
                    "outline_category": "法学基础和法律法规",
                    "importance_level": "core",
                    "importance_reasons": ["涉及多项法定要求"],
                },
                {
                    "candidate_id": "q-judgment",
                    "question_type": "judgment",
                    "stem": "判断题",
                    "options": {},
                    "correct_answer": True,
                    "evidence_chunk_indices": [0],
                    "evidence_quote": "原文",
                    "topic": "行政处罚",
                    "knowledge_point": "判断考点",
                    "outline_category": "法学基础和法律法规",
                    "importance_level": "normal",
                    "importance_reasons": ["大纲相关且原文明确"],
                },
                {
                    "candidate_id": "q-short",
                    "question_type": "short_answer",
                    "stem": "简答题",
                    "options": {},
                    "correct_answer": "参考答案",
                    "scoring_points": [{"point": "核心要点", "score": 100}],
                    "evidence_chunk_indices": [0],
                    "evidence_quote": "原文",
                    "topic": "行政处罚",
                    "knowledge_point": "简答考点",
                    "outline_category": "法学基础和法律法规",
                    "importance_level": "core",
                    "importance_reasons": ["适合考查程序要点"],
                },
            ]}

    async with factory() as session:
        async with session.begin():
            session.add(KnowledgeBase(
                id="kb",
                name="执法知识",
                kb_type=KnowledgeBaseType.PUBLIC,
                status=KnowledgeBaseStatus.ACTIVE,
                vector_store_scope=KnowledgeBaseStorageScope.SHARED,
                qdrant_collection="kb-collection",
            ))
            session.add(Document(
                id="doc",
                knowledge_base_id="kb",
                filename="执法原文.txt",
                status=DocumentStatus.COMPLETED,
                extra_metadata={
                    "exam_generation_eligible": True,
                    "validity_status": "effective",
                    "issuer": "测试机关",
                    "effective_date": "2020-01-01",
                    "official_source_url": "https://example.test/source",
                },
            ))
        async with session.begin():
            fake_llm = FakeLLM()
            service = ExamBankGenerationService(session, llm=fake_llm)

            async def load_chunks(_document_id):
                return [{"chunk_index": 0, "content": "原文"}]

            service._load_document_chunks = load_chunks
            result = await service.generate_document(
                knowledge_base_id="kb",
                document_id="doc",
                question_counts={
                    "single_choice": 1,
                    "multiple_choice": 1,
                    "judgment": 1,
                    "short_answer": 1,
                },
            )

    assert result["created_drafts"] == 4
    assert {item["question_type"] for item in result["questions"]} == {
        "single_choice", "multiple_choice", "judgment", "short_answer"
    }
    assert all("correct_answer" in item and "explanation_hint" in item for item in result["questions"])
    assert result["outline"]["question_count"] == 4
    assert result["outline"]["categories"][0]["name"] == "法学基础和法律法规"
    assert fake_llm.selected_tiers == ["pro", "pro"]
    assert all(
        item["source_refs"][0]["exam_outline"]["model_tier"] == "pro"
        for item in result["questions"]
    )
    await engine.dispose()

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.exam.catalog import list_exam_question_banks
from app.exam.models import ExamQuestion
from app.agent.tool_adapter import (
    call_llm_tool,
    get_react_agent_tool_registry,
    get_tool_schemas,
)
from app.knowledge_base.models import (
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeBaseStorageScope,
    KnowledgeBaseType,
)
from app.tools.exam.exam_bank import GenerateExamBankTool


def test_generate_exam_bank_schema_exposes_source_selection_and_question_mix():
    schema = GenerateExamBankTool().get_function_schema()
    properties = schema["parameters"]["properties"]

    assert schema["name"] == "generate_exam_bank"
    assert properties["action"]["enum"] == ["list_sources", "list_banks", "generate", "publish"]
    assert set(properties["question_counts"]["properties"]) == {
        "single_choice",
        "multiple_choice",
        "judgment",
        "short_answer",
    }


@pytest.mark.asyncio
async def test_react_adapter_exposes_and_routes_generate_exam_bank():
    schemas = get_tool_schemas(mode="enforcement_exam")
    assert "generate_exam_bank" in {schema["name"] for schema in schemas}

    registry = get_react_agent_tool_registry()
    assert callable(registry["generate_exam_bank"])

    result = await call_llm_tool(
        "generate_exam_bank",
        SimpleNamespace(runtime_mode="social", user_identifier="u-1"),
        action="list_sources",
    )
    assert result["success"] is False
    assert "执法考试模式" in result["summary"]


@pytest.mark.asyncio
async def test_generate_exam_bank_rejects_non_exam_runtime_without_opening_db():
    class SessionFactory:
        def __call__(self):
            raise AssertionError("database should not be opened")

    tool = GenerateExamBankTool(session_factory=SessionFactory())
    result = await tool.execute(
        context=SimpleNamespace(runtime_mode="social", user_identifier="u-1"),
        action="list_sources",
    )

    assert result["success"] is False
    assert "执法考试模式" in result["summary"]


@pytest.mark.asyncio
async def test_publish_requires_explicit_user_confirmation():
    class SessionFactory:
        def __call__(self):
            raise AssertionError("database should not be opened without confirmation")

    tool = GenerateExamBankTool(session_factory=SessionFactory())
    result = await tool.execute(
        context=SimpleNamespace(runtime_mode="enforcement_exam", user_identifier="u-1"),
        action="publish",
        bank_id="doc-1",
        confirm_publish=False,
    )

    assert result["success"] is False
    assert "明确同意" in result["summary"]


@pytest.mark.asyncio
async def test_publish_confirmed_bank_updates_only_matching_drafts():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[KnowledgeBase.__table__, ExamQuestion.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with session.begin():
                session.add(
                    KnowledgeBase(
                        id="kb-exam",
                        name="执法知识",
                        kb_type=KnowledgeBaseType.PUBLIC,
                        status=KnowledgeBaseStatus.ACTIVE,
                        vector_store_scope=KnowledgeBaseStorageScope.SHARED,
                        qdrant_collection="kb-exam-collection",
                    )
                )
                session.add_all(
                    [
                        ExamQuestion(
                            id="draft-publish",
                            question_type="single_choice",
                            topic="程序",
                            stem="哪项正确？",
                            options={"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                            correct_answer="A",
                            source_refs=[{
                                "knowledge_base_id": "kb-exam",
                                "document_id": "doc-publish",
                                "chunk_indices": [1],
                            }],
                            review_status="draft",
                        ),
                        ExamQuestion(
                            id="other-draft",
                            question_type="judgment",
                            topic="程序",
                            stem="另一题",
                            options={},
                            correct_answer=True,
                            source_refs=[{
                                "knowledge_base_id": "kb-exam",
                                "document_id": "doc-other",
                                "chunk_indices": [1],
                            }],
                            review_status="draft",
                        ),
                    ]
                )

        tool = GenerateExamBankTool(session_factory=factory)
        result = await tool.execute(
            context=SimpleNamespace(runtime_mode="enforcement_exam", user_identifier="u-1"),
            action="publish",
            bank_id="doc-publish",
            confirm_publish=True,
        )

        assert result["success"] is True
        assert result["data"]["published_question_count"] == 1
        async with factory() as session:
            assert (await session.get(ExamQuestion, "draft-publish")).review_status == "published"
            assert (await session.get(ExamQuestion, "other-draft")).review_status == "draft"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_question_bank_catalog_marks_drafts_not_selectable():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[KnowledgeBase.__table__, ExamQuestion.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with session.begin():
                session.add(
                    KnowledgeBase(
                        id="kb-exam",
                        name="执法知识",
                        kb_type=KnowledgeBaseType.PUBLIC,
                        status=KnowledgeBaseStatus.ACTIVE,
                        vector_store_scope=KnowledgeBaseStorageScope.SHARED,
                        qdrant_collection="kb-exam-collection",
                    )
                )
                session.add(
                    ExamQuestion(
                        id="draft-question",
                        question_type="judgment",
                        topic="程序",
                        stem="草稿题",
                        options={},
                        correct_answer=True,
                        source_refs=[{
                            "knowledge_base_id": "kb-exam",
                            "document_id": "doc-draft",
                            "document_title": "草稿题库",
                            "exam_outline": {
                                "category": "法学基础和法律法规",
                                "knowledge_point": "行政处罚程序",
                                "importance_level": "core",
                                "importance_reasons": ["核心执法程序"],
                            },
                        }],
                        review_status="draft",
                    )
                )
            async with session.begin():
                banks = await list_exam_question_banks(session, include_drafts=True)
                assert banks[0]["selectable"] is False
                assert banks[0]["review_status"] == "draft"
                assert banks[0]["outline"]["question_count"] == 1
                assert banks[0]["outline"]["categories"][0]["topics"][0]["knowledge_points"] == ["行政处罚程序"]
    finally:
        await engine.dispose()

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.business_rule_service import BusinessRuleService
from app.knowledge_base.models import KnowledgeBase


class FakeRuleLLM:
    async def call_llm_with_json_response(self, prompt, max_retries=2):
        return {
            "kind": "conditional_constraint",
            "summary": "厂界噪声结果按功能区和昼夜时段评价",
            "applies_to": ["monitoring_result"],
            "conditions": ["存在功能区类别", "存在昼夜时段"],
            "required_logic": ["使用对应限值评价"],
            "forbidden_logic": [],
        }


@pytest.fixture
async def rule_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            KnowledgeBase(
                id="kb1",
                name="规则知识库",
                qdrant_collection="kb1",
                scene_status="ready",
                graph_schema={"allowed_entity_types": ["monitoring_result"]},
            )
        )
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_rule_is_draft_until_user_confirms(rule_session):
    service = BusinessRuleService(rule_session, llm=FakeRuleLLM())
    rule = await service.parse_rule(
        "kb1",
        "工业企业厂界噪声结果应按功能区类别和昼夜时段使用对应限值评价。",
        created_by="u1",
    )
    assert rule.status == "draft"
    assert rule.structured_rule["kind"] == "conditional_constraint"
    await service.confirm_rule(rule.id, expected_version=1)
    kb = await rule_session.get(KnowledgeBase, "kb1")
    assert kb.rule_version == 1


@pytest.mark.asyncio
async def test_archived_rule_is_not_in_active_extraction_context(rule_session):
    service = BusinessRuleService(rule_session, llm=FakeRuleLLM())
    rule = await service.parse_rule("kb1", "按昼夜时段评价", created_by="u1")
    await service.confirm_rule(rule.id, expected_version=1)
    await service.archive_rule(rule.id)
    assert await service.active_rule_context("kb1") == []

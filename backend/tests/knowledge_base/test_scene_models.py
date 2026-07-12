from app.knowledge_base.graph_models import KnowledgeGraphEntity, KnowledgeGraphRelation
from app.knowledge_base.models import KnowledgeBase
from app.knowledge_base.scene_models import (
    KnowledgeBusinessRule,
    KnowledgeGraphExtractionRun,
    KnowledgeSceneProfile,
    KnowledgeSchemaSuggestion,
    KnowledgeUserFact,
)


def test_scene_tables_and_kb_state_contract():
    assert KnowledgeBase.__table__.c.scene_status.default.arg == "awaiting_documents"
    assert KnowledgeBase.__table__.c.scene_profile_version.default.arg == 0
    assert KnowledgeBase.__table__.c.schema_version.default.arg == 0
    assert KnowledgeSceneProfile.__tablename__ == "knowledge_scene_profiles"
    assert KnowledgeBusinessRule.__tablename__ == "knowledge_business_rules"
    assert KnowledgeUserFact.__tablename__ == "knowledge_user_facts"
    assert KnowledgeSchemaSuggestion.__tablename__ == "knowledge_schema_suggestions"
    assert KnowledgeGraphExtractionRun.__tablename__ == "knowledge_graph_extraction_runs"
    assert KnowledgeUserFact.__table__.c.review_status.default.arg == "draft"
    assert KnowledgeGraphEntity.__table__.c.source_type.default.arg == "document_fact"
    assert KnowledgeGraphRelation.__table__.c.source_type.default.arg == "document_fact"
    assert KnowledgeGraphRelation.__table__.c.schema_version.default.arg == 0

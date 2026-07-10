from app.db.database import Base


def test_unified_graph_tables_and_constraints_are_registered():
    from app.knowledge_base.graph_models import (
        KnowledgeChunk,
        KnowledgeGraphEntity,
        KnowledgeGraphEntityMention,
        KnowledgeGraphRelation,
        KnowledgeGraphRelationMention,
        KnowledgeIndexOutbox,
    )

    expected = {
        "knowledge_chunks",
        "knowledge_graph_entities",
        "knowledge_graph_relations",
        "knowledge_graph_entity_mentions",
        "knowledge_graph_relation_mentions",
        "knowledge_index_outbox",
    }

    assert expected <= set(Base.metadata.tables)
    assert KnowledgeChunk.__table__.c.content_generation.nullable is False
    assert KnowledgeGraphEntity.__table__.c.kb_id.nullable is False
    assert KnowledgeGraphRelation.__table__.c.source_entity_id.nullable is False
    assert KnowledgeGraphEntityMention.__table__.c.chunk_id.nullable is False
    assert KnowledgeGraphRelationMention.__table__.c.chunk_id.nullable is False
    assert KnowledgeIndexOutbox.__table__.c.payload_version.nullable is False


def test_knowledge_base_and_document_have_graph_state_columns():
    from app.knowledge_base.models import Document, KnowledgeBase

    assert KnowledgeBase.__table__.c.graph_enabled.default.arg is True
    assert "graph_schema" in KnowledgeBase.__table__.c
    assert "graph_extractor_config" in KnowledgeBase.__table__.c
    assert "graph_updated_at" in KnowledgeBase.__table__.c
    assert "content_generation" in Document.__table__.c
    assert "ingestion_status" in Document.__table__.c
    assert "graph_status" in Document.__table__.c
    assert "processing_error" in Document.__table__.c

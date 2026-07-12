"""Relational fact models for knowledge-base chunks and knowledge graphs."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.db.database import Base


def new_id() -> str:
    return str(uuid4())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_key",
            name="uq_knowledge_chunk_document_key",
        ),
        Index(
            "ix_knowledge_chunk_kb_status",
            "kb_id",
            "vector_status",
            "graph_status",
        ),
    )

    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_generation = Column(Integer, nullable=False)
    chunk_key = Column(String(96), nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_text = Column(Text, nullable=False)
    context_prefix = Column(Text, nullable=False, default="")
    start_char = Column(Integer)
    end_char = Column(Integer)
    page_number = Column(Integer)
    section_path = Column(JSON, nullable=False, default=list)
    chunk_metadata = Column(JSON, nullable=False, default=dict)
    vector_status = Column(String(20), nullable=False, default="pending")
    graph_status = Column(String(20), nullable=False, default="pending")
    last_error = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class KnowledgeGraphEntity(Base):
    __tablename__ = "knowledge_graph_entities"
    __table_args__ = (
        UniqueConstraint(
            "kb_id",
            "entity_type",
            "normalized_name",
            name="uq_kg_entity_identity",
        ),
        Index("ix_kg_entity_kb_review", "kb_id", "review_status"),
    )

    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type = Column(String(80), nullable=False)
    name = Column(String(512), nullable=False)
    normalized_name = Column(String(512), nullable=False)
    canonical_name = Column(String(512))
    aliases = Column(JSON, nullable=False, default=list)
    description = Column(Text)
    attributes = Column(JSON, nullable=False, default=dict)
    source_type = Column(String(24), nullable=False, default="document_fact")
    scene_profile_version = Column(Integer, nullable=False, default=0, server_default="0")
    schema_version = Column(Integer, nullable=False, default=0, server_default="0")
    rule_version = Column(Integer, nullable=False, default=0, server_default="0")
    review_status = Column(String(20), nullable=False, default="candidate")
    created_by = Column(String(20), nullable=False, default="extractor")
    locked_by_user = Column(Boolean, nullable=False, default=False)
    merged_into_id = Column(
        String(36),
        ForeignKey("knowledge_graph_entities.id", ondelete="SET NULL"),
    )
    mention_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class KnowledgeGraphRelation(Base):
    __tablename__ = "knowledge_graph_relations"
    __table_args__ = (
        UniqueConstraint(
            "kb_id",
            "source_entity_id",
            "relation_type",
            "target_entity_id",
            name="uq_kg_relation_identity",
        ),
        Index("ix_kg_relation_kb_review", "kb_id", "review_status"),
    )

    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_entity_id = Column(
        String(36),
        ForeignKey("knowledge_graph_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_entity_id = Column(
        String(36),
        ForeignKey("knowledge_graph_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type = Column(String(120), nullable=False)
    description = Column(Text)
    attributes = Column(JSON, nullable=False, default=dict)
    source_type = Column(String(24), nullable=False, default="document_fact")
    scene_profile_version = Column(Integer, nullable=False, default=0, server_default="0")
    schema_version = Column(Integer, nullable=False, default=0, server_default="0")
    rule_version = Column(Integer, nullable=False, default=0, server_default="0")
    review_status = Column(String(20), nullable=False, default="candidate")
    created_by = Column(String(20), nullable=False, default="extractor")
    locked_by_user = Column(Boolean, nullable=False, default=False)
    mention_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class KnowledgeGraphEntityMention(Base):
    __tablename__ = "knowledge_graph_entity_mentions"
    __table_args__ = (
        UniqueConstraint("entity_id", "chunk_id", name="uq_kg_entity_mention"),
        Index("ix_kg_entity_mention_document", "kb_id", "document_id"),
    )

    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id = Column(
        String(36),
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id = Column(
        String(36),
        ForeignKey("knowledge_graph_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_text = Column(Text, nullable=False, default="")
    evidence_start = Column(Integer)
    evidence_end = Column(Integer)
    page_number = Column(Integer)
    confidence = Column(Float)
    extractor_name = Column(String(120), nullable=False)
    extraction_run_id = Column(String(36), nullable=False)


class KnowledgeGraphRelationMention(Base):
    __tablename__ = "knowledge_graph_relation_mentions"
    __table_args__ = (
        UniqueConstraint(
            "relation_id",
            "chunk_id",
            name="uq_kg_relation_mention",
        ),
        Index("ix_kg_relation_mention_document", "kb_id", "document_id"),
    )

    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id = Column(
        String(36),
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_id = Column(
        String(36),
        ForeignKey("knowledge_graph_relations.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_text = Column(Text, nullable=False, default="")
    evidence_start = Column(Integer)
    evidence_end = Column(Integer)
    page_number = Column(Integer)
    confidence = Column(Float)
    extractor_name = Column(String(120), nullable=False)
    extraction_run_id = Column(String(36), nullable=False)


class KnowledgeIndexOutbox(Base):
    __tablename__ = "knowledge_index_outbox"
    __table_args__ = (
        UniqueConstraint(
            "record_type",
            "record_id",
            "operation",
            "payload_version",
            name="uq_knowledge_index_outbox_idempotency",
        ),
        Index(
            "ix_knowledge_index_outbox_pending",
            "status",
            "next_retry_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    record_type = Column(String(20), nullable=False)
    record_id = Column(String(36), nullable=False)
    operation = Column(String(10), nullable=False)
    payload_version = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_error = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

"""Persistence models for scene-driven knowledge-graph workflows."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text

from app.db.database import Base


def new_id() -> str:
    return str(uuid4())


class KnowledgeSceneProfile(Base):
    __tablename__ = "knowledge_scene_profiles"
    __table_args__ = (
        UniqueConstraint("kb_id", "version", name="uq_knowledge_scene_profile_version"),
        Index("ix_knowledge_scene_profile_kb_status", "kb_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    scene_goal = Column(Text, nullable=False)
    desired_questions = Column(JSON, nullable=False, default=list)
    business_objects = Column(JSON, nullable=False, default=list)
    business_logic = Column(JSON, nullable=False, default=list)
    ignored_content = Column(JSON, nullable=False, default=list)
    source_document_ids = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="draft")
    discovery_diagnostics = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime)


class KnowledgeBusinessRule(Base):
    __tablename__ = "knowledge_business_rules"
    __table_args__ = (
        Index("ix_knowledge_business_rule_kb_status", "kb_id", "status"),
        Index(
            "uq_knowledge_business_rule_confirmed_version",
            "kb_id",
            "version",
            unique=True,
            postgresql_where=text("status = 'confirmed'"),
        ),
    )

    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_text = Column(Text, nullable=False)
    structured_rule = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="draft")
    version = Column(Integer, nullable=False, default=0)
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime)


class KnowledgeUserFact(Base):
    __tablename__ = "knowledge_user_facts"
    __table_args__ = (Index("ix_knowledge_user_fact_kb_status", "kb_id", "review_status"),)

    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_text = Column(Text, nullable=False)
    structured_fact = Column(JSON, nullable=False)
    entity_link_decisions = Column(JSON, nullable=False, default=list)
    review_status = Column(String(24), nullable=False, default="draft")
    source_type = Column(String(24), nullable=False, default="user_asserted")
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class KnowledgeSchemaSuggestion(Base):
    __tablename__ = "knowledge_schema_suggestions"
    __table_args__ = (Index("ix_knowledge_schema_suggestion_kb_status", "kb_id", "status"),)

    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    suggestion_type = Column(String(32), nullable=False)
    payload = Column(JSON, nullable=False)
    evidence = Column(JSON, nullable=False, default=list)
    status = Column(String(24), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class KnowledgeGraphExtractionRun(Base):
    __tablename__ = "knowledge_graph_extraction_runs"
    __table_args__ = (Index("ix_knowledge_graph_extraction_run_kb_status", "kb_id", "status"),)

    id = Column(String(36), primary_key=True, default=new_id)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String(36), ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    content_generation = Column(Integer, nullable=False)
    scene_profile_version = Column(Integer, nullable=False)
    schema_version = Column(Integer, nullable=False)
    prompt_version = Column(String(40), nullable=False)
    model_name = Column(String(160), nullable=False)
    model_params = Column(JSON, nullable=False, default=dict)
    raw_response = Column(JSON, nullable=False, default=dict)
    parsed_response = Column(JSON, nullable=False, default=dict)
    validation_errors = Column(JSON, nullable=False, default=list)
    token_usage = Column(JSON, nullable=False, default=dict)
    latency_ms = Column(Integer)
    status = Column(String(24), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

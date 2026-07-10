"""Models tracking asynchronous knowledge-graph build jobs."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base


def _new_id() -> str:
    return str(uuid4())


class KnowledgeGraphBuildTask(Base):
    __tablename__ = "knowledge_graph_build_tasks"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','completed','partial','failed','cancelled')", name="ck_kg_build_status"),
        CheckConstraint("mode IN ('pending','reset_and_build')", name="ck_kg_build_mode"),
        Index(
            "uq_kg_build_active_kb",
            "kb_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_kg_build_task_status", "status"),
    )

    id = Column(String(36), primary_key=True, default=_new_id)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="queued")
    mode = Column(String(20), nullable=False, default="pending")
    created_by = Column(String(36), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    total_chunks = Column(Integer, nullable=False, default=0)
    processed_chunks = Column(Integer, nullable=False, default=0)
    failed_chunks = Column(Integer, nullable=False, default=0)
    remaining_chunks = Column(Integer, nullable=False, default=0)
    failed_chunk_ids = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list)
    last_error = Column(Text)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    lease_until = Column(DateTime)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

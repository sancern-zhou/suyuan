"""SQLAlchemy model for task review records.

NOTE (deployment reconstruction 2026-09-20): the upstream ``project/jiangsu-ops``
branch never committed this file — ``app/db/models/__init__.py`` and
``app/services/task_review.py`` reference it, but ``.gitignore`` or an oversight
kept it out of every branch. This module was reconstructed on the deployment
server from the full set of usages in ``app/services/task_review.py`` (the
``_db_save_review`` values dict enumerates every promoted column). Reconcile
against the developer's original before further schema changes.
"""
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base


class TaskReviewDB(Base):
    __tablename__ = "task_reviews"

    review_id = Column(String(255), primary_key=True)
    subject_id = Column(String(255), nullable=False, server_default="")
    event_id = Column(String(255), nullable=True)

    category = Column(String(120), nullable=False, server_default="", index=True)
    title = Column(String(500), nullable=True)
    summary = Column(Text, nullable=True)

    status = Column(String(32), nullable=False, index=True)
    decision = Column(String(64), nullable=True)
    comment = Column(Text, nullable=True)

    task_id = Column(String(255), nullable=False, server_default="", index=True)
    task_name = Column(String(255), nullable=True)
    execution_id = Column(String(255), nullable=True)
    version = Column(Integer, nullable=False, server_default="1")

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    allow_archived_review_reopen = Column(Boolean, nullable=False, server_default="true")

    submission = Column(JSONB, nullable=True)
    checks = Column(JSONB, nullable=True)
    data_impact = Column(JSONB, nullable=True)
    evidence = Column(JSONB, nullable=True)
    actions = Column(JSONB, nullable=True)
    sections = Column(JSONB, nullable=True)
    review_basis = Column(JSONB, nullable=True)

    # decide_review 写入结构化决策 dict（与 human_feedback/operations 同构），
    # 必须是 JSONB；曾误建为 varchar(64) 导致人工决策 500（2026-10-07 迁移 020 修正）。
    human_decision = Column(JSONB, nullable=True)
    human_feedback = Column(JSONB, nullable=True)
    operations = Column(JSONB, nullable=True)
    history = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_task_reviews_task_updated", "task_id", updated_at.desc()),
        Index("ix_task_reviews_status_updated", "status", updated_at.desc()),
    )

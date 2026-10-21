"""Long-lived personal matters, independent of short-lived spawn execution records."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.db.database import Base


class AssistantTaskDB(Base):
    __tablename__ = "assistant_tasks"

    task_id = Column(String(36), primary_key=True)
    project_id = Column(String(100), nullable=False)
    owner_user_id = Column(String(255), nullable=False)
    source_session_id = Column(String(255), nullable=False)
    request_key = Column(String(64), nullable=False)
    goal = Column(Text, nullable=False)
    completion_criteria = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="ready")
    next_step = Column(Text, nullable=False, default="")
    result_summary = Column(Text, nullable=False, default="")
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "owner_user_id", "request_key", name="uq_assistant_task_request"
        ),
        Index("ix_assistant_tasks_owner_updated", "project_id", "owner_user_id", "updated_at"),
    )


class AssistantTaskEventDB(Base):
    __tablename__ = "assistant_task_events"

    event_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("assistant_tasks.task_id"), nullable=False)
    version = Column(Integer, nullable=False)
    kind = Column(String(32), nullable=False)
    source_session_id = Column(String(255), nullable=False)
    source_request_id = Column(String(128), nullable=False)
    user_message = Column(Text, nullable=False)
    changes = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("task_id", "version", name="uq_assistant_task_event_version"),
    )

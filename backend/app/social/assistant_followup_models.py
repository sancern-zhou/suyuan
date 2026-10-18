"""Durable triggers, occurrences and owner-only notifications."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from app.db.database import Base


class AssistantTriggerDB(Base):
    __tablename__ = "assistant_triggers"

    trigger_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("assistant_tasks.task_id"), nullable=False)
    request_key = Column(String(64), nullable=False, unique=True)
    kind = Column(String(16), nullable=False)
    action = Column(String(16), nullable=False)
    instructions = Column(Text, nullable=False)
    schedule = Column(JSON, nullable=False)
    next_at = Column(DateTime, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    definition_hash = Column(String(64), nullable=False)
    recipient = Column(String(255), nullable=False)
    grant_session_id = Column(String(255), nullable=False)
    grant_request_id = Column(String(128), nullable=False)
    grant_message = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_result_hash = Column(String(64), nullable=True)

    __table_args__ = (Index("ix_assistant_trigger_due", "enabled", "next_at"),)


class AssistantRunDB(Base):
    __tablename__ = "assistant_runs"

    run_id = Column(String(36), primary_key=True)
    trigger_id = Column(String(36), ForeignKey("assistant_triggers.trigger_id"), nullable=False)
    task_id = Column(String(36), ForeignKey("assistant_tasks.task_id"), nullable=False)
    occurrence_key = Column(String(100), nullable=False)
    state = Column(String(24), nullable=False, default="queued")
    task_version = Column(Integer, nullable=True)
    lease_token = Column(String(36), nullable=True)
    lease_until = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("trigger_id", "occurrence_key", name="uq_assistant_run_occurrence"),
        Index("ix_assistant_run_queue", "state", "created_at"),
        Index(
            "uq_assistant_running_task",
            "task_id",
            unique=True,
            postgresql_where=text("state = 'running'"),
            sqlite_where=text("state = 'running'"),
        ),
    )


class AssistantOutboxDB(Base):
    __tablename__ = "assistant_outbox"

    message_id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("assistant_runs.run_id"), nullable=False, unique=True)
    task_id = Column(String(36), ForeignKey("assistant_tasks.task_id"), nullable=False)
    trigger_id = Column(String(36), ForeignKey("assistant_triggers.trigger_id"), nullable=False)
    recipient = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    state = Column(String(24), nullable=False, default="pending")
    lease_token = Column(String(36), nullable=True)
    lease_until = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("ix_assistant_outbox_pending", "state", "available_at"),)

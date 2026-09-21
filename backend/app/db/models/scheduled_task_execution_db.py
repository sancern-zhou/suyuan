"""SQLAlchemy model for scheduled task execution records.

Replaces the single-file ``executions.json`` store: rows are written
individually, concurrent web/worker access is safe, and there is no global
record cap forcing unrelated tasks to evict each other. Promoted columns
carry the fields used for filtering/sorting/pagination; the full
``TaskExecution`` document is kept in ``data`` for lossless restore.
"""
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text, JSON

from app.db.database import Base


class ScheduledTaskExecutionDB(Base):
    __tablename__ = "scheduled_task_executions"

    execution_id = Column(String(255), primary_key=True)
    task_id = Column(String(255), nullable=False, index=True)
    task_name = Column(String(255), nullable=False, server_default="")
    session_id = Column(String(255), nullable=True)

    status = Column(String(32), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    trigger_type = Column(String(32), nullable=False, server_default="scheduled")
    event_id = Column(String(240), nullable=True)
    event_type = Column(String(120), nullable=True)

    total_steps = Column(Integer, nullable=False, default=0)
    completed_steps = Column(Integer, nullable=False, default=0)
    failed_steps = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)

    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index(
            "ix_scheduled_task_executions_task_started",
            "task_id",
            started_at.desc(),
        ),
        Index(
            "ix_scheduled_task_executions_started",
            started_at.desc(),
        ),
    )

"""SQLAlchemy model for structured scheduled-task results.

One row per finished execution; promoted columns back the result query
filters (status/pollutant/station/time ranges) while list-shaped payloads
are stored as JSON documents.
"""
from sqlalchemy import Column, DateTime, Index, String, Text, JSON

from app.db.database import Base


class ScheduledTaskResultDB(Base):
    __tablename__ = "scheduled_task_results"

    execution_id = Column(String(255), primary_key=True)
    task_id = Column(String(255), nullable=False, index=True)
    task_name = Column(String(255), nullable=False, server_default="")
    session_id = Column(String(255), nullable=True)

    status = Column(String(32), nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    city = Column(String(120), nullable=True)
    station_id = Column(String(120), nullable=True, index=True)
    station_name = Column(String(255), nullable=True)
    pollutant = Column(String(120), nullable=True, index=True)

    conclusion = Column(Text, nullable=True)
    conclusion_source = Column(String(64), nullable=True)

    broadcast_message = Column(Text, nullable=True)
    broadcast_image_paths = Column(JSON, nullable=False, default=list)

    findings = Column(JSON, nullable=False, default=list)
    image_paths = Column(JSON, nullable=False, default=list)
    document_paths = Column(JSON, nullable=False, default=list)
    evidence_package_paths = Column(JSON, nullable=False, default=list)
    report_refs = Column(JSON, nullable=False, default=list)

    trigger_type = Column(String(32), nullable=False, server_default="scheduled")
    event_id = Column(String(240), nullable=True)
    event_type = Column(String(120), nullable=True)

    extra = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index(
            "ix_scheduled_task_results_task_completed",
            "task_id",
            "completed_at",
        ),
        Index(
            "ix_scheduled_task_results_completed",
            "completed_at",
        ),
    )

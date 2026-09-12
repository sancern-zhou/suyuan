"""Database models for per-user scheduled report results."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SocialReportResult(Base):
    __tablename__ = "social_report_results"

    report_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    execution_id: Mapped[str] = mapped_column(String(255), nullable=False)
    task_name: Mapped[str] = mapped_column(String(500), nullable=False)
    report_type: Mapped[str] = mapped_column(String(100), nullable=False, default="scheduled_report")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attachments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_social_report_owner_generated", "owner_user_id", "generated_at"),
        Index("ix_social_report_owner_type_generated", "owner_user_id", "report_type", "generated_at"),
    )

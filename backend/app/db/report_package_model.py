"""Database index for published report packages."""
from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base


class ReportPackageDB(Base):
    __tablename__ = "report_packages"

    report_id = Column(String(255), primary_key=True)
    title = Column(String(512), nullable=False)
    report_type = Column(String(120), nullable=False, server_default="other")
    source = Column(String(120), nullable=False, server_default="")
    task_id = Column(String(255), nullable=True)
    execution_id = Column(String(255), nullable=True)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(40), nullable=False, server_default="published")
    version = Column(Integer, nullable=False, server_default="1")
    files = Column(JSONB, nullable=False, default=dict)
    extra_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_report_packages_updated", updated_at.desc()),
        Index("ix_report_packages_type_updated", report_type, updated_at.desc()),
        Index("ix_report_packages_task_period", task_id, period_start, period_end),
    )

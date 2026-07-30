from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class PermitCrawlRun(Base):
    __tablename__ = "permit_crawl_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    phase = Column(String(16), nullable=False)
    province_code = Column(String(12), nullable=False, default="410000000000")
    city_code = Column(String(12), nullable=False, default="411000000000")
    start_page = Column(Integer)
    max_pages = Column(Integer)
    max_licenses = Column(Integer)
    status = Column(String(24), nullable=False, default="running")
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime)
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    stop_reason = Column(Text)


class PermitLicense(Base):
    __tablename__ = "permit_licenses"
    id = Column(String(36), primary_key=True, default=_uuid)
    source_data_id = Column(String(64), nullable=False, unique=True, index=True)
    province_code = Column(String(12), nullable=False, default="410000000000")
    province_name = Column(String(64), nullable=False)
    city_code = Column(String(12), nullable=False, default="411000000000")
    city_name = Column(String(64), nullable=False)
    permit_number = Column(String(64), nullable=False, index=True)
    unified_social_credit_code = Column(String(18), index=True)
    enterprise_name = Column(Text, nullable=False)
    production_site_address = Column(Text)
    industry_category = Column(Text)
    valid_from = Column(Date)
    valid_to = Column(Date)
    issue_date = Column(Date)
    management_category = Column(String(32))
    current_status = Column(String(32), nullable=False, default="unknown")
    latest_business_type = Column(String(64))
    detail_url = Column(Text, nullable=False)
    list_page_no = Column(Integer, nullable=False)
    detail_status = Column(String(24), nullable=False, default="pending")
    documents_status = Column(String(24), nullable=False, default="pending")
    first_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("ix_permit_licenses_pending", "detail_status", "documents_status"),)


class PermitLicenseVersion(Base):
    __tablename__ = "permit_license_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    license_id = Column(String(36), ForeignKey("permit_licenses.id", ondelete="CASCADE"), nullable=False)
    version_no = Column(Integer)
    permit_number = Column(String(64))
    business_type = Column(String(64), nullable=False)
    completion_date = Column(Date)
    valid_from = Column(Date)
    valid_to = Column(Date)
    source_order = Column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("license_id", "source_order", name="uq_permit_version_source_order"),
    )


class PermitPollutionDetail(Base):
    __tablename__ = "permit_pollution_details"
    license_id = Column(String(36), ForeignKey("permit_licenses.id", ondelete="CASCADE"), primary_key=True)
    main_pollutant_categories = Column(Text)
    air_pollutant_types = Column(Text)
    air_emission_pattern = Column(Text)
    air_emission_standard = Column(Text)
    water_pollutant_types = Column(Text)
    water_emission_pattern = Column(Text)
    water_emission_standard = Column(Text)
    emission_rights_info = Column(Text)
    parsed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    source_html_sha256 = Column(String(64), nullable=False)


class PermitDocument(Base):
    __tablename__ = "permit_documents"
    id = Column(String(36), primary_key=True, default=_uuid)
    license_id = Column(String(36), ForeignKey("permit_licenses.id", ondelete="CASCADE"), nullable=False)
    document_type = Column(String(32), nullable=False)
    page_no = Column(Integer, nullable=False, default=0)
    source_url = Column(Text)
    relative_path = Column(Text, nullable=False)
    mime_type = Column(String(128))
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False, default="complete")
    downloaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("license_id", "document_type", "page_no", name="uq_permit_document_page"),
    )


class PermitCrawlFailure(Base):
    __tablename__ = "permit_crawl_failures"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(String(36), ForeignKey("permit_crawl_runs.id", ondelete="CASCADE"), nullable=False)
    license_id = Column(String(36), ForeignKey("permit_licenses.id", ondelete="SET NULL"))
    stage = Column(String(32), nullable=False)
    request_url = Column(Text)
    error_type = Column(String(128), nullable=False)
    error_summary = Column(Text, nullable=False)
    retry_count = Column(Integer, nullable=False, default=0)
    first_occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    next_retry_at = Column(DateTime)


PERMIT_TABLES = (
    PermitCrawlRun.__table__,
    PermitLicense.__table__,
    PermitLicenseVersion.__table__,
    PermitPollutionDetail.__table__,
    PermitDocument.__table__,
    PermitCrawlFailure.__table__,
)

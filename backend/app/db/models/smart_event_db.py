"""SQLAlchemy models for the smart event store (events / task cards / state).

NOTE (deployment reconstruction 2026-09-20): the upstream ``project/jiangsu-ops``
branch never committed this file, although ``app/db/models/__init__.py``,
``app/db/database.py`` (create_all) and ``app/services/smart_event_db.py`` all
import it. Reconstructed on the deployment server from the full set of usages
in ``app/services/smart_event_db.py`` (``_event_row_values`` /
``_task_row_values`` enumerate the promoted columns; table names come from
``import_store_from_files_async`` which drops ``smart_events``,
``smart_event_tasks``, ``smart_event_state``). JSONB is required: the service
uses ``data["review_id"].astext`` and ``jsonb_extract_path_text``. Reconcile
against the developer's original before further schema changes.
"""
from sqlalchemy import Boolean, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base


class SmartEventDB(Base):
    __tablename__ = "smart_events"

    event_id = Column(String(255), primary_key=True)
    data = Column(JSONB, nullable=False)

    event_status = Column(String(64), nullable=True, index=True)
    event_type = Column(String(120), nullable=True, index=True)
    ai_event_type = Column(String(120), nullable=True)
    ai_suggested_level = Column(String(32), nullable=True)

    site_id = Column(String(120), nullable=True, index=True)
    site_name = Column(String(255), nullable=True)
    event_name = Column(String(500), nullable=True)
    initial_event_name = Column(String(500), nullable=True)
    primary_clue_tag = Column(String(255), nullable=True)
    source_alarm_rule_type = Column(String(255), nullable=True)

    latest_occurrence_time = Column(DateTime, nullable=True)
    event_start_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    archived = Column(Boolean, nullable=False, server_default="false")
    evidence = Column(JSONB, nullable=True)
    evidence_package_path = Column(String(1000), nullable=True)

    __table_args__ = (
        Index("ix_smart_events_time", latest_occurrence_time.desc(), event_start_time.desc()),
    )


class SmartEventTaskDB(Base):
    __tablename__ = "smart_event_tasks"

    task_id = Column(String(255), primary_key=True)
    data = Column(JSONB, nullable=False)

    event_id = Column(String(255), nullable=True, index=True)
    status = Column(String(64), nullable=True, index=True)
    scheduled_task_id = Column(String(255), nullable=True)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class SmartEventStateDB(Base):
    __tablename__ = "smart_event_state"

    key = Column(String(255), primary_key=True)
    value = Column(JSONB, nullable=True)

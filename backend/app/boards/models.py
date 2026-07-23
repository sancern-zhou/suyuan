from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Board(Base):
    __tablename__ = "drawio_boards"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(255), nullable=False, unique=True, index=True)
    title = Column(Text, nullable=False, default="Draw.io Board")
    current_version_id = Column(String(36), nullable=True)
    revision = Column(Integer, nullable=False, default=0)
    draft_xml_ref = Column(JSON, nullable=True)
    draft_sha256 = Column(String(64), nullable=True)
    draft_revision = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    versions = relationship(
        "BoardVersion",
        back_populates="board",
        cascade="all, delete-orphan",
        order_by="BoardVersion.version_number",
    )


class BoardVersion(Base):
    __tablename__ = "drawio_board_versions"

    id = Column(String(36), primary_key=True, default=_uuid)
    board_id = Column(
        String(36),
        ForeignKey("drawio_boards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    parent_version_id = Column(String(36), nullable=True)
    restored_from_version_id = Column(String(36), nullable=True)
    source = Column(String(32), nullable=False)
    lifecycle_status = Column(String(24), nullable=False)
    xml_ref = Column(JSON, nullable=False)
    xml_sha256 = Column(String(64), nullable=False, index=True)
    screenshot_ref = Column(JSON, nullable=True)
    quality_status = Column(String(24), nullable=False, default="pending")
    quality_report = Column(JSON, nullable=False, default=dict)
    agent_run_id = Column(String(255), nullable=True, index=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    accepted_at = Column(DateTime, nullable=True)

    board = relationship("Board", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("board_id", "version_number", name="uq_drawio_board_version_number"),
        Index("ix_drawio_board_versions_history", "board_id", "lifecycle_status", "version_number"),
    )

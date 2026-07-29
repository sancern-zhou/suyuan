"""Database model for the authoritative conversation catalog."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text

from app.db.database import Base


class ConversationCatalogDB(Base):
    __tablename__ = "conversation_catalog"

    session_id = Column(String(255), primary_key=True)
    owner_user_id = Column(String(255), nullable=False)
    owner_username = Column(String(255), nullable=False)
    owner_display_name = Column(String(255), nullable=False)
    source = Column(String(32), nullable=False)
    mode = Column(String(50), nullable=True)
    title = Column(Text, nullable=True)
    read_only_on_web = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index(
            "ix_conversation_catalog_owner_updated",
            "owner_user_id",
            "updated_at",
        ),
        Index("ix_conversation_catalog_source_updated", "source", "updated_at"),
    )

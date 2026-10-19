"""Owner-scoped replies, independent of execution and external delivery status."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, JSON, String, Text

from app.db.database import Base


class AssistantNotificationDB(Base):
    __tablename__ = "assistant_notifications"

    message_id = Column(String(255), primary_key=True)
    project_id = Column(String(100), nullable=False)
    owner_user_id = Column(String(255), nullable=False)
    source_session_id = Column(String(255), nullable=False)
    recipient = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    state = Column(String(24), nullable=False, default="pending")
    lease_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    read_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_assistant_notifications_owner", "project_id", "owner_user_id", "created_at"),
        Index("ix_assistant_notifications_delivery", "project_id", "state"),
    )

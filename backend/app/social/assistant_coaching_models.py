"""Personal coaching choices; separate from execution and authorization records."""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, UniqueConstraint

from app.db.database import Base


class AssistantCoachingOwnerDB(Base):
    __tablename__ = "assistant_coaching_owners"
    project_id = Column(String(100), primary_key=True)
    owner_user_id = Column(String(255), primary_key=True)
    revision = Column(Integer, nullable=False, default=0)


class AssistantSuggestionDB(Base):
    __tablename__ = "assistant_suggestions"
    suggestion_id = Column(String(36), primary_key=True)
    project_id = Column(String(100), nullable=False)
    owner_user_id = Column(String(255), nullable=False)
    dedup_key = Column(String(64), nullable=False)
    capability_id = Column(String(255), nullable=False)
    capability_revision = Column(String(64), nullable=False)
    goal = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    suggested_prompt = Column(Text, nullable=False)
    missing_inputs = Column(JSON, nullable=False)
    state = Column(String(32), nullable=False, default="pending")
    version = Column(Integer, nullable=False, default=1)
    source_session_id = Column(String(255), nullable=False)
    source_request_id = Column(String(128), nullable=False)
    source_user_message = Column(Text, nullable=False)
    decision_session_id = Column(String(255), nullable=True)
    decision_request_id = Column(String(128), nullable=True)
    decision_user_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "project_id", "owner_user_id", "dedup_key", name="uq_assistant_suggestion_dedup"
        ),
    )

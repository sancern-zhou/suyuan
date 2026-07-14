"""Stable contracts for the cross-source conversation catalog."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ConversationSource(str, Enum):
    WEB = "web"
    KNOWLEDGE_QA = "knowledge_qa"
    SOCIAL = "social"


class ConversationCatalogRecord(BaseModel):
    session_id: str
    owner_user_id: str
    owner_username: str
    owner_display_name: str
    source: ConversationSource
    mode: str | None = None
    title: str | None = None
    read_only_on_web: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

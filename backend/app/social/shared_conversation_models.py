"""Database models for the shared conversation board (共享对话面板).

A share is a snapshot of one conversation, copied at share time so later
edits or deletion of the original session never change what was shared.
Chart and attachment files are copied into a per-share directory under
DATA_REGISTRY_DIR so resource GC cannot break old shares.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

# Share lifecycle: active → withdrawn (by owner) / removed (by admin).
SHARE_STATUS_ACTIVE = "active"
SHARE_STATUS_WITHDRAWN = "withdrawn"
SHARE_STATUS_REMOVED = "removed"


class SocialSharedConversation(Base):
    __tablename__ = "social_shared_conversations"

    share_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_username: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    owner_display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="social")
    mode: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    first_question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    attachments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=SHARE_STATUS_ACTIVE, index=True)
    removed_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_social_shared_status_created", "status", "created_at"),
        Index("ix_social_shared_owner", "owner_user_id"),
    )

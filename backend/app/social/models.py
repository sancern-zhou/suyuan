"""Database models for social platform integration."""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Index, Integer
from app.db.database import Base


class SocialSessionMapping(Base):
    """
    Social platform user to agent session mapping.

    This table stores the mapping between social platform user IDs
    and ReActAgent session IDs for multi-turn conversation support.
    """

    __tablename__ = "social_session_mappings"

    social_user_id = Column(String(255), primary_key=True, nullable=False)
    """Social platform user ID (e.g., "qq:123456", "weixin:789012")"""

    session_id = Column(String(255), nullable=False, index=True)
    """Agent session ID"""

    last_used = Column(DateTime, default=datetime.now, nullable=False)
    """Last used timestamp for session expiry"""

    # ✅ 新增字段：记忆整合追踪
    last_consolidated_offset = Column(Integer, default=0, nullable=False)
    """Last consolidated message offset (for incremental consolidation)"""

    total_message_count = Column(Integer, default=0, nullable=False)
    """Total message count for this session"""

    # Index for efficient cleanup of expired sessions
    __table_args__ = (
        Index('idx_social_session_mappings_last_used', 'last_used'),
    )

    def __repr__(self):
        return f"<SocialSessionMapping(social_user_id={self.social_user_id}, session_id={self.session_id})>"

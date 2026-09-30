"""Runtime storage for project-scoped coordinator quick prompts."""

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text

from app.db.database import Base


class CoordinatorQuickPromptDB(Base):
    __tablename__ = "coordinator_quick_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(100), nullable=False, index=True)
    surface = Column(String(16), nullable=False, default="home", server_default="home")
    label = Column(String(30), nullable=False)
    prompt = Column(Text, nullable=False)
    mode = Column(String(100), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_coordinator_quick_prompts_scope", "project_id", "surface", "mode"),
        Index("ix_coordinator_quick_prompts_order", "project_id", "surface", "sort_order"),
    )

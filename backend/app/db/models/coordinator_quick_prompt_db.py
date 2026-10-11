"""SQLAlchemy model for coordinator quick prompts (常用问题).

Runtime source of truth for quick prompts shown in two surfaces:

- ``home``: coordinator home page quick prompts (label + prompt + optional
  mode switch), seeded from the manifest's
  ``frontend.coordinator.quick_prompts`` on first read.
- ``input``: per-agent-mode suggestions above the chat input box (label is
  the button text, prompt is filled into the composer), seeded from
  ``INPUT_QUICK_PROMPT_DEFAULTS`` in ``app.api.coordinator_config_routes``.

Admin edits only touch this table, never the manifest or hardcoded lists.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, text

from app.db.database import Base


class CoordinatorQuickPromptDB(Base):
    __tablename__ = "coordinator_quick_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(64), nullable=False, index=True)
    surface = Column(String(16), nullable=False, server_default="home")
    label = Column(String(60), nullable=False)
    prompt = Column(Text, nullable=False)
    mode = Column(String(64), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        # Labels are unique within (project, surface, mode); COALESCE keeps
        # NULL-mode home rows in the same key space. Must match the CREATE
        # UNIQUE INDEX in _ensure_coordinator_quick_prompts_schema.
        Index(
            "uq_coordinator_quick_prompts_scope_label",
            "project_id",
            "surface",
            text("COALESCE(mode, '')"),
            "label",
            unique=True,
        ),
    )

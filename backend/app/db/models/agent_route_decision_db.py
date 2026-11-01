"""SQLAlchemy model for delegation route-decision audit rows.

One row per top-level delegation (call_sub_agent / run_agent_workflow) from a
parent mode to child modes; workflow nodes and assistant-run internal
executions are not recorded. Clean schemas get the table via init_db
create_all; managed deployments apply
``app/db/migrations/026_create_agent_route_decisions.sql``.
"""
from sqlalchemy import Column, DateTime, Index, JSON, String

from app.db.database import Base


class AgentRouteDecisionDB(Base):
    __tablename__ = "agent_route_decisions"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(255), nullable=True)
    user_identifier = Column(String(255), nullable=True)
    parent_mode = Column(String(64), nullable=True)
    target_modes = Column(JSON, nullable=False, default=list)
    reason_code = Column(String(64), nullable=False)
    reason_values = Column(JSON, nullable=False, default=dict)
    route_hint = Column(String(255), nullable=True)
    created_at = Column(
        DateTime, nullable=False, server_default="CURRENT_TIMESTAMP"
    )

    __table_args__ = (
        Index(
            "ix_agent_route_decisions_session_created",
            "session_id",
            "created_at",
        ),
        Index("ix_agent_route_decisions_reason", "reason_code"),
    )

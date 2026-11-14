"""SQLAlchemy model for delegation route-decision audit rows.

One row per top-level delegation (call_sub_agent / run_agent_workflow) from a
parent mode to child modes; workflow nodes and assistant-run internal
executions are not recorded. Clean schemas get the table via init_db
create_all; managed deployments apply
``app/db/migrations/026_create_agent_route_decisions.sql``.
"""
from sqlalchemy import Column, DateTime, Index, JSON, String, text

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
    # text() 使 DDL 渲染为裸 DEFAULT CURRENT_TIMESTAMP；裸字符串会被
    # asyncpg 方言加引号成字面量 'CURRENT_TIMESTAMP'，全新建库即报
    # InvalidDatetimeFormatError（已存在表不受影响，故生产此前未暴露）。
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        Index(
            "ix_agent_route_decisions_session_created",
            "session_id",
            "created_at",
        ),
        Index("ix_agent_route_decisions_reason", "reason_code"),
    )

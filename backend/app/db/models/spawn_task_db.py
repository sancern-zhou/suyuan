"""SQLAlchemy model for background subagent (spawn) task rows.

取代此前的进程内 JSON 存储（``backend_data_registry/spawn_tasks.json``）：
Web/App 助手会话派发的后台任务必须跨进程可见（多 uvicorn worker 时，
派发与查询可能落在不同进程），且需要长期回查，属于业务事实而非常态
缓存，因此落 PostgreSQL。表结构对齐
``app/db/migrations/004_create_spawn_tasks.sql``（外部管理 schema 的部署
直接跑该迁移；全新建库由 init_db create_all 建表）。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Index, String, Text, text

from app.db.database import Base


class SpawnTaskDB(Base):
    __tablename__ = "spawn_tasks"

    task_id = Column(String(100), primary_key=True)
    social_user_id = Column(String(200), nullable=False)
    task = Column(Text, nullable=False)
    label = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, server_default="pending")
    progress = Column(Float, nullable=True, server_default="0")
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    origin_channel = Column(String(50), nullable=False)
    origin_chat_id = Column(String(200), nullable=False)
    origin_sender_id = Column(String(200), nullable=False)
    bot_account = Column(String(200), nullable=True)

    __table_args__ = (
        Index("idx_spawn_tasks_status", "status"),
        Index("idx_spawn_tasks_user", "social_user_id"),
        Index("idx_spawn_tasks_created", "created_at"),
        Index("idx_spawn_tasks_user_status", "social_user_id", "status"),
    )

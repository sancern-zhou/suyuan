"""
会话数据库模型

使用 PostgreSQL 存储会话和消息，支持：
- Anthropic 原生 content blocks 格式
- 分页查询消息
- 高效索引查询
- 事务处理

设计原则：
- role 字段：Anthropic API 角色（user/assistant），用于 LLM 对话恢复
- msg_type 字段：语义类型（user/thought/action/observation/tool_result/final），用于前端展示和查询过滤
- content 字段：JSONB 类型，原生支持 str 和 list（Anthropic content blocks）
"""

from sqlalchemy import Column, String, DateTime, Integer, Text, JSON, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class SessionResourceDB(Base):
    """One immutable member of a versioned session resource group."""

    __tablename__ = "session_resources"

    resource_id = Column(String(64), primary_key=True)
    session_id = Column(String(255), nullable=False)
    group_id = Column(String(64), nullable=False)
    parent_resource_id = Column(
        String(64),
        ForeignKey("session_resources.resource_id", ondelete="CASCADE"),
        nullable=True,
    )
    resource_key = Column(String(255), nullable=False)
    relation = Column(String(32), nullable=False)
    kind = Column(String(32), nullable=False, index=True)
    role = Column(String(32), nullable=False)
    label = Column(String(512), nullable=False)
    locator = Column(JSONB, nullable=False)
    format = Column(String(64), nullable=False)
    media_type = Column(String(255), nullable=False)
    renderer = Column(String(64), nullable=False, index=True)
    capabilities = Column(JSONB, nullable=False, default=list)
    resource_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    tool_name = Column(String(255), nullable=False, default="")
    run_id = Column(String(255), nullable=False)
    turn_sequence = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "group_id",
            "version",
            "resource_key",
            name="uq_session_resource_group_member",
        ),
        Index("ix_session_resources_catalog", "session_id", "status", "updated_at"),
        Index("ix_session_resources_group", "session_id", "group_id", "version"),
    )


class SessionResourceVersionDB(Base):
    """Monotonic coordination version; it contains no resource payload."""

    __tablename__ = "session_resource_versions"

    session_id = Column(String(255), primary_key=True)
    version = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SessionDB(Base):
    """
    会话主表

    存储会话的基本信息和元数据
    """
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)

    # 基本信息
    query = Column(Text, nullable=False)

    # 时间信息
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 执行上下文
    mode = Column(String(50), nullable=True)  # 助手模式/专家模式
    current_step = Column(String(255), nullable=True)
    current_expert = Column(String(100), nullable=True)

    # 错误信息
    error = Column(JSON, nullable=True)  # Dict[str, Any]

    # 元数据（重命名避免与 SQLAlchemy 保留字冲突）
    session_metadata = Column("metadata", JSON, nullable=True)  # Dict[str, Any]

    # 关联消息（一对多）
    messages = relationship("SessionMessageDB", back_populates="session", cascade="all, delete-orphan")

    # 索引
    __table_args__ = (
        Index('ix_sessions_mode_created', 'mode', 'created_at'),
    )


class SessionMessageDB(Base):
    """
    会话消息表

    存储每条消息的详细信息，完整兼容 Anthropic 原生格式：
    - role: Anthropic 角色（user/assistant）
    - msg_type: 语义类型（user/thought/action/observation/tool_result/final）
    - content: JSONB，支持纯文本字符串和 Anthropic content blocks 列表
    """
    __tablename__ = "session_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('sessions.session_id', ondelete='CASCADE'), nullable=False, index=True)

    # Anthropic 角色：user / assistant
    role = Column(String(20), nullable=False, index=True)

    # 语义类型：user / thought / action / observation / tool_result / final
    msg_type = Column(String(30), nullable=False, index=True)

    # 消息内容：JSONB 支持纯文本 (str) 和 Anthropic content blocks (list[dict])
    content = Column(JSON, nullable=True)

    # 消息数据（JSON 格式，存储完整的 data 字段）
    data = Column(JSON, nullable=True)

    # 时间戳
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 消息元数据（重命名避免与 SQLAlchemy 保留字冲突）
    msg_metadata = Column("metadata", JSON, nullable=True)  # Dict[str, Any]

    # 排序字段（用于保持消息顺序）
    sequence_number = Column(Integer, nullable=False, index=True)

    # 关联会话（多对一）
    session = relationship("SessionDB", back_populates="messages")

    # 索引
    __table_args__ = (
        Index('ix_session_messages_session_sequence', 'session_id', 'sequence_number'),
        Index('ix_session_messages_role_timestamp', 'role', 'timestamp'),
        Index('ix_session_messages_type_timestamp', 'msg_type', 'timestamp'),
    )

"""
会话数据库模型

使用 PostgreSQL 存储会话和消息，支持：
- 分页查询消息
- 高效索引查询
- 事务处理
"""

from sqlalchemy import Column, String, DateTime, Integer, Text, JSON, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class MessageType(str, enum.Enum):
    """消息类型枚举"""
    USER = "user"
    FINAL = "final"
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"


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

    # 结果数据引用
    data_ids = Column(JSON, nullable=True)  # List[str]
    visual_ids = Column(JSON, nullable=True)  # List[str]
    office_documents = Column(JSON, nullable=True)  # List[Dict[str, Any]] - Office文档PDF预览数据

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

    存储每条消息的详细信息，支持分页查询
    """
    __tablename__ = "session_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('sessions.session_id', ondelete='CASCADE'), nullable=False, index=True)

    # 消息类型和内容
    message_type = Column(SQLEnum(MessageType), nullable=False, index=True)
    content = Column(Text, nullable=True)

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
        Index('ix_session_messages_type_timestamp', 'message_type', 'timestamp'),
    )

"""
知识库数据模型

定义知识库和文档的SQLAlchemy模型。
"""

from sqlalchemy import (
    Column, String, DateTime, Integer, JSON, ForeignKey,
    Text, Enum, Boolean, BigInteger
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.db.database import Base


class KnowledgeBaseStatus(enum.Enum):
    """知识库状态"""
    ACTIVE = "active"
    BUILDING = "building"
    FAILED = "failed"
    ARCHIVED = "archived"


class KnowledgeBaseType(enum.Enum):
    """知识库类型"""
    PUBLIC = "public"    # 公共知识库：所有用户可见
    PRIVATE = "private"  # 个人知识库：仅创建者可见


class DocumentStatus(enum.Enum):
    """文档处理状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChunkingStrategy(enum.Enum):
    """分块策略

    说明：
    - 与 app.knowledge_base.schemas.ChunkingStrategyEnum 保持一致
    - 新增 LLM 策略，用于在知识库级别标记“优先使用 LLM 分块”
    """
    SEMANTIC = "semantic"    # 语义分块（慢但精准）
    SENTENCE = "sentence"    # 句子分块（快，默认）
    MARKDOWN = "markdown"    # Markdown标题分块
    HYBRID = "hybrid"        # 混合：先按标题，再按句子
    LLM = "llm"              # LLM 智能分块（需要结合文档上传时的 llm_mode 使用）


class KnowledgeBase(Base):
    """知识库模型"""
    __tablename__ = "knowledge_bases"

    id = Column(String(36), primary_key=True)
    name = Column(String(128), nullable=False, index=True)
    description = Column(Text, default="")

    # 类型和权限
    kb_type = Column(
        Enum(KnowledgeBaseType),
        default=KnowledgeBaseType.PRIVATE,
        index=True
    )
    owner_id = Column(String(36), nullable=True, index=True)  # 公共知识库为null
    is_default = Column(Boolean, default=False)  # 是否默认启用

    # 配置
    embedding_model = Column(String(64), default="BAAI/bge-m3")
    chunking_strategy = Column(
        Enum(ChunkingStrategy),
        default=ChunkingStrategy.SENTENCE
    )
    chunk_size = Column(Integer, default=256)
    chunk_overlap = Column(Integer, default=64)

    # Qdrant Collection名称
    qdrant_collection = Column(String(128), unique=True, nullable=False)

    # 状态统计
    status = Column(
        Enum(KnowledgeBaseStatus),
        default=KnowledgeBaseStatus.ACTIVE,
        index=True
    )
    document_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    total_size = Column(BigInteger, default=0)  # 总文件大小（字节）

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    documents = relationship(
        "Document",
        back_populates="knowledge_base",
        cascade="all, delete-orphan"
    )

    @property
    def is_public(self) -> bool:
        """是否为公共知识库"""
        return self.kb_type == KnowledgeBaseType.PUBLIC

    @property
    def is_private(self) -> bool:
        """是否为个人知识库"""
        return self.kb_type == KnowledgeBaseType.PRIVATE

    def __repr__(self):
        return f"<KnowledgeBase(id={self.id}, name={self.name}, type={self.kb_type.value})>"


class Document(Base):
    """文档模型"""
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True)
    knowledge_base_id = Column(
        String(36),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 文件信息
    filename = Column(String(256), nullable=False)
    file_path = Column(String(512))  # 存储路径
    file_type = Column(String(32), index=True)  # pdf, docx, xlsx, etc.
    file_size = Column(BigInteger, default=0)  # 文件大小（字节）
    file_hash = Column(String(64))  # MD5哈希，用于去重

    # 文件存储字段（新增）
    original_file_oid = Column(BigInteger, nullable=True)  # PostgreSQL Large Object ID
    file_storage_type = Column(String(20), default="database")  # database/local/oss
    file_mime_type = Column(String(100))  # MIME类型
    file_checksum = Column(String(64))  # SHA256校验和
    storage_size = Column(BigInteger, default=0)  # 实际存储大小
    file_preview_text = Column(Text)  # 文件预览文本

    # 处理状态
    status = Column(
        Enum(DocumentStatus),
        default=DocumentStatus.PENDING,
        index=True
    )
    chunk_count = Column(Integer, default=0)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # 元数据（用户自定义）
    extra_metadata = Column(JSON, default=dict)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")

    def __repr__(self):
        return f"<Document(id={self.id}, filename={self.filename}, status={self.status.value})>"


# ========================================
# 对话会话模型 (知识问答连续对话)
# ========================================

class ConversationSessionStatus(enum.Enum):
    """对话会话状态"""
    ACTIVE = "active"      # 活跃会话
    ARCHIVED = "archived"  # 已归档
    EXPIRED = "expired"    # 已过期


class ConversationSession(Base):
    """知识问答对话会话模型"""
    __tablename__ = "knowledge_conversation_sessions"

    id = Column(String(36), primary_key=True)
    title = Column(String(256), nullable=False, default="新对话")  # 会话标题(首轮问题)
    status = Column(
        Enum(ConversationSessionStatus),
        default=ConversationSessionStatus.ACTIVE,
        index=True
    )

    # 使用的知识库列表
    knowledge_base_ids = Column(JSON, default=list)

    # 统计信息
    total_turns = Column(Integer, default=0)  # 总轮次数

    # 最后的问题（用于会话列表显示）
    last_query = Column(Text, default="")

    # 用户ID（支持多用户场景）
    user_id = Column(String(36), nullable=True, index=True)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, index=True)  # 过期时间，用于自动清理

    # 关联
    turns = relationship(
        "ConversationTurn",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ConversationTurn.turn_index"
    )

    def __repr__(self):
        return f"<ConversationSession(id={self.id}, title={self.title}, status={self.status.value})>"


class ConversationTurn(Base):
    """对话轮次模型"""
    __tablename__ = "knowledge_conversation_turns"

    id = Column(String(36), primary_key=True)
    session_id = Column(
        String(36),
        ForeignKey("knowledge_conversation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    turn_index = Column(Integer, nullable=False)  # 轮次序号(从1开始)
    role = Column(String(20), nullable=False)  # user / assistant

    # 对话内容
    content = Column(Text, nullable=False)

    # 参考来源（assistant轮次）
    sources = Column(JSON, default=list)
    sources_count = Column(Integer, default=0)

    # 查询元数据（user轮次）
    query_metadata = Column(JSON, default=dict)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # 关联
    session = relationship("ConversationSession", back_populates="turns")

    def __repr__(self):
        return f"<ConversationTurn(id={self.id}, session_id={self.session_id}, turn_index={self.turn_index}, role={self.role})>"

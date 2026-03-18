"""
知识库模块

提供知识库管理、文档处理、向量存储和检索功能。
"""

from .models import (
    KnowledgeBase,
    Document,
    KnowledgeBaseStatus,
    KnowledgeBaseType,
    DocumentStatus,
    ChunkingStrategy
)
from .schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseResponse,
    DocumentCreate,
    DocumentResponse,
    SearchRequest,
    SearchResult
)

# 全局单例
_vector_store = None
_document_processor = None


def get_vector_store():
    """获取全局VectorStore实例（单例）"""
    global _vector_store
    if _vector_store is None:
        from .vector_store import KnowledgeVectorStore
        _vector_store = KnowledgeVectorStore()
    return _vector_store


def get_document_processor():
    """获取全局DocumentProcessor实例（单例）"""
    global _document_processor
    if _document_processor is None:
        from .document_processor import DocumentProcessor
        _document_processor = DocumentProcessor()
    return _document_processor


__all__ = [
    # Models
    "KnowledgeBase",
    "Document",
    "KnowledgeBaseStatus",
    "KnowledgeBaseType",
    "DocumentStatus",
    "ChunkingStrategy",
    # Schemas
    "KnowledgeBaseCreate",
    "KnowledgeBaseUpdate",
    "KnowledgeBaseResponse",
    "DocumentCreate",
    "DocumentResponse",
    "SearchRequest",
    "SearchResult",
    # Singletons
    "get_vector_store",
    "get_document_processor",
]

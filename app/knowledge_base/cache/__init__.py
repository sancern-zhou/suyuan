"""
知识库缓存模块
提供多级缓存支持：L1内存缓存、L2 Redis缓存
"""

from .layered_cache import (
    MemoryCache,
    RedisCache,
    LayeredCache,
    QueryCacheService,
    EmbeddingCache,
    HotKnowledgeBasePreloader,
    get_layered_cache,
    get_query_cache,
    get_embedding_cache,
    get_hot_preloader
)

__all__ = [
    "MemoryCache",
    "RedisCache",
    "LayeredCache",
    "QueryCacheService",
    "EmbeddingCache",
    "HotKnowledgeBasePreloader",
    "get_layered_cache",
    "get_query_cache",
    "get_embedding_cache",
    "get_hot_preloader"
]

"""
多级缓存系统
L1: 内存缓存（LRU，毫秒级响应）
L2: Redis缓存（分布式，秒级响应）
"""

import os
import json
import hashlib
import asyncio
from typing import Optional, Any, Dict, List, Callable
from datetime import datetime, timedelta
from collections import OrderedDict
from functools import wraps
import structlog

logger = structlog.get_logger()


class MemoryCache:
    """L1内存缓存 - LRU策略"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认过期时间（秒）
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict = OrderedDict()
        self._expiry: Dict[str, datetime] = {}
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key not in self._cache:
            self._misses += 1
            return None

        # 检查是否过期
        if key in self._expiry and datetime.now() > self._expiry[key]:
            self._delete(key)
            self._misses += 1
            return None

        # LRU: 移动到末尾
        self._cache.move_to_end(key)
        self._hits += 1
        return self._cache[key]

    def set(self, key: str, value: Any, ttl: int = None) -> None:
        """设置缓存值"""
        ttl = ttl or self.default_ttl

        # 如果已存在，先删除
        if key in self._cache:
            self._delete(key)

        # LRU淘汰
        while len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            self._delete(oldest_key)

        self._cache[key] = value
        self._expiry[key] = datetime.now() + timedelta(seconds=ttl)

    def delete(self, key: str) -> bool:
        """删除缓存"""
        return self._delete(key)

    def _delete(self, key: str) -> bool:
        """内部删除方法"""
        if key in self._cache:
            del self._cache[key]
            self._expiry.pop(key, None)
            return True
        return False

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._expiry.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4)
        }


class RedisCache:
    """L2 Redis缓存"""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        db: int = None,
        password: str = None,
        default_ttl: int = 3600,
        key_prefix: str = "kb:"
    ):
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.db = db or int(os.getenv("REDIS_DB", "0"))
        self.password = password or os.getenv("REDIS_PASSWORD") or None
        self.default_ttl = default_ttl
        self.key_prefix = key_prefix
        self._redis = None
        self._connected = False

    async def _get_redis(self):
        """获取Redis连接"""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    decode_responses=False  # 返回bytes以支持二进制数据
                )
                await self._redis.ping()
                self._connected = True
                logger.info("redis_connected", host=self.host, port=self.port)
            except Exception as e:
                logger.warning("redis_connection_failed", error=str(e))
                self._redis = None
                self._connected = False
        return self._redis

    def _make_key(self, key: str) -> str:
        """生成带前缀的key"""
        return f"{self.key_prefix}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        redis = await self._get_redis()
        if not redis:
            return None

        try:
            full_key = self._make_key(key)
            data = await redis.get(full_key)
            if data:
                return json.loads(data.decode('utf-8'))
            return None
        except Exception as e:
            logger.warning("redis_get_failed", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存值"""
        redis = await self._get_redis()
        if not redis:
            return False

        try:
            full_key = self._make_key(key)
            ttl = ttl or self.default_ttl
            data = json.dumps(value, ensure_ascii=False, default=str)
            await redis.setex(full_key, ttl, data.encode('utf-8'))
            return True
        except Exception as e:
            logger.warning("redis_set_failed", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """删除缓存"""
        redis = await self._get_redis()
        if not redis:
            return False

        try:
            full_key = self._make_key(key)
            result = await redis.delete(full_key)
            return result > 0
        except Exception as e:
            logger.warning("redis_delete_failed", key=key, error=str(e))
            return False

    async def get_bytes(self, key: str) -> Optional[bytes]:
        """获取二进制缓存（用于Embedding向量）"""
        redis = await self._get_redis()
        if not redis:
            return None

        try:
            full_key = self._make_key(key)
            return await redis.get(full_key)
        except Exception as e:
            logger.warning("redis_get_bytes_failed", key=key, error=str(e))
            return None

    async def set_bytes(self, key: str, value: bytes, ttl: int = None) -> bool:
        """设置二进制缓存（用于Embedding向量）"""
        redis = await self._get_redis()
        if not redis:
            return False

        try:
            full_key = self._make_key(key)
            ttl = ttl or self.default_ttl
            await redis.setex(full_key, ttl, value)
            return True
        except Exception as e:
            logger.warning("redis_set_bytes_failed", key=key, error=str(e))
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """清除匹配模式的所有key"""
        redis = await self._get_redis()
        if not redis:
            return 0

        try:
            full_pattern = self._make_key(pattern)
            keys = []
            async for key in redis.scan_iter(match=full_pattern):
                keys.append(key)
            if keys:
                return await redis.delete(*keys)
            return 0
        except Exception as e:
            logger.warning("redis_clear_pattern_failed", pattern=pattern, error=str(e))
            return 0

    async def close(self):
        """关闭连接"""
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._connected = False


class LayeredCache:
    """多级缓存管理器"""

    def __init__(
        self,
        l1_max_size: int = 1000,
        l1_ttl: int = 300,
        l2_ttl: int = 3600,
        enable_l2: bool = True
    ):
        """
        Args:
            l1_max_size: L1缓存最大条目数
            l1_ttl: L1缓存TTL（秒）
            l2_ttl: L2缓存TTL（秒）
            enable_l2: 是否启用L2 Redis缓存
        """
        self.l1 = MemoryCache(max_size=l1_max_size, default_ttl=l1_ttl)
        self.l2 = RedisCache(default_ttl=l2_ttl) if enable_l2 else None
        self.l2_ttl = l2_ttl

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存（L1 -> L2）"""
        # L1查找
        value = self.l1.get(key)
        if value is not None:
            return value

        # L2查找
        if self.l2:
            value = await self.l2.get(key)
            if value is not None:
                # 回填L1
                self.l1.set(key, value)
                return value

        return None

    async def set(self, key: str, value: Any, l1_ttl: int = None, l2_ttl: int = None) -> None:
        """设置缓存（同时写入L1和L2）"""
        self.l1.set(key, value, ttl=l1_ttl)
        if self.l2:
            await self.l2.set(key, value, ttl=l2_ttl or self.l2_ttl)

    async def delete(self, key: str) -> None:
        """删除缓存"""
        self.l1.delete(key)
        if self.l2:
            await self.l2.delete(key)

    async def clear(self, pattern: str = None) -> None:
        """清空缓存"""
        self.l1.clear()
        if self.l2 and pattern:
            await self.l2.clear_pattern(pattern)

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "l1": self.l1.get_stats(),
            "l2_enabled": self.l2 is not None,
            "l2_connected": self.l2._connected if self.l2 else False
        }


class QueryCacheService:
    """查询结果缓存服务"""

    def __init__(self, cache: LayeredCache = None):
        self.cache = cache or LayeredCache()

    def _make_query_key(self, query: str, kb_ids: List[str] = None, **kwargs) -> str:
        """生成查询缓存key"""
        key_parts = [
            "query",
            query,
            ",".join(sorted(kb_ids)) if kb_ids else "all"
        ]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")

        key_str = ":".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()

    async def get_search_result(
        self,
        query: str,
        kb_ids: List[str] = None,
        **kwargs
    ) -> Optional[List[Dict]]:
        """获取搜索结果缓存"""
        key = self._make_query_key(query, kb_ids, **kwargs)
        return await self.cache.get(f"search:{key}")

    async def set_search_result(
        self,
        query: str,
        results: List[Dict],
        kb_ids: List[str] = None,
        ttl: int = 600,
        **kwargs
    ) -> None:
        """缓存搜索结果"""
        key = self._make_query_key(query, kb_ids, **kwargs)
        await self.cache.set(f"search:{key}", results, l1_ttl=60, l2_ttl=ttl)

    async def invalidate_kb(self, kb_id: str) -> None:
        """使知识库相关缓存失效"""
        # 清除包含该知识库的所有缓存
        await self.cache.clear(f"search:*{kb_id}*")
        logger.info("kb_cache_invalidated", kb_id=kb_id)


class EmbeddingCache:
    """Embedding向量缓存"""

    def __init__(self, redis_cache: RedisCache = None, ttl: int = 86400):
        """
        Args:
            redis_cache: Redis缓存实例
            ttl: 缓存过期时间（默认24小时）
        """
        self.redis = redis_cache or RedisCache(key_prefix="emb:", default_ttl=ttl)
        self.ttl = ttl
        self._local_cache = MemoryCache(max_size=500, default_ttl=600)

    def _make_key(self, text: str, model: str = "default") -> str:
        """生成Embedding缓存key"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"{model}:{text_hash}"

    async def get(self, text: str, model: str = "default") -> Optional[List[float]]:
        """获取缓存的Embedding向量"""
        key = self._make_key(text, model)

        # L1查找
        cached = self._local_cache.get(key)
        if cached is not None:
            return cached

        # L2查找
        try:
            import numpy as np
            data = await self.redis.get_bytes(key)
            if data:
                embedding = np.frombuffer(data, dtype=np.float32).tolist()
                self._local_cache.set(key, embedding)
                return embedding
        except Exception as e:
            logger.warning("embedding_cache_get_failed", error=str(e))

        return None

    async def set(self, text: str, embedding: List[float], model: str = "default") -> bool:
        """缓存Embedding向量"""
        key = self._make_key(text, model)

        # L1缓存
        self._local_cache.set(key, embedding)

        # L2缓存
        try:
            import numpy as np
            data = np.array(embedding, dtype=np.float32).tobytes()
            return await self.redis.set_bytes(key, data, ttl=self.ttl)
        except Exception as e:
            logger.warning("embedding_cache_set_failed", error=str(e))
            return False

    async def get_batch(
        self,
        texts: List[str],
        model: str = "default"
    ) -> Dict[str, Optional[List[float]]]:
        """批量获取Embedding缓存"""
        results = {}
        for text in texts:
            results[text] = await self.get(text, model)
        return results

    async def set_batch(
        self,
        embeddings: Dict[str, List[float]],
        model: str = "default"
    ) -> int:
        """批量缓存Embedding"""
        success_count = 0
        for text, embedding in embeddings.items():
            if await self.set(text, embedding, model):
                success_count += 1
        return success_count

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "local_cache": self._local_cache.get_stats(),
            "redis_connected": self.redis._connected
        }


class HotKnowledgeBasePreloader:
    """热点知识库预加载器"""

    def __init__(
        self,
        cache: LayeredCache = None,
        preload_threshold: int = 10,
        preload_interval: int = 300
    ):
        """
        Args:
            cache: 缓存实例
            preload_threshold: 访问次数阈值，超过则预加载
            preload_interval: 预加载检查间隔（秒）
        """
        self.cache = cache or LayeredCache()
        self.preload_threshold = preload_threshold
        self.preload_interval = preload_interval
        self._access_counts: Dict[str, int] = {}
        self._preloaded_kbs: set = set()
        self._running = False

    def record_access(self, kb_id: str) -> None:
        """记录知识库访问"""
        self._access_counts[kb_id] = self._access_counts.get(kb_id, 0) + 1

    def get_hot_kbs(self, top_n: int = 5) -> List[str]:
        """获取热点知识库列表"""
        sorted_kbs = sorted(
            self._access_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [kb_id for kb_id, count in sorted_kbs[:top_n]
                if count >= self.preload_threshold]

    async def preload_kb_metadata(self, kb_id: str, metadata: Dict) -> None:
        """预加载知识库元数据"""
        await self.cache.set(
            f"kb_meta:{kb_id}",
            metadata,
            l1_ttl=600,
            l2_ttl=3600
        )
        self._preloaded_kbs.add(kb_id)
        logger.info("kb_metadata_preloaded", kb_id=kb_id)

    async def get_kb_metadata(self, kb_id: str) -> Optional[Dict]:
        """获取预加载的知识库元数据"""
        self.record_access(kb_id)
        return await self.cache.get(f"kb_meta:{kb_id}")

    async def start_preload_task(self, get_kb_metadata_func: Callable):
        """启动预加载后台任务"""
        if self._running:
            return

        self._running = True
        logger.info("hot_kb_preloader_started")

        while self._running:
            try:
                hot_kbs = self.get_hot_kbs()
                for kb_id in hot_kbs:
                    if kb_id not in self._preloaded_kbs:
                        metadata = await get_kb_metadata_func(kb_id)
                        if metadata:
                            await self.preload_kb_metadata(kb_id, metadata)

                await asyncio.sleep(self.preload_interval)
            except Exception as e:
                logger.error("preload_task_error", error=str(e))
                await asyncio.sleep(60)

    def stop_preload_task(self):
        """停止预加载任务"""
        self._running = False
        logger.info("hot_kb_preloader_stopped")

    def get_stats(self) -> Dict[str, Any]:
        """获取预加载统计"""
        return {
            "access_counts": dict(self._access_counts),
            "preloaded_count": len(self._preloaded_kbs),
            "hot_kbs": self.get_hot_kbs(),
            "running": self._running
        }


# 全局单例
_layered_cache: Optional[LayeredCache] = None
_query_cache: Optional[QueryCacheService] = None
_embedding_cache: Optional[EmbeddingCache] = None
_hot_preloader: Optional[HotKnowledgeBasePreloader] = None


def get_layered_cache() -> LayeredCache:
    """获取多级缓存单例"""
    global _layered_cache
    if _layered_cache is None:
        _layered_cache = LayeredCache()
    return _layered_cache


def get_query_cache() -> QueryCacheService:
    """获取查询缓存服务单例"""
    global _query_cache
    if _query_cache is None:
        _query_cache = QueryCacheService(get_layered_cache())
    return _query_cache


def get_embedding_cache() -> EmbeddingCache:
    """获取Embedding缓存单例"""
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = EmbeddingCache()
    return _embedding_cache


def get_hot_preloader() -> HotKnowledgeBasePreloader:
    """获取热点预加载器单例"""
    global _hot_preloader
    if _hot_preloader is None:
        _hot_preloader = HotKnowledgeBasePreloader(get_layered_cache())
    return _hot_preloader

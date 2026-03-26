"""Query result caching for social platforms."""

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass

import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)


@dataclass
class CacheEntry:
    """A cache entry."""

    key: str
    value: Any
    timestamp: float
    ttl: int

    def is_expired(self) -> bool:
        """Check if entry is expired."""
        return time.time() - self.timestamp > self.ttl


class SimpleCache:
    """
    Simple in-memory cache for query results.

    Features:
    - TTL-based expiration
    - Automatic cleanup
    - Thread-safe operations
    """

    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        self._cache: Dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None
    ) -> None:
        """Set a value in cache."""
        async with self._lock:
            ttl = ttl or self._default_ttl
            self._cache[key] = CacheEntry(
                key=key,
                value=value,
                timestamp=time.time(),
                ttl=ttl
            )

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()

    async def cleanup(self) -> int:
        """Clean up expired entries. Returns number of entries removed."""
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]

            for key in expired_keys:
                del self._cache[key]

            return len(expired_keys)

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        async with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0

            return {
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.2%}",
            }

    def generate_key(self, query: str, platform: str) -> str:
        """Generate a cache key from query and platform."""
        # Create a hash of the query
        hash_obj = hashlib.md5(f"{platform}:{query}".encode())
        return f"cache:{platform}:{hash_obj.hexdigest()}"


class QueryResultCache:
    """
    High-level cache for social platform query results.

    Caches query results to avoid redundant Agent calls.
    """

    def __init__(self, default_ttl: int = 300):  # 5 minutes
        self.cache = SimpleCache(default_ttl=default_ttl)
        self._enabled = True

    async def get_cached_result(
        self,
        query: str,
        platform: str
    ) -> Optional[str]:
        """
        Get cached query result.

        Args:
            query: User query text
            platform: Platform name (qq, weixin, etc.)

        Returns:
            Cached result or None if not found/expired
        """
        if not self._enabled:
            return None

        key = self.cache.generate_key(query, platform)
        result = await self.cache.get(key)

        if result:
            logger.debug("Cache hit", platform=platform, query=query[:50])

        return result

    async def cache_result(
        self,
        query: str,
        platform: str,
        result: str,
        ttl: int | None = None
    ) -> None:
        """
        Cache a query result.

        Args:
            query: User query text
            platform: Platform name
            result: Query result to cache
            ttl: Time to live in seconds
        """
        if not self._enabled:
            return

        key = self.cache.generate_key(query, platform)
        await self.cache.set(key, result, ttl)

        logger.debug("Cached result", platform=platform, ttl=ttl or self.cache._default_ttl)

    async def invalidate(self, query: str, platform: str) -> None:
        """Invalidate a cached query result."""
        key = self.cache.generate_key(query, platform)
        await self.cache.delete(key)

    async def clear_all(self) -> None:
        """Clear all cached results."""
        await self.cache.clear()

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        cache_stats = await self.cache.get_stats()
        return {
            "enabled": self._enabled,
            **cache_stats
        }

    def enable(self) -> None:
        """Enable caching."""
        self._enabled = True

    def disable(self) -> None:
        """Disable caching."""
        self._enabled = False


# Global cache instance
_cache: QueryResultCache | None = None


def get_query_cache() -> QueryResultCache:
    """Get the global query cache instance."""
    global _cache
    if _cache is None:
        # Default TTL: 5 minutes for query results
        _cache = QueryResultCache(default_ttl=300)
    return _cache

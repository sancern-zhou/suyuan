"""会话作用域的图表短别名注册表。

``[[chart:chart_N]]`` 是发给模型的抄写友好标记：模型只需原样复制
``chart_<序号>`` 这样的短串（抄写熵接近零），最终答复在 Finalizer
落库/下发前统一改写回全局唯一 visual_id。历史教训：高熵随机
visual_id 全串（如 ``echarts_hnccwfa3se_0``）模型照抄经常丢段，
前端按精确匹配找不到资源就不渲染（见 app/utils/visual_ids.py docstring）。

隔离保证（跨会话不串）：

- 别名映射按 session_id 隔离存储；两个会话各自的 ``chart_0`` 指向
  各自的 visual_id，解析只发生在本会话请求内，落库/下发的永远是全串；
- 会话内序号单调递增（Redis INCR），计数器不设置 TTL，映射过期后
  也不复用旧序号，避免旧标记指向新图；
- 映射 HASH 带独立 TTL（每次 bind 刷新），不随运行结束丢失；
- web 多 worker 部署依赖 Redis 共享；Redis 不可用时不分配新别名，
  工具继续返回真实 visual_id，避免多个 worker 的本地计数器重号。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

import structlog

from app.utils.visual_ids import chart_reference_sub

logger = structlog.get_logger(__name__)

# 别名形式：chart_<序号>。同时必须满足 [[chart:<id>]] 协议字符集
# （VISUAL_ID_PATTERN，契约测试钉住），这里收紧为纯数字序号。
ALIAS_ID_PATTERN = re.compile(r"chart_[0-9]{1,18}")

_MAX_ALIASES_PER_BIND = 50


def is_alias_id(candidate: str) -> bool:
    return bool(ALIAS_ID_PATTERN.fullmatch(str(candidate or "")))


class InMemoryVisualAliasStore:
    """进程内存储，仅用于显式选择的单进程场景和单元测试。"""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._mappings: dict[str, dict[str, str]] = {}

    async def allocate(self, session_id: str, count: int) -> list[int]:
        start = self._counters.get(session_id, 0)
        self._counters[session_id] = start + count
        return list(range(start, start + count))

    async def store(self, session_id: str, mapping: dict[str, str]) -> None:
        self._mappings.setdefault(session_id, {}).update(mapping)

    async def lookup(self, session_id: str, aliases: list[str]) -> dict[str, str]:
        mapping = self._mappings.get(session_id) or {}
        return {alias: mapping[alias] for alias in aliases if alias in mapping}


class RedisVisualAliasStore:
    """跨 uvicorn worker 共享的 Redis 存储。

    - ``<prefix>:seq:<session_id>``：会话级单调计数器（INCR），保证跨轮不重号；
    - ``<prefix>:map:<session_id>``：别名 → visual_id HASH，TTL 随每次写入刷新。
    """

    def __init__(self, redis_client: Any, *, key_prefix: str, ttl_seconds: int) -> None:
        self.redis = redis_client
        self.key_prefix = key_prefix.rstrip(":")
        self.ttl_seconds = max(60, int(ttl_seconds))

    def _hash_key(self, session_id: str) -> str:
        return f"{self.key_prefix}:map:{session_id}"

    def _seq_key(self, session_id: str) -> str:
        return f"{self.key_prefix}:seq:{session_id}"

    async def allocate(self, session_id: str, count: int) -> list[int]:
        pipe = self.redis.pipeline(transaction=True)
        for _ in range(count):
            pipe.incr(self._seq_key(session_id))
        results = await pipe.execute()
        return [int(value) - 1 for value in results]

    async def store(self, session_id: str, mapping: dict[str, str]) -> None:
        await self.redis.hset(self._hash_key(session_id), mapping=mapping)
        await self.redis.expire(self._hash_key(session_id), self.ttl_seconds)

    async def lookup(self, session_id: str, aliases: list[str]) -> dict[str, str]:
        if not aliases:
            return {}
        values = await self.redis.hmget(self._hash_key(session_id), list(aliases))
        return {
            alias: str(value)
            for alias, value in zip(aliases, values)
            if value
        }


class VisualAliasRegistry:
    """bind：给一批 visual_id 分配会话级短别名；resolve：别名 → visual_id。

    生产环境只使用 Redis；显式允许时可用进程内存储进行独立测试。
    """

    def __init__(
        self,
        redis_store: Optional[RedisVisualAliasStore] = None,
        *,
        allow_memory: bool = True,
    ) -> None:
        self._redis_store = redis_store
        self._fallback = InMemoryVisualAliasStore() if allow_memory else None

    async def bind(self, session_id: str, visual_ids: Iterable[str]) -> dict[str, str]:
        ids = list(dict.fromkeys(
            value for value in visual_ids if isinstance(value, str) and value
        ))[:_MAX_ALIASES_PER_BIND]
        if not ids or not session_id:
            return {}
        store = self._redis_store or self._fallback
        if store is None:
            return {}
        try:
            seqs = await store.allocate(session_id, len(ids))
            mapping = {
                f"chart_{seq}": visual_id
                for seq, visual_id in zip(seqs, ids)
            }
            await store.store(session_id, mapping)
            return mapping
        except Exception as exc:
            logger.warning(
                "visual_alias_store_bind_failed",
                session_id=session_id,
                store=type(store).__name__,
                error=str(exc),
            )
        return {}

    async def resolve_ids(self, session_id: str, aliases: list[str]) -> dict[str, str]:
        unique = list(dict.fromkeys(alias for alias in aliases if is_alias_id(alias)))
        if not unique or not session_id:
            return {}
        store = self._redis_store or self._fallback
        if store is None:
            return {}
        try:
            return await store.lookup(session_id, unique)
        except Exception as exc:
            logger.warning(
                "visual_alias_store_lookup_failed",
                session_id=session_id,
                store=type(store).__name__,
                error=str(exc),
            )
            return {}


def _create_production_registry() -> VisualAliasRegistry:
    try:
        import redis.asyncio as redis

        from config.settings import settings

        client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        store = RedisVisualAliasStore(
            client,
            key_prefix=settings.agent_visual_alias_redis_prefix,
            ttl_seconds=settings.agent_visual_alias_ttl_seconds,
        )
        return VisualAliasRegistry(redis_store=store, allow_memory=False)
    except Exception as exc:
        logger.warning("visual_alias_redis_unavailable", error=str(exc))
        return VisualAliasRegistry(redis_store=None, allow_memory=False)


visual_alias_registry = _create_production_registry()


async def resolve_chart_alias_markers(
    text: str,
    session_id: str | None,
    registry: VisualAliasRegistry | None = None,
) -> str:
    """把最终答复里的 ``[[chart:chart_N]]`` 改写回全局唯一 visual_id。

    无法解析的标记保持原样（fail-open），由后续模糊修复兜底。
    """
    if not text or "[[chart:" not in text or not session_id:
        return text
    pattern = chart_reference_sub()
    candidates = [
        match.group(1) for match in pattern.finditer(text) if is_alias_id(match.group(1))
    ]
    if not candidates:
        return text
    mapping = await (registry or visual_alias_registry).resolve_ids(session_id, candidates)
    if not mapping:
        return text

    def _replace(match: re.Match) -> str:
        alias = match.group(1)
        return f"[[chart:{mapping[alias]}]]" if alias in mapping else match.group(0)

    resolved = pattern.sub(_replace, text)
    if resolved != text:
        logger.info(
            "chart_alias_markers_resolved",
            session_id=session_id,
            aliases=sorted(mapping),
        )
    return resolved


class ChartAliasStreamFilter:
    """Resolve complete chart markers while retaining markers split across chunks."""

    def __init__(
        self,
        session_id: str,
        registry: VisualAliasRegistry | None = None,
    ) -> None:
        self.session_id = session_id
        self.registry = registry
        self._pending = ""

    async def append(self, chunk: str) -> str:
        self._pending += chunk
        prefix = "[[chart:"
        boundary = len(self._pending)
        marker_start = self._pending.rfind(prefix)
        if marker_start >= 0 and "]]" not in self._pending[marker_start:]:
            if len(self._pending) - marker_start <= 256:
                boundary = marker_start
        else:
            for length in range(min(len(prefix) - 1, len(self._pending)), 0, -1):
                if self._pending.endswith(prefix[:length]):
                    boundary -= length
                    break
        ready, self._pending = self._pending[:boundary], self._pending[boundary:]
        return await resolve_chart_alias_markers(ready, self.session_id, self.registry)

    async def flush(self) -> str:
        pending, self._pending = self._pending, ""
        return await resolve_chart_alias_markers(pending, self.session_id, self.registry)

"""会话作用域的图表短别名注册表。

``[[chart:chart_N]]`` 是发给模型的抄写友好标记：模型只需原样复制
``chart_<序号>`` 这样的短串（抄写熵接近零），最终答复在 Finalizer
落库/下发前统一改写回全局唯一 visual_id。历史教训：高熵随机
visual_id 全串（如 ``echarts_hnccwfa3se_0``）模型照抄经常丢段，
前端按精确匹配找不到资源就不渲染（见 app/utils/visual_ids.py docstring）。

隔离保证（跨会话不串）：

- 别名映射按 session_id 隔离存储；两个会话各自的 ``chart_0`` 指向
  各自的 visual_id，解析只发生在本会话请求内，落库/下发的永远是全串；
- 会话内序号单调递增（Redis INCR），跨轮不重号，历史消息里的旧标记
  仍可解析，不会被本轮图表顶掉；
- 映射 HASH 带独立 TTL（每次 bind 刷新），不随运行结束丢失；
- web 多 worker 部署依赖 Redis 共享；Redis 不可用时降级进程内存储
  （fail-open）：同 worker 内仍可解析，跨 worker 未命中时保持原文，
  由 ``repair_chart_reference_ids`` 模糊修复兜底。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

import structlog

from app.utils.visual_ids import chart_reference_sub

logger = structlog.get_logger(__name__)

# 别名形式：chart_<序号>。同时必须满足 [[chart:<id>]] 协议字符集
# （VISUAL_ID_PATTERN，契约测试钉住），这里收紧为纯数字序号。
ALIAS_ID_PATTERN = re.compile(r"chart_[0-9]{1,6}")

_MAX_ALIASES_PER_BIND = 50


def is_alias_id(candidate: str) -> bool:
    return bool(ALIAS_ID_PATTERN.fullmatch(str(candidate or "")))


class InMemoryVisualAliasStore:
    """进程内存储；Redis 降级兜底与单元测试共用。"""

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
        await self.redis.expire(self._seq_key(session_id), self.ttl_seconds)
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

    Redis 优先，异常/未命中时回退进程内存储（fail-open，永不抛出）。
    """

    def __init__(self, redis_store: Optional[RedisVisualAliasStore] = None) -> None:
        self._redis_store = redis_store
        self._fallback = InMemoryVisualAliasStore()

    async def bind(self, session_id: str, visual_ids: Iterable[str]) -> dict[str, str]:
        ids = [
            vid for vid in dict.fromkeys(visual_ids)
            if isinstance(vid, str) and vid
        ][:_MAX_ALIASES_PER_BIND]
        if not ids or not session_id:
            return {}
        stores = [store for store in (self._redis_store, self._fallback) if store]
        for store in stores:
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
        resolved: dict[str, str] = {}
        for store in (self._redis_store, self._fallback):
            missing = [alias for alias in unique if alias not in resolved]
            if not missing:
                break
            if store is None:
                continue
            try:
                resolved.update(await store.lookup(session_id, missing))
            except Exception as exc:
                logger.warning(
                    "visual_alias_store_lookup_failed",
                    session_id=session_id,
                    store=type(store).__name__,
                    error=str(exc),
                )
        return resolved


def _create_production_registry() -> VisualAliasRegistry:
    try:
        import redis.asyncio as redis

        from config.settings import settings

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        store = RedisVisualAliasStore(
            client,
            key_prefix=settings.agent_visual_alias_redis_prefix,
            ttl_seconds=settings.agent_visual_alias_ttl_seconds,
        )
        return VisualAliasRegistry(redis_store=store)
    except Exception as exc:
        logger.warning("visual_alias_redis_unavailable", error=str(exc))
        return VisualAliasRegistry(redis_store=None)


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

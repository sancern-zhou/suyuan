"""LLM 供应商失败小时桶计数器（Redis）。

在 llm_failover.mark_provider_cooldown 真正标记冷却时计数（429 限流、过载、
超时等都会走到这里；format 类瞬态错误刻意不冷却、不计数）。
供运行监控工具查询"上一时段 LLM 限流/失败次数"。

Redis 不可用时静默跳过——计数是旁路能力，不因 Redis 故障放大 LLM 调用问题。
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import structlog

logger = structlog.get_logger()

# TTL 26 小时：保证跨日后上一整天的小时桶仍可查询。
_TTL_SECONDS = 93600

_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis

        _redis = aioredis.Redis(
            host=os.getenv("REDIS_HOST", "127.0.0.1"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD") or None,
            decode_responses=True,
        )
    return _redis


def _key(now: datetime | None = None) -> str:
    return f"monitor:llm_fail:{(now or datetime.now()).strftime('%Y%m%d%H')}"


async def record_llm_failure(
    provider: str,
    reason: str,
    now: datetime | None = None,
) -> None:
    """按 小时桶/provider:原因 计数 +1；失败只记日志。"""
    try:
        client = _get_redis()
        key = _key(now)
        async with client.pipeline(transaction=True) as pipe:
            pipe.hincrby(key, "total", 1)
            pipe.hincrby(key, f"{provider}:{reason}", 1)
            pipe.expire(key, _TTL_SECONDS)
            await pipe.execute()
    except Exception as exc:  # noqa: BLE001 - 旁路计数不放大故障
        logger.warning("llm_failure_counter_unavailable", error=str(exc))


async def read_llm_failure_buckets(
    hours: int = 24,
) -> dict[str, dict[str, int]]:
    """读取最近 N 小时（含当前小时）的失败计数桶，返回 {yyyyMMddHH: {field: count}}。"""
    try:
        client = _get_redis()
        now = datetime.now()
        keys = [
            _key(now - timedelta(hours=offset))
            for offset in range(max(int(hours), 1))
        ]
        # MGET 不支持 hash，逐个 HGETALL（小时桶数量有限，≤48）
        buckets: dict[str, dict[str, int]] = {}
        for key in keys:
            data = await client.hgetall(key)
            if data:
                buckets[key.split(":")[-1]] = {
                    field: int(count) for field, count in data.items()
                }
        return buckets
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_failure_counter_read_failed", error=str(exc))
        return {}

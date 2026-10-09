"""百度路况接口共享配额计数器（Redis，实时工具与定时抓取共用）。

口径（实施方案 §6.2）：
- key ``baidu_traffic:quota:{YYYYMMDD}``，INCR 后 EXPIRE 172800；
- 定时路径每轮预检查剩余额度（不足则整轮跳过），每次调用前 INCR，>QUOTA_HARDCAP 放弃；
- 实时路径不做预检查（优先放行），INCR 后 >QUOTA_HARDCAP 才拒并提示当日额度用尽；
- Redis 不可用时放行（不因 Redis 故障放大路况数据缺口），仅记 warning。
"""
from __future__ import annotations

import os
from datetime import datetime

import structlog

logger = structlog.get_logger()

# 百度按 AK 计 2000 次/日；硬顶 1900 给实时与应急留余量。调整配额只改这里。
QUOTA_HARDCAP = 1900
QUOTA_TTL_SECONDS = 172800

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
    return f"baidu_traffic:quota:{(now or datetime.now()).strftime('%Y%m%d')}"


async def quota_incr(now: datetime | None = None) -> int | None:
    """计数 +1，返回新值；Redis 不可用返回 None（调用方按放行处理）。"""
    try:
        client = _get_redis()
        key = _key(now)
        value = await client.incr(key)
        if value == 1:
            await client.expire(key, QUOTA_TTL_SECONDS)
        return int(value)
    except Exception as exc:
        logger.warning("baidu_traffic_quota_unavailable", error=str(exc))
        return None


async def quota_remaining(now: datetime | None = None) -> int | None:
    """返回当日剩余额度；Redis 不可用返回 None（视为充足）。"""
    try:
        value = await _get_redis().get(_key(now))
        return QUOTA_HARDCAP - int(value or 0)
    except Exception as exc:
        logger.warning("baidu_traffic_quota_unavailable", error=str(exc))
        return None


async def quota_exceeded(now: datetime | None = None) -> bool:
    """INCR 后判断是否越过硬顶；为 True 时调用方应放弃本次调用。"""
    value = await quota_incr(now)
    return value is not None and value > QUOTA_HARDCAP

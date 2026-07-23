"""Cross-worker active-run steering queues for in-flight agent runs."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

import structlog


logger = structlog.get_logger()
STEERABLE_MODES = {"assistant", "social"}


@dataclass
class SteeringInput:
    content: str
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    input_id: str = field(default_factory=lambda: f"steer_{uuid4().hex}")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> "SteeringInput":
        payload = json.loads(value)
        return cls(
            content=str(payload.get("content") or ""),
            attachments=[
                dict(item)
                for item in payload.get("attachments") or []
                if isinstance(item, dict)
            ],
            created_at=str(payload.get("created_at") or datetime.now().isoformat()),
            input_id=str(payload.get("input_id") or f"steer_{uuid4().hex}"),
        )


@dataclass
class ActiveRun:
    session_id: str
    run_id: str
    mode: str
    status: str = "accepting"
    queue: List[SteeringInput] = field(default_factory=list)


class SteeringStore(Protocol):
    async def register(self, session_id: str, run_id: str, mode: str) -> bool: ...
    async def unregister(self, session_id: str, run_id: str) -> None: ...
    async def add_input(self, session_id: str, item: SteeringInput) -> bool: ...
    async def drain(self, session_id: str, run_id: str) -> List[SteeringInput]: ...
    async def begin_completion(self, session_id: str, run_id: str) -> List[SteeringInput]: ...
    async def close_and_drain(self, session_id: str, run_id: str) -> List[SteeringInput]: ...
    async def mark_closing(self, session_id: str, run_id: str) -> bool: ...
    async def is_active(self, session_id: str, mode: str | None = None) -> bool: ...
    async def aclose(self) -> None: ...


class InMemorySteeringStore:
    """Single-process store retained for isolated unit tests."""

    def __init__(self) -> None:
        self._runs: Dict[str, ActiveRun] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, run_id: str, mode: str) -> bool:
        async with self._lock:
            if mode not in STEERABLE_MODES:
                self._runs.pop(session_id, None)
                return False
            self._runs[session_id] = ActiveRun(session_id=session_id, run_id=run_id, mode=mode)
            return True

    async def unregister(self, session_id: str, run_id: str) -> None:
        async with self._lock:
            active = self._runs.get(session_id)
            if active and active.run_id == run_id:
                self._runs.pop(session_id, None)

    async def add_input(self, session_id: str, item: SteeringInput) -> bool:
        async with self._lock:
            active = self._runs.get(session_id)
            if (
                not active
                or active.mode not in STEERABLE_MODES
                or active.status != "accepting"
            ):
                return False
            active.queue.append(item)
            return True

    async def drain(self, session_id: str, run_id: str) -> List[SteeringInput]:
        async with self._lock:
            active = self._runs.get(session_id)
            if not active or active.run_id != run_id:
                return []
            items = list(active.queue)
            active.queue.clear()
            return items

    async def begin_completion(self, session_id: str, run_id: str) -> List[SteeringInput]:
        async with self._lock:
            active = self._runs.get(session_id)
            if not active or active.run_id != run_id:
                return []
            if active.queue:
                items = list(active.queue)
                active.queue.clear()
                return items
            active.status = "closing"
            return []

    async def mark_closing(self, session_id: str, run_id: str) -> bool:
        async with self._lock:
            active = self._runs.get(session_id)
            if not active or active.run_id != run_id:
                return False
            active.status = "closing"
            return True

    async def close_and_drain(self, session_id: str, run_id: str) -> List[SteeringInput]:
        async with self._lock:
            active = self._runs.get(session_id)
            if not active or active.run_id != run_id:
                return []
            active.status = "closing"
            items = list(active.queue)
            active.queue.clear()
            return items

    async def is_active(self, session_id: str, mode: str | None = None) -> bool:
        async with self._lock:
            active = self._runs.get(session_id)
            if not active or active.status != "accepting":
                return False
            return mode is None or active.mode == mode

    async def aclose(self) -> None:
        return None


class RedisSteeringStore:
    """Redis-backed store whose Lua operations are atomic across workers."""

    REGISTER_SCRIPT = """-- steering:register
if ARGV[4] ~= '1' then
  redis.call('DEL', KEYS[1], KEYS[2])
  return 0
end
redis.call('HSET', KEYS[1], 'run_id', ARGV[1], 'mode', ARGV[2], 'status', 'accepting')
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('DEL', KEYS[2])
return 1
"""
    ADD_SCRIPT = """-- steering:add
if redis.call('HGET', KEYS[1], 'status') ~= 'accepting' then return 0 end
if not redis.call('HGET', KEYS[1], 'run_id') then return 0 end
redis.call('RPUSH', KEYS[2], ARGV[1])
redis.call('EXPIRE', KEYS[2], ARGV[2])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""
    DRAIN_SCRIPT = """-- steering:drain
if redis.call('HGET', KEYS[1], 'run_id') ~= ARGV[1] then return {} end
local items = redis.call('LRANGE', KEYS[2], 0, -1)
redis.call('DEL', KEYS[2])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return items
"""
    BEGIN_COMPLETION_SCRIPT = """-- steering:begin_completion
if redis.call('HGET', KEYS[1], 'run_id') ~= ARGV[1] then return {'missing'} end
local items = redis.call('LRANGE', KEYS[2], 0, -1)
if #items > 0 then
  redis.call('DEL', KEYS[2])
  redis.call('EXPIRE', KEYS[1], ARGV[2])
  local result = {'drained'}
  for _, item in ipairs(items) do table.insert(result, item) end
  return result
end
redis.call('HSET', KEYS[1], 'status', 'closing')
redis.call('EXPIRE', KEYS[1], ARGV[2])
return {'closing'}
"""
    MARK_CLOSING_SCRIPT = """-- steering:mark_closing
if redis.call('HGET', KEYS[1], 'run_id') ~= ARGV[1] then return 0 end
redis.call('HSET', KEYS[1], 'status', 'closing')
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""
    CLOSE_AND_DRAIN_SCRIPT = """-- steering:close_and_drain
if redis.call('HGET', KEYS[1], 'run_id') ~= ARGV[1] then return {} end
local items = redis.call('LRANGE', KEYS[2], 0, -1)
redis.call('DEL', KEYS[2])
redis.call('HSET', KEYS[1], 'status', 'closing')
redis.call('EXPIRE', KEYS[1], ARGV[2])
return items
"""
    UNREGISTER_SCRIPT = """-- steering:unregister
if redis.call('HGET', KEYS[1], 'run_id') ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1], KEYS[2])
return 1
"""
    IS_ACTIVE_SCRIPT = """-- steering:is_active
local run_id = redis.call('HGET', KEYS[1], 'run_id')
if not run_id then return {} end
return {run_id, redis.call('HGET', KEYS[1], 'mode'), redis.call('HGET', KEYS[1], 'status')}
"""

    def __init__(self, redis_client: Any, *, key_prefix: str, ttl_seconds: int) -> None:
        self.redis = redis_client
        self.key_prefix = key_prefix.rstrip(":")
        self.ttl_seconds = max(1, int(ttl_seconds))

    def _keys(self, session_id: str) -> tuple[str, str]:
        return (
            f"{self.key_prefix}:active:{session_id}",
            f"{self.key_prefix}:queue:{session_id}",
        )

    async def register(self, session_id: str, run_id: str, mode: str) -> bool:
        active_key, queue_key = self._keys(session_id)
        result = await self.redis.eval(
            self.REGISTER_SCRIPT,
            2,
            active_key,
            queue_key,
            run_id,
            mode,
            self.ttl_seconds,
            "1" if mode in STEERABLE_MODES else "0",
        )
        return bool(result)

    async def unregister(self, session_id: str, run_id: str) -> None:
        active_key, queue_key = self._keys(session_id)
        await self.redis.eval(
            self.UNREGISTER_SCRIPT,
            2,
            active_key,
            queue_key,
            run_id,
        )

    async def add_input(self, session_id: str, item: SteeringInput) -> bool:
        active_key, queue_key = self._keys(session_id)
        result = await self.redis.eval(
            self.ADD_SCRIPT,
            2,
            active_key,
            queue_key,
            item.to_json(),
            self.ttl_seconds,
        )
        return bool(result)

    async def drain(self, session_id: str, run_id: str) -> List[SteeringInput]:
        active_key, queue_key = self._keys(session_id)
        values = await self.redis.eval(
            self.DRAIN_SCRIPT,
            2,
            active_key,
            queue_key,
            run_id,
            self.ttl_seconds,
        )
        return [SteeringInput.from_json(value) for value in values or []]

    async def begin_completion(self, session_id: str, run_id: str) -> List[SteeringInput]:
        active_key, queue_key = self._keys(session_id)
        result = await self.redis.eval(
            self.BEGIN_COMPLETION_SCRIPT,
            2,
            active_key,
            queue_key,
            run_id,
            self.ttl_seconds,
        )
        if not result or result[0] != "drained":
            return []
        return [SteeringInput.from_json(value) for value in result[1:]]

    async def mark_closing(self, session_id: str, run_id: str) -> bool:
        active_key, _ = self._keys(session_id)
        result = await self.redis.eval(
            self.MARK_CLOSING_SCRIPT,
            1,
            active_key,
            run_id,
            self.ttl_seconds,
        )
        return bool(result)

    async def close_and_drain(self, session_id: str, run_id: str) -> List[SteeringInput]:
        active_key, queue_key = self._keys(session_id)
        values = await self.redis.eval(
            self.CLOSE_AND_DRAIN_SCRIPT,
            2,
            active_key,
            queue_key,
            run_id,
            self.ttl_seconds,
        )
        return [SteeringInput.from_json(value) for value in values or []]

    async def is_active(self, session_id: str, mode: str | None = None) -> bool:
        active_key, _ = self._keys(session_id)
        result = await self.redis.eval(self.IS_ACTIVE_SCRIPT, 1, active_key)
        if not result or len(result) < 3 or result[2] != "accepting":
            return False
        return mode is None or result[1] == mode

    async def aclose(self) -> None:
        await self.redis.aclose()


class SteeringRegistry:
    """Failure-safe facade over a steering store."""

    def __init__(self, store: SteeringStore | None = None) -> None:
        self.store: SteeringStore = store or InMemorySteeringStore()

    async def _safe(self, operation: str, fallback: Any, awaitable):
        try:
            return await awaitable
        except Exception as exc:
            logger.warning(
                "steering_store_operation_failed",
                operation=operation,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return fallback

    async def register(self, session_id: str, run_id: str, mode: str) -> bool:
        return await self._safe("register", False, self.store.register(session_id, run_id, mode))

    async def unregister(self, session_id: str, run_id: str) -> None:
        await self._safe("unregister", None, self.store.unregister(session_id, run_id))

    async def add_input(
        self,
        session_id: str,
        content: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        input_id: Optional[str] = None,
    ) -> bool:
        text = (content or "").strip()
        clean_attachments = [dict(item) for item in attachments or [] if isinstance(item, dict)]
        if not text and not clean_attachments:
            return False
        item = SteeringInput(
            content=text,
            attachments=clean_attachments,
            input_id=str(input_id or f"steer_{uuid4().hex}"),
        )
        return await self._safe("add_input", False, self.store.add_input(session_id, item))

    async def drain(self, session_id: str, run_id: str) -> List[SteeringInput]:
        return await self._safe("drain", [], self.store.drain(session_id, run_id))

    async def begin_completion(self, session_id: str, run_id: str) -> List[SteeringInput]:
        return await self._safe(
            "begin_completion",
            [],
            self.store.begin_completion(session_id, run_id),
        )

    async def mark_closing(self, session_id: str, run_id: str) -> bool:
        return await self._safe(
            "mark_closing",
            False,
            self.store.mark_closing(session_id, run_id),
        )

    async def close_and_drain(self, session_id: str, run_id: str) -> List[SteeringInput]:
        return await self._safe(
            "close_and_drain",
            [],
            self.store.close_and_drain(session_id, run_id),
        )

    async def is_active(self, session_id: str, mode: str | None = None) -> bool:
        return await self._safe("is_active", False, self.store.is_active(session_id, mode))

    async def aclose(self) -> None:
        await self._safe("close", None, self.store.aclose())


def _create_production_registry() -> SteeringRegistry:
    import redis.asyncio as redis

    from config.settings import settings

    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    store = RedisSteeringStore(
        client,
        key_prefix=settings.agent_steering_redis_prefix,
        ttl_seconds=settings.agent_steering_ttl_seconds,
    )
    return SteeringRegistry(store=store)


steering_registry = _create_production_registry()

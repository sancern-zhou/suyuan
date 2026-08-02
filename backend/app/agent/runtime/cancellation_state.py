"""Shared cancellation state used to coordinate agent runs across workers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional, Protocol


TERMINAL_STATUSES = {"paused", "finished", "failed"}


@dataclass(frozen=True)
class CancellationState:
    run_id: str
    status: str
    reason: Optional[str] = None
    error: Optional[str] = None


class CancellationStateStore(Protocol):
    async def register(self, session_id: str, run_id: str) -> bool: ...
    async def request_cancel(
        self,
        session_id: str,
        expected_run_id: Optional[str],
        reason: str,
    ) -> bool: ...
    async def get(self, session_id: str) -> Optional[CancellationState]: ...
    async def finish(
        self,
        session_id: str,
        run_id: str,
        *,
        error: Optional[str] = None,
    ) -> bool: ...
    async def aclose(self) -> None: ...


class InMemoryCancellationStateStore:
    """Shared test store; multiple registries may use the same instance."""

    def __init__(self) -> None:
        self._states: dict[str, CancellationState] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, run_id: str) -> bool:
        async with self._lock:
            current = self._states.get(session_id)
            if (
                current
                and current.run_id != run_id
                and current.status not in TERMINAL_STATUSES
            ):
                return False
            self._states[session_id] = CancellationState(run_id=run_id, status="running")
            return True

    async def request_cancel(
        self,
        session_id: str,
        expected_run_id: Optional[str],
        reason: str,
    ) -> bool:
        async with self._lock:
            current = self._states.get(session_id)
            if not current or (
                expected_run_id is not None and current.run_id != expected_run_id
            ):
                return False
            if current.status in TERMINAL_STATUSES:
                return True
            effective_reason = (
                "user_paused"
                if reason == "user_paused" or current.reason == "user_paused"
                else reason
            )
            self._states[session_id] = CancellationState(
                run_id=current.run_id,
                status="pause_requested",
                reason=effective_reason,
            )
            return True

    async def get(self, session_id: str) -> Optional[CancellationState]:
        async with self._lock:
            return self._states.get(session_id)

    async def finish(
        self,
        session_id: str,
        run_id: str,
        *,
        error: Optional[str] = None,
    ) -> bool:
        async with self._lock:
            current = self._states.get(session_id)
            if not current or current.run_id != run_id:
                return False
            if current.status == "failed" and not error:
                return True
            status = "failed" if error else (
                "paused" if current.reason == "user_paused" else "finished"
            )
            self._states[session_id] = CancellationState(
                run_id=run_id,
                status=status,
                reason=current.reason,
                error=error,
            )
            return True

    async def aclose(self) -> None:
        return None


class RedisCancellationStateStore:
    """Atomic Redis control plane for cancellation across Uvicorn workers."""

    REGISTER_SCRIPT = """-- cancellation:register
local current_run = redis.call('HGET', KEYS[1], 'run_id')
local current_status = redis.call('HGET', KEYS[1], 'status')
if current_run and current_run ~= ARGV[1]
   and current_status ~= 'paused'
   and current_status ~= 'finished'
   and current_status ~= 'failed' then
  return 0
end
redis.call('HSET', KEYS[1], 'run_id', ARGV[1], 'status', 'running')
redis.call('HDEL', KEYS[1], 'reason', 'error')
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""
    REQUEST_SCRIPT = """-- cancellation:request
local current_run = redis.call('HGET', KEYS[1], 'run_id')
if not current_run then return 0 end
if ARGV[1] ~= '' and current_run ~= ARGV[1] then return 0 end
local current_status = redis.call('HGET', KEYS[1], 'status')
if current_status == 'paused' or current_status == 'finished' or current_status == 'failed' then
  return 1
end
local current_reason = redis.call('HGET', KEYS[1], 'reason')
local reason = ARGV[2]
if current_reason == 'user_paused' or reason == 'user_paused' then reason = 'user_paused' end
redis.call('HSET', KEYS[1], 'status', 'pause_requested', 'reason', reason)
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""
    FINISH_SCRIPT = """-- cancellation:finish
if redis.call('HGET', KEYS[1], 'run_id') ~= ARGV[1] then return 0 end
local current_status = redis.call('HGET', KEYS[1], 'status')
if current_status == 'failed' and ARGV[2] == '' then return 1 end
local reason = redis.call('HGET', KEYS[1], 'reason')
local status = 'finished'
if ARGV[2] ~= '' then
  status = 'failed'
elseif reason == 'user_paused' then
  status = 'paused'
end
redis.call('HSET', KEYS[1], 'status', status)
if ARGV[2] ~= '' then redis.call('HSET', KEYS[1], 'error', ARGV[2]) end
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""

    def __init__(self, redis_client: Any, *, key_prefix: str, ttl_seconds: int) -> None:
        self.redis = redis_client
        self.key_prefix = key_prefix.rstrip(":")
        self.ttl_seconds = max(60, int(ttl_seconds))

    def _key(self, session_id: str) -> str:
        return f"{self.key_prefix}:state:{session_id}"

    async def register(self, session_id: str, run_id: str) -> bool:
        result = await self.redis.eval(
            self.REGISTER_SCRIPT,
            1,
            self._key(session_id),
            run_id,
            self.ttl_seconds,
        )
        return bool(result)

    async def request_cancel(
        self,
        session_id: str,
        expected_run_id: Optional[str],
        reason: str,
    ) -> bool:
        result = await self.redis.eval(
            self.REQUEST_SCRIPT,
            1,
            self._key(session_id),
            expected_run_id or "",
            reason,
            self.ttl_seconds,
        )
        return bool(result)

    async def get(self, session_id: str) -> Optional[CancellationState]:
        values = await self.redis.hgetall(self._key(session_id))
        if not values or not values.get("run_id"):
            return None
        return CancellationState(
            run_id=str(values["run_id"]),
            status=str(values.get("status") or "running"),
            reason=str(values["reason"]) if values.get("reason") else None,
            error=str(values["error"]) if values.get("error") else None,
        )

    async def finish(
        self,
        session_id: str,
        run_id: str,
        *,
        error: Optional[str] = None,
    ) -> bool:
        result = await self.redis.eval(
            self.FINISH_SCRIPT,
            1,
            self._key(session_id),
            run_id,
            error or "",
            self.ttl_seconds,
        )
        return bool(result)

    async def aclose(self) -> None:
        await self.redis.aclose()

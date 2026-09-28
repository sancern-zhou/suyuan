"""Durable workflow jobs and cross-worker event streams."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import redis.asyncio as redis

from config.settings import settings


@dataclass(frozen=True)
class WorkflowJob:
    workflow_id: str
    session_id: str
    definition: dict[str, Any]
    snapshot: dict[str, Any]
    status: str = "queued"
    job_id: str = ""


class WorkflowJobStore:
    """Redis-backed queue, lease state and append-only workflow event stream."""

    def __init__(self, client: Any, *, prefix: str = "suyuan:agent:workflow", lease_seconds: int = 900):
        self.redis = client
        self.prefix = prefix.rstrip(":")
        self.lease_seconds = max(60, int(lease_seconds))
        self.worker_id = f"{socket.gethostname()}:{id(self)}"

    @property
    def queue_key(self) -> str:
        return f"{self.prefix}:queue"

    def state_key(self, workflow_id: str) -> str:
        return f"{self.prefix}:state:{workflow_id}"

    def event_key(self, workflow_id: str) -> str:
        return f"{self.prefix}:events:{workflow_id}"

    async def enqueue(
        self,
        *,
        session_id: str,
        workflow_id: str,
        definition: Mapping[str, Any],
        snapshot: Mapping[str, Any],
    ) -> WorkflowJob:
        key = self.state_key(workflow_id)
        current = await self.redis.hgetall(key)
        current_status = str(current.get("status") or "")
        if current_status in {"queued", "running"}:
            return self._decode_job(current)
        payload = {
            "session_id": session_id,
            "workflow_id": workflow_id,
            "definition": dict(definition),
            "snapshot": dict(snapshot),
        }
        await self.redis.hset(
            key,
            mapping={
                "job_id": workflow_id,
                "session_id": session_id,
                "workflow_id": workflow_id,
                "status": "queued",
                "payload": json.dumps(payload, ensure_ascii=False, default=str),
                "updated_at": str(time.time()),
            },
        )
        await self.redis.expire(key, self.lease_seconds * 4)
        await self.redis.rpush(self.queue_key, workflow_id)
        await self.publish_event(workflow_id, {"type": "workflow.queued", "status": "queued"})
        return WorkflowJob(workflow_id, session_id, dict(definition), dict(snapshot), "queued", workflow_id)

    async def claim(self, *, timeout: int = 1) -> Optional[WorkflowJob]:
        item = await self.redis.blpop(self.queue_key, timeout=max(0, int(timeout)))
        if not item:
            return None
        workflow_id = item[1]
        if isinstance(workflow_id, bytes):
            workflow_id = workflow_id.decode()
        values = await self.redis.hgetall(self.state_key(workflow_id))
        if str(values.get("status") or "") != "queued":
            return None
        await self.redis.hset(
            self.state_key(workflow_id),
            mapping={"status": "running", "owner": self.worker_id, "updated_at": str(time.time())},
        )
        await self.publish_event(workflow_id, {"type": "workflow.running", "status": "running"})
        values["status"] = "running"
        return self._decode_job(values)

    async def recover_expired(self) -> int:
        """Requeue jobs whose worker lease expired after a crash."""
        recovered = 0
        now = time.time()
        async for key in self.redis.scan_iter(match=f"{self.prefix}:state:*"):
            values = await self.redis.hgetall(key)
            if str(values.get("status") or "") != "running":
                continue
            updated_at = float(values.get("updated_at") or 0)
            if now - updated_at <= self.lease_seconds:
                continue
            workflow_id = str(values.get("workflow_id") or "")
            if not workflow_id:
                continue
            await self.redis.hset(key, mapping={"status": "queued", "updated_at": str(now)})
            await self.redis.rpush(self.queue_key, workflow_id)
            await self.publish_event(workflow_id, {"type": "workflow.recovered", "status": "queued"})
            recovered += 1
        return recovered

    async def heartbeat(self, workflow_id: str) -> None:
        await self.redis.hset(self.state_key(workflow_id), "updated_at", str(time.time()))
        await self.redis.expire(self.state_key(workflow_id), self.lease_seconds * 4)

    async def publish_snapshot(self, workflow_id: str, snapshot: Mapping[str, Any]) -> None:
        await self.heartbeat(workflow_id)
        runtime = snapshot.get("runtime") if isinstance(snapshot, Mapping) else None
        events = runtime.get("events") if isinstance(runtime, Mapping) else None
        last_sequence = int((await self.redis.hget(self.state_key(workflow_id), "last_sequence") or 0))
        for event in events or []:
            if not isinstance(event, Mapping):
                continue
            sequence = int(event.get("sequence") or 0)
            if sequence <= last_sequence:
                continue
            await self.publish_event(workflow_id, {"type": "runtime", "sequence": sequence, "event": dict(event)})
            last_sequence = sequence
        await self.redis.hset(
            self.state_key(workflow_id),
            mapping={
                "last_sequence": str(last_sequence),
                "snapshot": json.dumps(dict(snapshot), ensure_ascii=False, default=str),
                "status": str(snapshot.get("status") or "running"),
                "updated_at": str(time.time()),
            },
        )

    async def publish_event(self, workflow_id: str, event: Mapping[str, Any]) -> str:
        values = {"event": json.dumps(dict(event), ensure_ascii=False, default=str), "created_at": str(time.time())}
        result = await self.redis.xadd(self.event_key(workflow_id), values, maxlen=5000, approximate=True)
        return result.decode() if isinstance(result, bytes) else str(result)

    async def read_events(
        self,
        workflow_id: str,
        *,
        after_id: str = "0-0",
        block_ms: Optional[int] = None,
        count: int = 100,
    ) -> list[tuple[str, dict[str, Any]]]:
        # Redis interprets BLOCK 0 as an infinite wait.  A normal snapshot
        # lookup must return immediately when no stream exists; only the SSE
        # follow path supplies a positive polling timeout.
        block = None if block_ms is None or block_ms <= 0 else block_ms
        result = await self.redis.xread(
            {self.event_key(workflow_id): after_id},
            count=max(1, count),
            block=block,
        )
        if not result:
            return []
        rows = []
        for _, entries in result:
            for event_id, values in entries:
                if isinstance(event_id, bytes):
                    event_id = event_id.decode()
                raw = values.get("event") if isinstance(values, Mapping) else None
                if isinstance(raw, bytes):
                    raw = raw.decode()
                try:
                    payload = json.loads(raw or "{}")
                except (TypeError, ValueError):
                    payload = {"type": "workflow.event", "raw": raw}
                rows.append((str(event_id), payload))
        return rows

    async def get(self, workflow_id: str) -> Optional[WorkflowJob]:
        values = await self.redis.hgetall(self.state_key(workflow_id))
        if not values:
            return None
        return self._decode_job(values)

    async def finish(self, workflow_id: str, *, status: str, result: Optional[Mapping[str, Any]] = None) -> None:
        await self.redis.hset(
            self.state_key(workflow_id),
            mapping={"status": status, "result": json.dumps(dict(result or {}), ensure_ascii=False, default=str), "updated_at": str(time.time())},
        )
        await self.publish_event(workflow_id, {"type": "workflow.terminal", "status": status})

    def _decode_job(self, values: Mapping[str, Any]) -> WorkflowJob:
        raw = values.get("payload") or "{}"
        if isinstance(raw, bytes):
            raw = raw.decode()
        payload = json.loads(raw)
        return WorkflowJob(
            workflow_id=str(payload.get("workflow_id") or values.get("workflow_id") or ""),
            session_id=str(payload.get("session_id") or values.get("session_id") or ""),
            definition=dict(payload.get("definition") or {}),
            snapshot=dict(payload.get("snapshot") or {}),
            status=str(values.get("status") or "queued"),
            job_id=str(values.get("job_id") or payload.get("workflow_id") or ""),
        )


_workflow_job_store: Optional[WorkflowJobStore] = None


def get_workflow_job_store() -> WorkflowJobStore:
    global _workflow_job_store
    if _workflow_job_store is None:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        _workflow_job_store = WorkflowJobStore(client, prefix=f"{settings.agent_steering_redis_prefix}:workflow")
    return _workflow_job_store

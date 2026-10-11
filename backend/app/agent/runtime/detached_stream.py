"""Detached-run 事件镜像（共享层）。

把 agent run 产生的 SSE 帧镜像到 Redis Stream，使 web 前端断开后任务继续运行、
重连后可从任意 web worker 回放并跟随事件（app 同款体验）。设计要点：

- run 与请求解耦后，SSE 生成器只是订阅者；本模块是订阅者的唯一数据源。
- 写入与读取都容错：Redis 不可用时发布方静默降级（run 不受影响），
  读取方通过 ``stream_lost`` 事件让前端回退到会话恢复接口。
- stream 键与 "活跃 run" 映射均带 TTL，孤儿状态自动过期，无需人工清理。
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

import structlog

logger = structlog.get_logger()

#: 终止类事件：订阅者收到即结束，活跃映射随之清除
TERMINAL_EVENT_TYPES = frozenset({"complete", "incomplete", "fatal_error", "interrupted"})
#: 传输层合成事件：表示镜像通道结束（区别于业务终止事件）
STREAM_CLOSED_EVENT_TYPE = "stream_closed"
STREAM_LOST_EVENT_TYPE = "stream_lost"
STREAM_OPEN_EVENT_TYPE = "stream_open"

_SSE_DATA_PREFIX = "data: "


def parse_sse_payload(frame: str) -> Optional[dict[str, Any]]:
    """从 SSE 帧（``[id: ...]\\ndata: {...}\\n\\n``）解析业务事件；失败返回 None。"""
    payload = ""
    for line in frame.splitlines():
        if line.startswith(_SSE_DATA_PREFIX):
            payload = line[len(_SSE_DATA_PREFIX):].strip()
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def payload_event_type(payload: dict[str, Any]) -> Optional[str]:
    value = payload.get("type")
    return value if isinstance(value, str) else None


class RunEventStream:
    """单个 web 实例共享的 run 事件镜像存取器（Redis Streams）。"""

    def __init__(
        self,
        redis: Any,
        *,
        stream_prefix: str = "suyuan:run:events:",
        active_prefix: str = "suyuan:run:active:",
        owner_prefix: str = "suyuan:run:owner:",
        ttl_seconds: int = 7200,
        max_entries: int = 20000,
        read_block_ms: int = 15000,
    ) -> None:
        self._redis = redis
        self._stream_prefix = stream_prefix
        self._active_prefix = active_prefix
        self._owner_prefix = owner_prefix
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._read_block_ms = read_block_ms

    @classmethod
    def from_app(cls, app: Any) -> Optional["RunEventStream"]:
        """从 FastAPI app 提取共享 Redis 客户端；未配置时返回 None（回退内联模式）。"""
        redis = getattr(app.state, "auth_redis", None)
        if redis is None:
            return None
        return cls(redis)

    # ---------- 发布侧（后台 run 任务调用） ----------

    async def open(self, session_id: str, stream_id: str) -> None:
        """登记活跃映射、归属映射并写入 stream_open 事件，让订阅者拿到 stream_id。"""
        key = self._stream_key(stream_id)
        try:
            await self._redis.xadd(
                key,
                {
                    "type": STREAM_OPEN_EVENT_TYPE,
                    "payload": json.dumps(
                        {
                            "type": STREAM_OPEN_EVENT_TYPE,
                            "data": {"session_id": session_id, "stream_id": stream_id},
                        },
                        ensure_ascii=False,
                    ),
                },
                id="*",
            )
            await self._redis.expire(key, self._ttl_seconds)
            await self._redis.set(f"{self._active_prefix}{session_id}", stream_id, ex=self._ttl_seconds)
            await self._redis.set(f"{self._owner_prefix}{stream_id}", session_id, ex=self._ttl_seconds)
        except Exception as exc:
            logger.warning("run_stream_open_failed", error_type=type(exc).__name__)

    async def publish(self, stream_id: str, sse_chunk: str) -> None:
        """镜像一帧业务事件；终止事件同时清除活跃映射。失败不影响 run 本身。"""
        payload = parse_sse_payload(sse_chunk)
        if payload is None:
            return
        key = self._stream_key(stream_id)
        event_type = payload_event_type(payload) or "unknown"
        terminal = event_type in TERMINAL_EVENT_TYPES
        try:
            await self._redis.xadd(
                key,
                {"type": event_type, "payload": sse_chunk[len(_SSE_DATA_PREFIX):].strip()},
                id="*",
                maxlen=self._max_entries,
                approximate=True,
            )
            await self._redis.expire(key, self._ttl_seconds)
            if terminal:
                await self._clear_active_for_stream(stream_id)
        except Exception as exc:
            logger.warning("run_stream_publish_failed", error_type=type(exc).__name__)

    async def close(self, stream_id: str) -> None:
        """run 结束（含异常/取消）后补写传输层闭合事件并清理活跃/归属映射。"""
        try:
            await self._redis.xadd(
                self._stream_key(stream_id),
                {
                    "type": STREAM_CLOSED_EVENT_TYPE,
                    "payload": json.dumps(
                        {"type": STREAM_CLOSED_EVENT_TYPE, "data": {}}, ensure_ascii=False
                    ),
                },
                id="*",
            )
            await self._redis.expire(self._stream_key(stream_id), self._ttl_seconds)
        except Exception as exc:
            logger.warning("run_stream_close_failed", error_type=type(exc).__name__)
        await self._clear_active_for_stream(stream_id)
        try:
            await self._redis.delete(f"{self._owner_prefix}{stream_id}")
        except Exception as exc:
            logger.warning("run_stream_owner_clear_failed", error_type=type(exc).__name__)

    async def owner_of(self, stream_id: str) -> Optional[str]:
        """返回 stream 归属的 session_id；已过期/不存在时为 None。"""
        try:
            value = await self._redis.get(f"{self._owner_prefix}{stream_id}")
        except Exception:
            return None
        return value or None

    async def _clear_active_for_stream(self, stream_id: str) -> None:
        try:
            async for session_key in self._redis.scan_iter(match=f"{self._active_prefix}*"):
                if await self._redis.get(session_key) == stream_id:
                    await self._redis.delete(session_key)
        except Exception as exc:
            logger.warning("run_stream_active_clear_failed", error_type=type(exc).__name__)

    # ---------- 订阅侧（SSE 订阅/重连接口调用） ----------

    async def resolve_active(self, session_id: str) -> Optional[str]:
        try:
            value = await self._redis.get(f"{self._active_prefix}{session_id}")
        except Exception:
            return None
        return value or None

    async def is_active(self, session_id: str, stream_id: str) -> bool:
        return await self.resolve_active(session_id) == stream_id

    async def read(
        self, stream_id: str, last_id: str, *, block_ms: Optional[int] = None
    ) -> Optional[list[tuple[str, str]]]:
        """读取新事件；返回 (entry_id, payload) 列表。

        返回 None 表示流已消失（过期/被清理），调用方应结束订阅。
        """
        key = self._stream_key(stream_id)
        block = self._read_block_ms if block_ms is None else block_ms
        try:
            if block and block > 0 and last_id != "$":
                result = await self._redis.xread({key: last_id}, block=block, count=200)
            else:
                result = await self._redis.xread({key: last_id}, count=200)
        except Exception as exc:
            logger.warning("run_stream_read_failed", error_type=type(exc).__name__)
            return None
        if not result:
            return []
        entries: list[tuple[str, str]] = []
        for _key, messages in result.items():
            for entry_id, fields in messages:
                payload = fields.get("payload") if isinstance(fields, dict) else None
                if payload:
                    entries.append((entry_id, payload))
        return entries

    def stream_lost_event(self, session_id: str, stream_id: str) -> str:
        return json.dumps(
            {
                "type": STREAM_LOST_EVENT_TYPE,
                "data": {"session_id": session_id, "stream_id": stream_id},
            },
            ensure_ascii=False,
        )

    async def follow(
        self,
        stream_id: str,
        *,
        session_id: str,
        last_id: str = "0",
        keepalive_comment: str = ": keepalive\n\n",
    ) -> AsyncIterator[str]:
        """回放并跟随事件直到终止；供 SSE 订阅生成器直接 async for。"""
        cursor = last_id or "0"
        while True:
            entries = await self.read(stream_id, cursor)
            if entries is None:
                yield f"data: {self.stream_lost_event(session_id, stream_id)}\n\n"
                return
            if not entries:
                yield keepalive_comment
                if not await self.is_active(session_id, stream_id):
                    # 活跃映射已消失：做一次非阻塞补读（终止事件先于清理写入），
                    # 仍无事件则认定 run 已结束且镜像不完整/已过期。
                    tail = await self.read(stream_id, cursor, block_ms=0)
                    if tail is None or not tail:
                        yield f"data: {self.stream_lost_event(session_id, stream_id)}\n\n"
                        return
                    for entry_id, payload in tail:
                        cursor = entry_id
                        yield f"id: {entry_id}\ndata: {payload}\n\n"
                        if self.is_terminal_payload(payload):
                            return
                    yield f"data: {self.stream_lost_event(session_id, stream_id)}\n\n"
                    return
                continue
            for entry_id, payload in entries:
                cursor = entry_id
                yield f"id: {entry_id}\ndata: {payload}\n\n"
                if self.is_terminal_payload(payload):
                    return

    def is_terminal_payload(self, payload: str) -> bool:
        parsed = parse_sse_payload(f"data: {payload}")
        if parsed is None:
            return False
        event_type = payload_event_type(parsed)
        return event_type in TERMINAL_EVENT_TYPES or event_type == STREAM_CLOSED_EVENT_TYPE

    def _stream_key(self, stream_id: str) -> str:
        return f"{self._stream_prefix}{stream_id}"

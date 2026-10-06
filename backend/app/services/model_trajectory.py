"""Session-scoped model request records, independent of the chat transcript."""
import asyncio
import functools
import hashlib
import inspect
import json
import os
import tempfile
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import structlog
from app.utils.path_config import get_data_registry

logger = structlog.get_logger()
_scope = ContextVar("model_trajectory_scope", default=None)
_capturing = ContextVar("model_trajectory_capturing", default=None)


def update_trajectory_provider(service):
    capture = _capturing.get()
    if capture and capture.record:
        capture.record.update(provider=service.provider, model=service.model,
                              token_usage_mode="anthropic" if getattr(service, "api_mode", "") == "anthropic_messages" else "chat_completions")


@contextmanager
def trajectory_scope(session_id=None, *, run_id=None, source=None):
    previous = _scope.get() or {}
    current_session = session_id or previous.get("session_id")
    root = previous.get("root_session_id") or current_session
    kind = source or ("subagent" if root != current_session else "main")
    token = _scope.set({
        "session_id": current_session, "root_session_id": root,
        "run_id": run_id or previous.get("run_id"), "kind": kind,
    })
    try:
        yield
    finally:
        _scope.reset(token)


def plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


class ModelTrajectoryStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else get_data_registry() / "model_trajectory"

    def session_directory(self, session_id):
        # Session ids are identifiers, never filesystem paths supplied by clients.
        return self.directory / hashlib.sha256(session_id.encode()).hexdigest()

    def write(self, record):
        for session_id in {record["session_id"], record["root_session_id"]}:
            directory = self.session_directory(session_id)
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f'{record["request_id"]}.json'
            descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".pending-")
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                    json.dump(record, output, ensure_ascii=False, default=str)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def read(self, session_id, *, before=None, limit=50):
        files = sorted(self.session_directory(session_id).glob("*.json"), reverse=True)
        candidates = [path for path in files if before is None or path.stem < before]
        selected = candidates[:limit]
        records = []
        for path in reversed(selected):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                logger.warning("model_trajectory_record_unreadable", request_id=path.stem)
        return {"records": records, "total_count": len(files), "has_more": len(candidates) > limit,
                "oldest_request_id": selected[-1].stem if selected else None}


async def persist(record):
    try:
        await asyncio.to_thread(ModelTrajectoryStore().write, record)
    except Exception as error:
        # Recording must never turn an otherwise successful model call into a failure.
        logger.warning("model_trajectory_write_failed", error_type=type(error).__name__)


class Capture:
    def __init__(self, service, arguments):
        scope = _scope.get()
        self.record = None
        self.started = time.monotonic()
        self.blocks = {}
        self.fragments = {}
        self.usage = {}
        self.last_snapshot = self.started
        if not scope or not scope.get("session_id"):
            return
        self.record = {
            **scope, "request_id": f'{time.time_ns():020d}-{uuid4().hex}',
            "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
            "source": scope["kind"], "provider": service.provider, "model": service.model,
            "token_usage_mode": "anthropic" if getattr(service, "api_mode", "") == "anthropic_messages" else "chat_completions",
            "request": plain({key: arguments[key] for key in ("messages", "system", "tools", "max_tokens", "temperature") if key in arguments}),
            "response": {"content": [], "usage": {}},
        }

    def feed(self, event, service):
        if not self.record:
            return
        self.record.update(provider=service.provider, model=service.model)
        if isinstance(event, str):
            self.blocks.setdefault(0, {"type": "text", "text": ""})["text"] += event
            return
        event = plain(event)
        data = event.get("data") or {}
        kind = event.get("type")
        index = data.get("index", 0)
        if kind == "message_start":
            self.usage.update(data.get("usage") or {})
            if data.get("model"):
                self.record["model"] = data["model"]
        elif kind == "content_block_start":
            self.blocks[index] = dict(data.get("block") or data.get("content_block") or {})
        elif kind == "content_block_delta":
            delta = data.get("delta") or {}
            block = self.blocks.setdefault(index, {})
            if delta.get("type") in ("text_delta", "thinking_delta", "signature_delta"):
                field = {"text_delta": "text", "thinking_delta": "thinking", "signature_delta": "signature"}[delta["type"]]
                block[field] = block.get(field, "") + delta.get(field, "")
            elif delta.get("type") == "input_json_delta":
                self.fragments[index] = self.fragments.get(index, "") + delta.get("partial_json", "")
        elif kind == "message_delta":
            self.usage.update(data.get("usage") or {})
            self.record["response"]["stop_reason"] = data.get("stop_reason")
        elif "chunk" in event:
            self.feed(event.get("chunk") or "", service)

    def snapshot(self):
        if not self.record:
            return
        blocks = plain(self.blocks)
        for index, fragment in self.fragments.items():
            try:
                blocks[index]["input"] = json.loads(fragment)
            except ValueError:
                blocks[index]["input_partial"] = fragment
        self.record["response"].update(content=[blocks[index] for index in sorted(blocks)], usage=dict(self.usage))

    def finish(self, response=None, *, error=None, cancelled=False):
        if not self.record:
            return
        if response is not None:
            normalized = plain(response)
            self.record["response"] = normalized if isinstance(normalized, dict) else {"content": [{"type": "text", "text": str(normalized)}]}
            self.record["model"] = self.record["response"].get("model") or self.record["model"]
        else:
            self.snapshot()
        self.record.update(status="cancelled" if cancelled else "failed" if error else "completed",
                           duration_ms=round((time.monotonic() - self.started) * 1000, 2))
        if error:
            self.record["error"] = {"type": type(error).__name__, "message": str(error)}


def trace_model_call(function):
    """Capture one logical LLM call; protocol/profile delegation is not double counted."""
    signature = inspect.signature(function)
    if inspect.isasyncgenfunction(function):
        @functools.wraps(function)
        async def stream(self, *args, **kwargs):
            bound = signature.bind(self, *args, **kwargs)
            bound.apply_defaults()
            if _same_capture_scope() or not _scope.get() or any(bound.arguments.get(key) for key in ("provider", "model", "auto_profile")):
                async for event in function(self, *args, **kwargs):
                    yield event
                return
            arguments = bound.arguments
            capture = Capture(self, arguments)
            token = _capturing.set(capture)
            iterator = function(self, *args, **kwargs)
            try:
                if capture.record:
                    await persist(capture.record)
                async for event in iterator:
                    capture.feed(event, self)
                    if capture.record and time.monotonic() - capture.last_snapshot >= 1:
                        capture.snapshot()
                        await persist(capture.record)
                        capture.last_snapshot = time.monotonic()
                    # The consumer can run tools/subagents before requesting the
                    # next chunk. Do not let delegation suppression leak to it.
                    _capturing.reset(token)
                    token = None
                    yield event
                    token = _capturing.set(capture)
                capture.finish()
            except BaseException as error:
                capture.finish(error=error, cancelled=isinstance(error, (asyncio.CancelledError, GeneratorExit)))
                raise
            finally:
                try:
                    await iterator.aclose()
                finally:
                    if token is not None:
                        _capturing.reset(token)
                if capture.record:
                    await asyncio.shield(persist(capture.record))
        return stream

    @functools.wraps(function)
    async def call(self, *args, **kwargs):
        bound = signature.bind(self, *args, **kwargs)
        bound.apply_defaults()
        if _same_capture_scope() or not _scope.get() or any(bound.arguments.get(key) for key in ("provider", "model", "auto_profile")):
            return await function(self, *args, **kwargs)
        capture = Capture(self, bound.arguments)
        token = _capturing.set(capture)
        try:
            if capture.record:
                await persist(capture.record)
            result = await function(self, *args, **kwargs)
            capture.finish(result)
            return result
        except BaseException as error:
            capture.finish(error=error, cancelled=isinstance(error, asyncio.CancelledError))
            raise
        finally:
            _capturing.reset(token)
            if capture.record:
                await asyncio.shield(persist(capture.record))
    return call


def _same_capture_scope():
    capture = _capturing.get()
    scope = _scope.get() or {}
    return bool(capture and capture.record and capture.record["session_id"] == scope.get("session_id") and capture.record["source"] == scope.get("kind"))


def trajectory_source(source):
    def decorate(function):
        @functools.wraps(function)
        async def wrapped(*args, **kwargs):
            with trajectory_scope(source=source):
                return await function(*args, **kwargs)
        return wrapped
    return decorate

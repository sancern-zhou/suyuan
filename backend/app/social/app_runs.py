"""Detached App turns with a shared, durable event log.

SQLite lives under DATA_REGISTRY_DIR, so all web processes on a deployment
share admission control, status and replay. Server restarts fail stale runs;
they never silently repeat tools with side effects.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import AsyncIterator, Callable


TERMINAL = {"completed", "failed", "cancelled"}


class AppRunStore:
    def __init__(self, path: Path):
        self.path = path
        self.tasks: set[asyncio.Task] = set()

    def _call(self, operation):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.row_factory = sqlite3.Row
            db.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_id TEXT NOT NULL, session_id TEXT NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL, heartbeat REAL NOT NULL, cancel_requested INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL, UNIQUE(owner, request_id))")
            db.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS event_run ON events(run_id, sequence)")
            db.execute("BEGIN IMMEDIATE")
            # A dead web process cannot leave the App spinning forever.
            stale = db.execute("SELECT run_id FROM runs WHERE status='running' AND heartbeat < ?", (time.time() - 90,)).fetchall()
            for row in stale:
                db.execute("UPDATE runs SET status='failed' WHERE run_id=?", (row[0],))
                self._event(db, row[0], {"type": "fatal_error", "data": {"error": "服务执行已中断，请重新发起对话", "code": "app_run_lost"}})
            result = operation(db)
            db.commit()
            return result

    @staticmethod
    def _event(db, run_id, event):
        db.execute("INSERT INTO events(run_id,payload) VALUES (?,?)", (run_id, json.dumps(event, ensure_ascii=False, default=str)))

    async def lookup(self, owner, request_id):
        return await asyncio.to_thread(self._call, lambda db: self._row(db.execute("SELECT * FROM runs WHERE owner=? AND request_id=?", (owner, request_id)).fetchone()))

    @staticmethod
    def _row(row):
        return dict(row) if row else None

    async def get(self, run_id):
        return await asyncio.to_thread(self._call, lambda db: self._row(db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()))

    async def create(self, owner, request_id, session_id, fingerprint, payload=None):
        def operation(db):
            existing = db.execute("SELECT * FROM runs WHERE owner=? AND request_id=?", (owner, request_id)).fetchone()
            if existing:
                if existing['fingerprint'] != fingerprint:
                    raise ValueError("request_id_conflict")
                return dict(existing), False
            if db.execute("SELECT 1 FROM runs WHERE session_id=? AND status='running'", (session_id,)).fetchone():
                raise ValueError("session_run_active")
            run_id = uuid.uuid4().hex
            db.execute("INSERT INTO runs(run_id,owner,request_id,session_id,fingerprint,status,heartbeat,payload) VALUES (?,?,?,?,?,'running',?,?)", (run_id, owner, request_id, session_id, fingerprint, time.time(), json.dumps(payload or {}, ensure_ascii=False)))
            self._event(db, run_id, {"type": "start", "data": {"session_id": session_id, "run_id": run_id}})
            return dict(db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()), True
        return await asyncio.to_thread(self._call, operation)

    async def append(self, run_id, event):
        def operation(db):
            row = db.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row or row[0] != 'running':
                return
            self._event(db, run_id, event)
            status = {"complete": "completed", "fatal_error": "failed", "incomplete": "failed", "interrupted": "cancelled"}.get(event.get('type'), 'running')
            db.execute("UPDATE runs SET status=?,heartbeat=? WHERE run_id=?", (status, time.time(), run_id))
        await asyncio.to_thread(self._call, operation)

    async def heartbeat(self, run_id):
        def operation(db):
            db.execute("UPDATE runs SET heartbeat=? WHERE run_id=? AND status='running'", (time.time(), run_id))
            row = db.execute("SELECT cancel_requested FROM runs WHERE run_id=?", (run_id,)).fetchone()
            return bool(row and row[0])
        return await asyncio.to_thread(self._call, operation)

    async def cancel_session(self, session_id):
        return bool(await asyncio.to_thread(self._call, lambda db: db.execute("UPDATE runs SET cancel_requested=1 WHERE session_id=? AND status='running'", (session_id,)).rowcount))

    async def events(self, run_id, after=0):
        return await asyncio.to_thread(self._call, lambda db: [(row[0], json.loads(row[1])) for row in db.execute("SELECT sequence,payload FROM events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT 200", (run_id, after))])

    def start(self, run_id: str, producer: Callable[[], AsyncIterator[str]]):
        task = asyncio.create_task(self._execute(run_id, producer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _execute(self, run_id, producer):
        execution = asyncio.current_task()
        async def pulse():
            while True:
                if await self.heartbeat(run_id):
                    execution.cancel()
                    return
                await asyncio.sleep(1)
        heartbeat = asyncio.create_task(pulse())
        try:
            async for frame in producer():
                if frame.startswith("data: "):
                    event = json.loads(frame[6:])
                    # Admission already emitted the start event with stable IDs.
                    if event.get('type') != 'start':
                        await self.append(run_id, event)
            await self.append(run_id, {"type": "incomplete", "data": {"error": "执行结束但未返回最终结果"}})
        except asyncio.CancelledError:
            await self.append(run_id, {"type": "interrupted", "data": {"reason": "本轮对话已停止"}})
            raise
        except Exception:
            await self.append(run_id, {"type": "fatal_error", "data": {"error": "对话执行失败，请稍后重试"}})
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def stream(self, run_id, after=0):
        while True:
            events = await self.events(run_id, after)
            for sequence, event in events:
                after = sequence
                yield f"id: {sequence}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            row = await self.get(run_id)
            if row is None:
                return
            if row['status'] in TERMINAL:
                # A terminal event may have been committed after our first read.
                if not await self.events(run_id, after):
                    return
                continue
            if not events:
                yield ": keepalive\n\n"
                await asyncio.sleep(0.5)


_store = None


def get_app_run_store() -> AppRunStore:
    global _store
    if _store is None:
        from app.utils.path_config import get_data_registry
        _store = AppRunStore(get_data_registry() / 'social' / 'app_runs.sqlite3')
    return _store

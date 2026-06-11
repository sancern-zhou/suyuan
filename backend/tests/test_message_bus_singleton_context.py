import asyncio

import pytest
from sqlalchemy import text

from app.agent.core.executor import ToolExecutor
from app.agent.memory.hybrid_manager import HybridMemoryManager
from app.agent.react_agent import ReActAgent
from app.agent.runtime.session_advisory_lock import _session_lock_key, session_advisory_lock
from app.agent.session.models import Session
from app.agent.session.session_manager_db import SessionManagerDB
from app.social.message_bus_singleton import (
    get_current_bot_account,
    get_current_channel,
    get_current_chat_id,
    reset_current_context,
    set_current_context,
)


def test_social_context_is_isolated_between_async_tasks():
    async def worker(channel: str, chat_id: str, bot_account: str, delay: float):
        tokens = set_current_context(
            channel=channel,
            chat_id=chat_id,
            bot_account=bot_account,
        )
        try:
            await asyncio.sleep(delay)
            return (
                get_current_channel(),
                get_current_chat_id(),
                get_current_bot_account(),
            )
        finally:
            reset_current_context(tokens)

    async def run():
        return await asyncio.gather(
            worker("weixin:auto_a", "chat_a", "bot_a", 0.02),
            worker("qq", "chat_b", "bot_b", 0.01),
        )

    assert asyncio.run(run()) == [
        ("weixin:auto_a", "chat_a", "bot_a"),
        ("qq", "chat_b", "bot_b"),
    ]


def test_session_advisory_lock_key_is_session_scoped():
    assert _session_lock_key("session_a") == _session_lock_key("session_a")
    assert _session_lock_key("session_a") != _session_lock_key("session_b")


@pytest.mark.asyncio
async def test_session_advisory_lock_uses_autocommit_connection(monkeypatch):
    class FakeResult:
        def scalar(self):
            return True

    class FakeConnection:
        def __init__(self):
            self.execution_options_calls = []
            self.statements = []
            self.invalidated = False

        async def execution_options(self, **kwargs):
            self.execution_options_calls.append(kwargs)
            return self

        async def execute(self, statement, params):
            self.statements.append((str(statement), params))
            return FakeResult()

        async def invalidate(self):
            self.invalidated = True

    class FakeConnectContext:
        def __init__(self, connection):
            self.connection = connection

        async def __aenter__(self):
            return self.connection

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def __init__(self, connection):
            self.connection = connection
            self.pool = type(
                "Pool",
                (),
                {
                    "status": lambda self: "fake",
                    "size": lambda self: 1,
                    "checkedout": lambda self: 0,
                    "overflow": lambda self: 0,
                },
            )()

        def connect(self):
            return FakeConnectContext(self.connection)

    connection = FakeConnection()
    monkeypatch.setattr(
        "app.agent.runtime.session_advisory_lock.engine",
        FakeEngine(connection),
    )

    async with session_advisory_lock("session_a"):
        pass

    assert connection.execution_options_calls == [{"isolation_level": "AUTOCOMMIT"}]
    assert connection.statements[0][0] == str(text("SELECT pg_advisory_lock(:key)"))
    assert connection.statements[1][0] == str(text("SELECT pg_advisory_unlock(:key) AS unlocked"))
    assert connection.invalidated is False


@pytest.mark.asyncio
async def test_session_advisory_lock_invalidates_connection_when_unlock_fails(monkeypatch):
    class FakeResult:
        def __init__(self, unlocked):
            self.unlocked = unlocked

        def scalar(self):
            return self.unlocked

    class FakeConnection:
        def __init__(self):
            self.execute_count = 0
            self.invalidated = False

        async def execution_options(self, **kwargs):
            return self

        async def execute(self, statement, params):
            self.execute_count += 1
            return FakeResult(unlocked=self.execute_count == 1)

        async def invalidate(self):
            self.invalidated = True

    class FakeConnectContext:
        def __init__(self, connection):
            self.connection = connection

        async def __aenter__(self):
            return self.connection

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def __init__(self, connection):
            self.connection = connection
            self.pool = type(
                "Pool",
                (),
                {
                    "status": lambda self: "fake",
                    "size": lambda self: 1,
                    "checkedout": lambda self: 0,
                    "overflow": lambda self: 0,
                },
            )()

        def connect(self):
            return FakeConnectContext(self.connection)

    connection = FakeConnection()
    monkeypatch.setattr(
        "app.agent.runtime.session_advisory_lock.engine",
        FakeEngine(connection),
    )

    async with session_advisory_lock("session_a"):
        pass

    assert connection.invalidated is True


@pytest.mark.asyncio
async def test_react_agent_creates_run_scoped_executor(monkeypatch):
    captured_executors = []

    class FakeLoop:
        def __init__(self, *, tool_executor, **kwargs):
            captured_executors.append(tool_executor)

        async def run(self, **kwargs):
            yield {"type": "complete", "data": {"answer": "ok"}}

    monkeypatch.setattr("app.agent.react_agent.ReActLoop", FakeLoop)

    agent = ReActAgent(tool_registry={"dummy": lambda **kwargs: {"success": True}})

    async def drain(session_id):
        async for _ in agent.analyze(
            user_query=f"query {session_id}",
            session_id=session_id,
            manual_mode=None,
            enhance_with_history=False,
        ):
            pass

    await asyncio.gather(drain("session_a"), drain("session_b"))

    assert len(captured_executors) == 2
    assert captured_executors[0] is not captured_executors[1]
    executors_by_session = {
        executor.memory_manager.session_id: executor
        for executor in captured_executors
    }
    assert set(executors_by_session) == {"session_a", "session_b"}


@pytest.mark.asyncio
async def test_tool_executor_supports_run_scoped_clone_without_mutating_parent():
    parent = ToolExecutor(tool_registry={})
    memory_a = HybridMemoryManager(session_id="session_a")
    memory_b = HybridMemoryManager(session_id="session_b")

    executor_a = parent.clone_for_run(memory_a)
    executor_b = parent.clone_for_run(memory_b)

    assert parent.memory_manager is None
    assert parent.data_context_manager is None
    assert executor_a.memory_manager.session_id == "session_a"
    assert executor_b.memory_manager.session_id == "session_b"
    assert executor_a is not executor_b


@pytest.mark.asyncio
async def test_db_session_load_defaults_to_repository_not_worker_cache(monkeypatch):
    manager = SessionManagerDB(enable_cache=True)
    manager.sessions["same_session"] = Session(
        session_id="same_session",
        query="stale",
        conversation_history=[{"type": "user", "content": "old"}],
    )

    async def fake_get_session_with_messages(session_id, include_messages=True):
        return {
            "session_id": session_id,
            "query": "fresh",
            "created_at": "2026-06-03T00:00:00",
            "updated_at": "2026-06-03T00:01:00",
            "conversation_history": [{"type": "user", "content": "new"}],
            "data_ids": [],
            "visual_ids": [],
            "office_documents": [],
            "metadata": {},
            "error": None,
            "current_step": None,
            "current_expert": None,
        }

    monkeypatch.setattr(manager.repository, "get_session_with_messages", fake_get_session_with_messages)

    loaded = await manager.load_session("same_session")

    assert loaded.query == "fresh"
    assert loaded.conversation_history[0]["content"] == "new"

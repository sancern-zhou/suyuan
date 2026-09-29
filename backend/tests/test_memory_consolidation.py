from types import SimpleNamespace

import pytest

from app.agent.memory.unified_memory_manager import UnifiedMemoryManager
from app.agent.react_agent import ReActAgent


@pytest.mark.asyncio
async def test_consolidation_processes_every_batch_and_persists_cursor(tmp_path, monkeypatch):
    messages = [{"role": "user", "content": f"message_{index}"} for index in range(53)]
    manager = UnifiedMemoryManager(base_workspace=str(tmp_path))
    agent = ReActAgent.__new__(ReActAgent)
    agent.memory_manager = manager
    agent._session_store = {
        "session_a": {
            "memory": SimpleNamespace(session=SimpleNamespace(get_messages_for_llm=lambda: messages))
        }
    }
    prompts = []

    class FakeConsolidator:
        async def analyze(self, *, user_query, **kwargs):
            prompts.append(user_query)
            yield {"type": "complete"}

    monkeypatch.setattr(
        "app.agent.memory_consolidator_factory.create_memory_consolidator_agent",
        FakeConsolidator,
    )

    await agent._background_memory_consolidation("session_a", "global", "expert")

    assert len(prompts) == 6
    assert "message_0" in prompts[0]
    assert "message_9" in prompts[0]
    assert "message_10" in prompts[1]
    assert "message_52" in prompts[-1]
    assert "message_10" not in prompts[0]
    restarted = UnifiedMemoryManager(base_workspace=str(tmp_path))
    assert (await restarted.get_consolidation_cursor("expert", "session_a"))["offset"] == 53


@pytest.mark.asyncio
async def test_failed_batch_retries_without_skipping_messages(tmp_path, monkeypatch):
    messages = [{"role": "user", "content": f"message_{index}"} for index in range(50)]
    manager = UnifiedMemoryManager(base_workspace=str(tmp_path))
    agent = ReActAgent.__new__(ReActAgent)
    agent.memory_manager = manager
    agent._session_store = {
        "session_a": {
            "memory": SimpleNamespace(session=SimpleNamespace(get_messages_for_llm=lambda: messages))
        }
    }
    prompts = []
    fail_second = True

    class FakeConsolidator:
        async def analyze(self, *, user_query, **kwargs):
            prompts.append(user_query)
            if fail_second and len(prompts) == 2:
                yield {"type": "error", "data": {"error": "provider unavailable"}}
            else:
                yield {"type": "complete"}

    monkeypatch.setattr(
        "app.agent.memory_consolidator_factory.create_memory_consolidator_agent",
        FakeConsolidator,
    )

    await agent._background_memory_consolidation("session_a", "global", "expert")
    assert (await manager.get_consolidation_cursor("expert", "session_a"))["offset"] == 10

    fail_second = False
    await agent._background_memory_consolidation("session_a", "global", "expert", force=True)
    assert "message_10" in prompts[2]
    assert (await manager.get_consolidation_cursor("expert", "session_a"))["offset"] == 50


@pytest.mark.asyncio
async def test_consolidation_scheduler_coalesces_same_session(tmp_path):
    agent = ReActAgent.__new__(ReActAgent)
    calls = []

    async def fake_consolidation(session_id, user_id, mode, *, force=False):
        calls.append((session_id, user_id, mode, force))

    agent._background_memory_consolidation = fake_consolidation
    agent._schedule_memory_consolidation("session_a", "global", "expert")
    agent._schedule_memory_consolidation("session_a", "global", "expert", force=True)
    task = agent._memory_consolidation_tasks["expert"]
    await task

    assert calls == [("session_a", "global", "expert", True)]

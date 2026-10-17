"""Storage contract: shared per mode, isolated per social user."""
import asyncio
from pathlib import Path

import pytest

from app.agent.memory.memory_store import ImprovedMemoryStore, MemoryStore
from app.agent.memory.unified_memory_manager import UnifiedMemoryManager
from app.agent.memory.curated_facts import CuratedFactStore
from app.agent.memory.memory_paths import memory_workspace
from app.social.user_memory_manager import UserMemoryManager


def test_non_social_memory_is_shared_within_mode(tmp_path):
    first = ImprovedMemoryStore(user_id="user1", mode="expert", workspace=tmp_path)
    second = ImprovedMemoryStore(user_id="user2", mode="expert", workspace=tmp_path)
    other = ImprovedMemoryStore(user_id="user1", mode="query", workspace=tmp_path)
    first.memory_file.write_text("shared preference", encoding="utf-8")
    assert first.workspace == second.workspace == tmp_path / "expert"
    assert "shared preference" in second.get_memory_context()
    assert "shared preference" not in other.get_memory_context()


def test_social_uses_same_implementation_but_isolates_users(tmp_path):
    first = ImprovedMemoryStore(user_id="wx:bot:one", mode="social", workspace=tmp_path)
    second = ImprovedMemoryStore(user_id="wx:bot:two", mode="social", workspace=tmp_path)
    first.memory_file.write_text("one only", encoding="utf-8")
    assert first.workspace == tmp_path / "wx_bot_one"
    assert "one only" not in second.get_memory_context()
    assert not (tmp_path / "social").exists()


@pytest.mark.parametrize("mode,user", [("../outside",None), ("/outside",None),
    ("query/../../outside",None), ("social",None), ("social","global"),
    ("social","wx:../outside"), ("social", "wx:foo\\bar"),
    ("memory_consolidator",None)])
def test_invalid_targets_rejected(tmp_path, mode, user):
    with pytest.raises(ValueError):
        memory_workspace(mode, user, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mode,user", [("expert","global"), ("social","wx:bot:one")])
def test_facts_and_resident_memory_are_separate_in_same_scope(tmp_path, mode, user):
    store = ImprovedMemoryStore(user_id=user, mode=mode, workspace=tmp_path)
    before = store.read_long_term()
    facts = CuratedFactStore(store.workspace)
    result = facts.add(fact="Prefer concise answers", category="用户偏好",
                       source_ref="session:1", applies_when=mode)
    assert result["status"] == "created"
    assert "Prefer concise answers" in facts.index()
    assert store.read_long_term() == before
    assert facts.replace(result["fact_id"], "Use short answers") == "replaced"
    assert facts.remove(result["fact_id"]) == "removed"
    assert facts.index() == ""


async def test_social_manager_honors_configured_root(tmp_path):
    manager = UserMemoryManager(base_workspace=tmp_path)
    store = await manager.get_user_memory("wx:bot:one")
    assert store.workspace == tmp_path / "wx_bot_one"
    assert await manager.get_user_memory("wx:bot:one") is store


async def test_consolidation_cursor_is_durable_and_session_scoped(tmp_path):
    manager = UnifiedMemoryManager(base_workspace=str(tmp_path))
    await manager.set_consolidation_cursor("expert", "session_a", 10, "digest")
    restarted = UnifiedMemoryManager(base_workspace=str(tmp_path))
    assert await restarted.get_consolidation_cursor("expert", "session_a") == {
        "offset": 10, "boundary_hash": "digest"}
    assert (await restarted.get_consolidation_cursor("expert", "session_b"))["offset"] == 0
    with pytest.raises(ValueError):
        await restarted.get_consolidation_cursor("../outside", "session_a")


async def test_cached_store_snapshots_are_task_local(tmp_path):
    store = ImprovedMemoryStore(mode="expert", workspace=tmp_path)
    store.memory_file.write_text("first", encoding="utf-8")
    ready = asyncio.Event()
    second_ready = asyncio.Event()

    async def first_run():
        store.create_snapshot()
        ready.set()
        await second_ready.wait()
        assert "first" in store.get_memory_context()
        assert "second" not in store.get_memory_context()
        store.cleanup_snapshot()

    async def second_run():
        await ready.wait()
        store.memory_file.write_text("second", encoding="utf-8")
        store.create_snapshot()
        second_ready.set()
        assert "second" in store.get_memory_context()
        store.cleanup_snapshot()

    await asyncio.gather(first_run(), second_run())
    assert not list(store.workspace.glob("memory_snapshot_*"))


async def test_fact_context_does_not_leak_between_tasks(tmp_path, monkeypatch):
    import app.agent.memory.memory_paths as paths
    from app.tools.social.remember_fact.tool import RememberFactTool
    monkeypatch.setattr(paths, "get_memory_dir", lambda: tmp_path)
    ready = asyncio.Event()
    tool = RememberFactTool()

    async def scoped():
        tool.set_memory_context("expert", "global")
        ready.set()
        await asyncio.sleep(0)
        result = await tool.execute(fact="Scoped fact", category="领域知识",
                                    source_ref="session:2", applies_when="expert")
        tool.clear_memory_context()
        assert result["success"]

    async def unscoped():
        await ready.wait()
        result = await tool.execute(fact="Wrong fact", category="领域知识",
                                    source_ref="session:3", applies_when="expert")
        assert not result["success"]

    await asyncio.gather(scoped(), unscoped())
    assert "Wrong fact" not in CuratedFactStore(tmp_path / "expert").index()


@pytest.mark.parametrize("mode", ["social", "enforcement_exam"])
async def test_social_run_without_user_scoped_store_fails_closed(mode):
    from app.agent.react_agent import ReActAgent
    agent = ReActAgent.__new__(ReActAgent)
    agent.enable_memory = True
    with pytest.raises(ValueError, match="user-scoped"):
        await anext(agent.analyze(user_query="hello", manual_mode=mode))


async def test_unified_manager_selects_default_social_root(tmp_path, monkeypatch):
    import app.agent.memory.memory_paths as paths
    import app.agent.memory.unified_memory_manager as manager_module
    monkeypatch.setattr(paths, "get_social_memory_dir", lambda: tmp_path / "social")
    monkeypatch.setattr(manager_module, "get_memory_dir", lambda: tmp_path / "shared")
    store = await UnifiedMemoryManager().get_user_memory("wx:bot:one", "social")
    assert store.workspace == tmp_path / "social" / "wx_bot_one"

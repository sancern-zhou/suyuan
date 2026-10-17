"""Exercise real fact tools under both memory scopes, without touching live data."""
import pytest

from app.agent.memory.active_memory_retriever import build_memory_context
from app.agent.memory.memory_store import ImprovedMemoryStore
from app.tools.social.remember_fact.tool import RememberFactTool
from app.tools.social.replace_memory.tool import ReplaceMemoryTool
from app.tools.social.remove_memory.tool import RemoveMemoryTool

TOOLS = (RememberFactTool, ReplaceMemoryTool, RemoveMemoryTool)


@pytest.fixture(autouse=True)
def isolated_context():
    for tool in TOOLS:
        tool.clear_memory_context()
    yield
    for tool in TOOLS:
        tool.clear_memory_context()


@pytest.mark.parametrize("mode,user", [("expert", "global"), ("social", "wx:bot:one")])
async def test_fact_tool_lifecycle_uses_same_scope_as_resident_memory(tmp_path, monkeypatch, mode, user):
    import app.agent.memory.memory_paths as paths
    monkeypatch.setattr(paths, "get_memory_dir", lambda: tmp_path / "shared")
    monkeypatch.setattr(paths, "get_social_memory_dir", lambda: tmp_path / "social")
    store = ImprovedMemoryStore(mode=mode, user_id=user)
    resident = store.read_long_term()
    for tool in TOOLS:
        tool.set_memory_context(mode, user)
    created = await RememberFactTool().execute(
        fact="Concise answers", category="用户偏好", source_ref="session:1", applies_when=mode)
    assert created["success"]
    assert "Concise answers" in build_memory_context(store, "preferences")
    replaced = await ReplaceMemoryTool().execute(old_text=created["fact_id"], new_text="Short answers")
    assert replaced["success"]
    assert "Short answers" in build_memory_context(store, "preferences")
    removed = await RemoveMemoryTool().execute(old_text=created["fact_id"])
    assert removed["success"]
    assert "Short answers" not in build_memory_context(store, "preferences")
    assert store.read_long_term() == resident


@pytest.mark.parametrize("mode,user", [(None, None), ("memory_consolidator", "global"),
                                      ("social", None), ("social", "global"),
                                      ("../escape", "global"), ("social", "wx:../escape")])
async def test_all_fact_tools_reject_unknown_or_unsafe_targets(tmp_path, monkeypatch, mode, user):
    import app.agent.memory.memory_paths as paths
    monkeypatch.setattr(paths, "get_memory_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "get_social_memory_dir", lambda: tmp_path)
    for tool in TOOLS:
        tool.set_memory_context(mode, user)
    assert not (await RememberFactTool().execute(
        fact="Invalid", category="领域知识", source_ref="s:1", applies_when="all"))["success"]
    assert not (await ReplaceMemoryTool().execute(old_text="Invalid", new_text="Other"))["success"]
    assert not (await RemoveMemoryTool().execute(old_text="Invalid"))["success"]
    assert list(tmp_path.iterdir()) == []

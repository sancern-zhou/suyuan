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


def test_social_memory_context_includes_curated_facts_index(tmp_path):
    """社交整合器把晋升事实写入 facts/*.md，注入端必须渲染其索引（否则写而不读）。"""
    from app.agent.memory.active_memory_retriever import build_memory_context
    from app.agent.memory.curated_facts import CuratedFactStore

    workspace = tmp_path / "wx_user1"
    workspace.mkdir()
    CuratedFactStore(workspace).add(
        fact="用户偏好简洁回复",
        category="用户偏好",
        source_ref="social_session_x [3]",
        applies_when="社交对话",
    )
    fake_store = SimpleNamespace(workspace=workspace, read_long_term=lambda: "")

    context = build_memory_context(fake_store, query="随便聊聊")

    assert "已整理事实索引" in context
    assert "用户偏好简洁回复" in context
    assert "social_session_x [3]" in context


def test_consolidation_prompt_follows_two_layer_contract():
    """整合提示词：只写事实层，MEMORY.md 为只读判重背景；旧容量契约不得残留。"""
    prompt = ReActAgent._build_consolidation_prompt(
        None,
        [{"role": "user", "content": "需要记住的事"}],
        "expert",
        existing_memory="# 长期记忆 (MEMORY.md)\n\n## 用户偏好\n",
    )
    assert "facts/*.md" in prompt
    assert "只读背景" in prompt
    assert "remember_fact" in prompt
    assert "3000" not in prompt
    assert "使用率" not in prompt
    assert "记忆文件路径" not in prompt

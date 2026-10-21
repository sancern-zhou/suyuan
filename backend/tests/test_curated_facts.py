from datetime import date, timedelta

import pytest

from app.agent.memory.curated_facts import CuratedFactStore


def test_curated_facts_deduplicate_and_render_compact_index(tmp_path):
    store = CuratedFactStore(tmp_path)
    created = store.add(
        fact="报告审核优先核对数据口径",
        category="feedback",
        source_ref="session-a:messages-1-10",
        applies_when="report review",
    )
    assert created["status"] == "created"
    duplicate = store.add(
        fact="报告审核优先核对数据口径",
        category="feedback",
        source_ref="session-b:messages-1-10",
        applies_when="report review",
    )
    assert duplicate["status"] == "duplicate"
    index = store.index()
    assert "报告审核优先核对数据口径" in index
    assert "session-a:messages-1-10" in index
    assert "适用：report review" in index


def test_curated_facts_reject_expired_and_ambiguous_mutations(tmp_path):
    store = CuratedFactStore(tmp_path)
    with pytest.raises(ValueError):
        store.add(
            fact="过期事实", category="project",
            source_ref="session:1", applies_when="当前任务",
            valid_until=(date.today() - timedelta(days=1)).isoformat(),
        )
    store.add(fact="同样的规则 A", category="project", source_ref="session:1", applies_when="当前任务")
    store.add(fact="同样的规则 B", category="project", source_ref="session:2", applies_when="当前任务")
    assert store.replace("规则", "新规则") == "ambiguous"


def test_curated_facts_require_provenance(tmp_path):
    with pytest.raises(ValueError):
        CuratedFactStore(tmp_path).add(fact="没有来源", category="project")


def test_curated_facts_index_purges_expired_files(tmp_path):
    """过期事实：索引不再展示，且文件被物理清除（事实层的"遗忘"）。"""
    store = CuratedFactStore(tmp_path)
    store.add(
        fact="长期有效的口径", category="project",
        source_ref="session:1", applies_when="当前任务",
    )
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    expired_path = store.root / "fact-expired0000000000.md"
    expired_path.write_text(
        "---\n"
        "name: fact-expired0000000000\n"
        "description: 临时口径，月底失效\n"
        "metadata:\n"
        "  type: project\n"
        f"  valid_until: '{yesterday}'\n"
        "---\n\n"
        "临时口径，月底失效\n",
        encoding="utf-8",
    )
    assert expired_path.exists()

    index = store.index()

    assert "长期有效的口径" in index
    assert "临时口径" not in index
    assert not expired_path.exists()


async def test_remember_fact_routes_to_mode_facts_dir(tmp_path, monkeypatch):
    """三件套为后台整合器专用：非社交上下文写入该模式 facts/*.md。"""
    import app.tools.social.remember_fact.tool as remember_mod

    monkeypatch.setattr("app.agent.memory.memory_paths.get_memory_dir", lambda: tmp_path)
    try:
        remember_mod._memory_context.set(("report", "global"))
        result = await remember_mod.RememberFactTool().execute(
            fact="区域对比需注明城市口径",
            category="领域知识",
            source_ref="report_session_x [3]",
            applies_when="report 模式区域对比",
        )
        assert result["success"] is True
        facts = list((tmp_path / "report" / "facts").glob("fact-*.md"))
        assert len(facts) == 1
        assert "区域对比" in facts[0].read_text(encoding="utf-8")
    finally:
        remember_mod._memory_context.set((None, None))


async def test_remember_fact_routes_to_social_user_facts_dir(tmp_path, monkeypatch):
    """助理模式按用户隔离：事实写入该用户 facts/*.md，而非 MEMORY.md。"""
    import app.tools.social.remember_fact.tool as remember_mod

    monkeypatch.setattr("app.agent.memory.memory_paths.get_social_memory_dir", lambda: tmp_path)
    try:
        remember_mod._memory_context.set(("assistant", "wx:oUser_1"))
        result = await remember_mod.RememberFactTool().execute(
            fact="用户偏好简洁回复",
            category="用户偏好",
            source_ref="social_session_x [5]",
            applies_when="社交对话",
        )
        assert result["success"] is True
        facts = list((tmp_path / "wx_oUser_1" / "facts").glob("fact-*.md"))
        assert len(facts) == 1
        assert not (tmp_path / "wx_oUser_1" / "MEMORY.md").exists()
    finally:
        remember_mod._memory_context.set((None, None))


async def test_memory_tools_refuse_consolidator_target_mode(tmp_path, monkeypatch):
    """解析到 memory_consolidator 时，记忆工具必须拒绝写入而不是落进不可见目录。"""
    import app.tools.social.remember_fact.tool as remember_mod
    import app.tools.social.remove_memory.tool as remove_mod
    import app.tools.social.replace_memory.tool as replace_mod

    monkeypatch.setattr(
        "app.agent.memory.memory_paths.get_memory_dir", lambda: tmp_path
    )
    try:
        for module in (remember_mod, replace_mod, remove_mod):
            module._memory_context.set(("memory_consolidator", "global"))

        remember_result = await remember_mod.RememberFactTool().execute(
            fact="整合产出事实",
            category="领域知识",
            source_ref="report_session_x [1]",
            applies_when="report 模式",
        )
        assert remember_result["success"] is False
        assert "memory_consolidator" in remember_result["error"]

        replace_result = await replace_mod.ReplaceMemoryTool().execute(
            old_text="旧事实", new_text="新事实",
        )
        assert replace_result["success"] is False

        remove_result = await remove_mod.RemoveMemoryTool().execute(old_text="旧事实")
        assert remove_result["success"] is False

        # 拒绝路径不得在任何模式目录产生事实文件
        assert list(tmp_path.rglob("fact-*.md")) == []
    finally:
        for module in (remember_mod, replace_mod, remove_mod):
            module._memory_context.set((None, None))

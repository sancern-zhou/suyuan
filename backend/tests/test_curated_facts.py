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

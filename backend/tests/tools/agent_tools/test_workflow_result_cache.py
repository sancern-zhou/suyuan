"""节点成果缓存：store/load、goal 哈希失效、依赖闭包复用选择。"""

import json

from app.agent.workflow.result_cache import (
    _node_path,
    goal_hash,
    load_node_result,
    select_reusable_nodes,
    store_node_result,
)


def test_store_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.agent.workflow.result_cache._cache_root", lambda: tmp_path / "workflow_cache"
    )
    result = {"status": "success", "data": {"file_paths": ["a.json"]}}
    assert store_node_result("wf-1", "met", "按风速分箱", "expert_meteorology", result)
    loaded = load_node_result("wf-1", "met", "按风速分箱", "expert_meteorology")
    assert loaded == result


def test_goal_change_invalidates_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.agent.workflow.result_cache._cache_root", lambda: tmp_path / "workflow_cache"
    )
    store_node_result("wf-1", "met", "按风速分箱", "expert_meteorology", {"v": 1})
    assert load_node_result("wf-1", "met", "按风速分箱（改为>4m/s）", "expert_meteorology") is None
    assert load_node_result("wf-1", "met", "按风速分箱", "expert_analysis") is None
    assert load_node_result("wf-2", "met", "按风速分箱", "expert_meteorology") is None


def test_goal_hash_is_whitespace_stable():
    assert goal_hash("a  b", "expert") == goal_hash(" a   b ", "expert")
    assert goal_hash("a", "expert") != goal_hash("a", "query")


def test_select_reusable_respects_dependency_closure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.agent.workflow.result_cache._cache_root", lambda: tmp_path / "workflow_cache"
    )
    nodes = [
        {"task_id": "air", "target_mode": "query", "goal": "取空气质量", "dependencies": []},
        {"task_id": "met", "target_mode": "query", "goal": "取气象", "dependencies": []},
        {"task_id": "corr", "target_mode": "expert_analysis", "goal": "相关性", "dependencies": ["air", "met"]},
        {"task_id": "report-prep", "target_mode": "expert", "goal": "整合准备", "dependencies": ["corr"]},
    ]
    # 只有 air 与 corr 入过缓存（met 本次 goal 变了）
    store_node_result("wf-1", "air", "取空气质量", "query", {"r": "air"})
    store_node_result("wf-1", "corr", "相关性", "expert_analysis", {"r": "corr"})

    reusable = select_reusable_nodes("wf-1", nodes)
    # met 未命中 → corr 与 report-prep 即使有缓存也必须重跑
    assert set(reusable) == {"air"}


def test_dependency_result_change_invalidates_downstream_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.agent.workflow.result_cache._cache_root", lambda: tmp_path / "workflow_cache"
    )
    from app.agent.workflow.result_cache import result_fingerprint

    source = {"rows": [1]}
    derived = {"summary": "from source"}
    store_node_result("wf-dep", "source", "取数据", "query", source)
    store_node_result(
        "wf-dep",
        "derived",
        "汇总",
        "expert_analysis",
        derived,
        dependency_hashes={"source": result_fingerprint(source)},
    )
    nodes = [
        {"task_id": "source", "target_mode": "query", "goal": "取数据", "dependencies": []},
        {"task_id": "derived", "target_mode": "expert_analysis", "goal": "汇总", "dependencies": ["source"]},
    ]
    assert set(select_reusable_nodes("wf-dep", nodes)) == {"source", "derived"}
    store_node_result("wf-dep", "source", "取数据", "query", {"rows": [2]})
    assert set(select_reusable_nodes("wf-dep", nodes)) == {"source"}


def test_oversize_result_is_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.agent.workflow.result_cache._cache_root", lambda: tmp_path / "workflow_cache"
    )
    big = {"blob": "x" * (600 * 1024)}
    assert store_node_result("wf-1", "big", "g", "query", big) is False
    assert load_node_result("wf-1", "big", "g", "query") is None


def test_corrupt_cache_file_fails_soft(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.agent.workflow.result_cache._cache_root", lambda: tmp_path / "workflow_cache"
    )
    store_node_result("wf-1", "met", "g", "query", {"r": 1})
    path = _node_path("wf-1", "met")
    path.write_text("{broken", encoding="utf-8")
    assert load_node_result("wf-1", "met", "g", "query") is None
    # 坏文件不影响再次写入
    assert store_node_result("wf-1", "met", "g2", "query", {"r": 2})
    assert json.loads(path.read_text(encoding="utf-8"))["result"] == {"r": 2}


def test_raw_ids_colliding_after_sanitization_stay_separate(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.agent.workflow.result_cache._cache_root", lambda: tmp_path / "workflow_cache"
    )
    # 旧实现仅做字符过滤："wf/1" 与 "wf1" 会映射到同一条路径互相覆盖
    store_node_result("wf/1", "met", "g", "query", {"v": 1})
    store_node_result("wf1", "met", "g", "query", {"v": 2})
    assert load_node_result("wf/1", "met", "g", "query") == {"v": 1}
    assert load_node_result("wf1", "met", "g", "query") == {"v": 2}


def test_path_components_stay_within_cache_root(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.agent.workflow.result_cache._cache_root", lambda: tmp_path / "workflow_cache"
    )
    path = _node_path("../../escape", "..")
    resolved = path.resolve()
    assert resolved.is_relative_to((tmp_path / "workflow_cache").resolve())
    assert path.exists() is False


def test_workflow_journal_roundtrip(tmp_path):
    from app.agent.workflow.journal import WorkflowJournal

    journal = WorkflowJournal(db_path=tmp_path / "journal.db")
    journal.append(workflow_id="wf-j", event_type="workflow.started")
    journal.append(
        workflow_id="wf-j",
        event_type="node.failed",
        task_id="binning",
        payload={"error": "超时", "progress": {"delivered_files": ["a.json"]}},
    )
    events = journal.recent("wf-j")
    assert [e["event_type"] for e in events] == ["workflow.started", "node.failed"]
    assert events[1]["payload"]["progress"]["delivered_files"] == ["a.json"]
    assert journal.recent("wf-other") == []

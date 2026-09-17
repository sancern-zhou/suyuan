"""Storage isolation, immutable evidence references and concurrent commits."""
import json
from copy import deepcopy

import pytest

from app.services.jiangsu_smart_event import JiangsuSmartEventService
from app.services.jiangsu_smart_event_store import JiangsuEventPackages, EventStoreConflict, SCHEMA
from app.utils.path_config import resolve_agent_path


def event(identity, marker):
    package = {"event_id": identity, "status": "success", "sources": {"monitoring": {"marker": marker}}}
    return {"event_id": identity, "event_name": identity,
            "evidence_package": package, "evidence": {"package": deepcopy(package)},
            "judgment_history": [{"final_response": marker}], "operation_records": [{"summary": marker}]}


def test_migration_keeps_backup_and_separates_detail_and_evidence(tmp_path):
    path = tmp_path / "store.json"
    legacy = {"schema_version": "jiangsu_smart_events/v1", "events": [event("a", "a-only"), event("b", "b-only")], "tasks": []}
    original = json.dumps(legacy).encode()
    path.write_bytes(original)
    storage = JiangsuEventPackages(path)
    storage.save(storage.load())
    assert next((tmp_path / "legacy-backups").glob("*.json")).read_bytes() == original
    manifest = json.loads(path.read_text())
    assert manifest["schema_version"] == SCHEMA
    assert "a-only" not in path.read_text() and "b-only" not in path.read_text()
    for row in manifest["events"]:
        detail = json.loads(resolve_agent_path(row["_detail_ref"]).read_text())
        assert "evidence_package" not in detail
        assert "package" not in detail["evidence"]
        evidence = json.loads(resolve_agent_path(detail["_evidence_ref"]).read_text())
        assert evidence["event_id"] == row["event_id"]
        assert evidence["sources"]["monitoring"]["marker"] == row["event_id"] + "-only"


@pytest.mark.asyncio
async def test_detail_and_ai_load_only_selected_event(tmp_path, monkeypatch):
    service = JiangsuSmartEventService(data_root=tmp_path)
    service._save_store({"events": [event("a", "a-only"), event("b", "b-only")], "tasks": []})
    original = JiangsuEventPackages.read_event
    reads = []
    def selected_only(self, row):
        reads.append(row["event_id"])
        assert row["event_id"] == "a"
        return original(self, row)
    monkeypatch.setattr(JiangsuEventPackages, "read_event", selected_only)
    detail = await service.get_event("a")
    assert detail["evidence_package"]["sources"]["monitoring"]["marker"] == "a-only"
    # Stop at dispatch: no LLM execution is needed to check the evidence contract.
    async def dispatch(store, **kwargs):
        assert kwargs["event_ids"] == {"a"}
        selected = service._stored_event(store, "a")
        assert selected["evidence_package"]["event_id"] == "a"
        return []
    monkeypatch.setattr(service, "_dispatch_pending_tasks", dispatch)
    await service.run_ai_judgment("a")
    assert reads and set(reads) == {"a"}


def test_concurrent_updates_to_different_events_are_preserved(tmp_path):
    storage = JiangsuEventPackages(tmp_path / "store.json")
    storage.save({"events": [event("a", "first"), event("b", "second")], "tasks": []})
    first = storage.load(event_ids={"a"})
    second = storage.load(event_ids={"b"})
    first["events"][0]["event_name"] = "updated-a"
    second["events"][1]["event_name"] = "updated-b"
    storage.save(first)
    storage.save(second)
    assert [e["event_name"] for e in storage.load()["events"]] == ["updated-a", "updated-b"]
    second["events"][1]["event_name"] = "updated-b-again"
    storage.save(second)
    assert [e["event_name"] for e in storage.load()["events"]] == ["updated-a", "updated-b-again"]


def test_conflicting_writes_do_not_silently_overwrite_event(tmp_path):
    storage = JiangsuEventPackages(tmp_path / "store.json")
    storage.save({"events": [event("a", "first")], "tasks": []})
    first, second = storage.load(), storage.load()
    first["events"][0]["event_name"] = "winner"
    second["events"][0]["event_name"] = "stale"
    storage.save(first)
    with pytest.raises(EventStoreConflict):
        storage.save(second)
    assert storage.load()["events"][0]["event_name"] == "winner"


def test_dispatched_evidence_reference_is_immutable(tmp_path):
    storage = JiangsuEventPackages(tmp_path / "store.json")
    storage.save({"events": [event("a", "first")], "tasks": []})
    snapshot = storage.load()
    old_path = resolve_agent_path(snapshot["events"][0]["evidence_package"]["persisted_path"])
    old_bytes = old_path.read_bytes()
    snapshot["events"][0]["evidence_package"]["sources"]["monitoring"]["marker"] = "new"
    storage.save(snapshot)
    assert old_path.read_bytes() == old_bytes
    assert storage.load()["events"][0]["evidence_package"]["persisted_path"] != str(old_path)


def test_evidence_package_splits_sources_into_index_and_files(tmp_path):
    storage = JiangsuEventPackages(tmp_path / "store.json")
    payload = {
        "event_id": "a", "status": "success",
        "sources": {
            "monitoring": {"status": "success", "record_count": 3, "data": {"rows": [1, 2, 3]}},
            "instrument_status": {"status": "success", "data": {"series": [{"p": "PM10"}]}},
            "weather": {"status": "empty"},
        },
    }
    storage.save({"events": [{"event_id": "a", "event_name": "a", "evidence_package": payload}], "tasks": []})

    reference = storage.load()["events"][0]["evidence_package"]["persisted_path"]
    index_path = resolve_agent_path(reference)
    assert index_path.name == "index.json"
    index = json.loads(index_path.read_text())
    assert index["sources"]["monitoring"]["record_count"] == 3
    assert "data" not in index["sources"]["monitoring"]
    assert index["sources"]["weather"] == {"status": "empty"}
    assert json.loads((index_path.parent / "sources" / "monitoring.json").read_text())["data"] == {"rows": [1, 2, 3]}

    restored = storage.read_evidence_package(reference, "a")
    assert restored["sources"]["monitoring"]["data"] == {"rows": [1, 2, 3]}
    assert restored["sources"]["instrument_status"]["data"] == {"series": [{"p": "PM10"}]}


def test_mismatched_evidence_is_rejected_before_manifest_commit(tmp_path):
    storage = JiangsuEventPackages(tmp_path / "store.json")
    wrong = event("a", "first")
    wrong["evidence_package"]["event_id"] = "b"
    with pytest.raises(ValueError, match="identity_mismatch"):
        storage.save({"events": [wrong], "tasks": []})
    assert not storage.path.exists()

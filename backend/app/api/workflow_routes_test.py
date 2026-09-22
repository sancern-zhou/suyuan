from app.api.workflow_routes import _workflow_snapshots


def test_workflow_snapshot_index_supports_multiple_and_legacy_metadata():
    current = {"workflow_coordinators": {"wf-1": {"workflow_id": "wf-1"}}}
    assert list(_workflow_snapshots(current)) == ["wf-1"]

    legacy = {"workflow_coordinator": {"workflow_id": "wf-old", "status": "succeeded"}}
    assert _workflow_snapshots(legacy)["wf-old"]["status"] == "succeeded"

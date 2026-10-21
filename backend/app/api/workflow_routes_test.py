from app.api.workflow_routes import _workflow_snapshots


def test_workflow_snapshot_index_requires_complete_indexed_snapshots():
    current = {"workflow_coordinators": {"wf-1": {"workflow_id": "wf-1"}}}
    assert list(_workflow_snapshots(current)) == ["wf-1"]

    incomplete = {"workflow_coordinators": {"wf-2": {"status": "succeeded"}}}
    assert _workflow_snapshots(incomplete) == {}

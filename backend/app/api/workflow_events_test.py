from app.api.workflow_routes import _workflow_events


def test_workflow_events_are_read_incrementally_from_runtime_journal():
    snapshot = {
        "runtime": {
            "events": [
                {"sequence": 1, "event_type": "task.created"},
                {"sequence": 2, "event_type": "task.running"},
            ]
        }
    }
    assert [event["sequence"] for event in _workflow_events(snapshot)] == [1, 2]
    assert [event["event_type"] for event in _workflow_events(snapshot, after=1)] == ["task.running"]

from app.agent.workflow.templates import build_report_delivery_manifest


def test_report_delivery_manifest_collects_synthesis_and_artifacts():
    snapshot = {
        "definition": {"nodes": [
            {"task_id": "source", "target_mode": "expert"},
            {"task_id": "synthesis", "target_mode": "expert", "dependencies": ["source"]},
            {"task_id": "report", "target_mode": "report", "dependencies": ["synthesis"]},
        ]},
        "node_lineage": {
            "synthesis": {"status": "complete", "evidence": [{"ref_id": "e1"}], "artifacts": []},
            "report": {"status": "complete", "evidence": [], "artifacts": [{"ref_id": "r1", "kind": "report_package", "source_task_id": "report"}]},
        },
        "node_results": {
            "synthesis": {"data": {"result_envelope": {"outputs": {"finding": "ok"}}}}
        },
    }
    manifest = build_report_delivery_manifest(snapshot)
    assert manifest["status"] == "completed"
    assert manifest["synthesis_outputs"]["finding"] == "ok"
    assert manifest["report_artifacts"][0]["ref_id"] == "r1"

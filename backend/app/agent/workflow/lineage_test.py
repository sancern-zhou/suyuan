from app.agent.workflow.lineage import build_node_lineage, validate_node_lineage


def test_node_lineage_normalizes_evidence_and_artifact_references():
    result = {
        "data": {
            "result_envelope": {
                "status": "completed",
                "outputs": {"value": 1},
                "evidence": [{"source": "station.csv"}],
                "artifacts": [{"path": "chart.png"}],
            }
        }
    }
    manifest = build_node_lineage(task_id="air", dependency_task_ids=["source"], result=result)
    assert manifest["inputs"][0]["source_task_id"] == "source"
    assert manifest["evidence"][0]["source_task_id"] == "air"
    assert manifest["artifacts"][0]["kind"] == "artifact"
    assert validate_node_lineage(manifest, expected_task_id="air", expected_dependencies=["source"], require_envelope=True) == []


def test_lineage_detects_missing_dependency_reference():
    manifest = build_node_lineage(task_id="merge", dependency_task_ids=[], result={})
    errors = validate_node_lineage(manifest, expected_task_id="merge", expected_dependencies=["air"])
    assert errors[0]["expected"] == "air"

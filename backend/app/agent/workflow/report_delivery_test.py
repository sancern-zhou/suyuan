from app.agent.workflow.templates import build_report_analysis_manifest


def test_report_analysis_manifest_collects_synthesis_without_delivery_node():
    snapshot = {
        "definition": {"nodes": [
            {"task_id": "source", "target_mode": "expert"},
            {"task_id": "synthesis", "target_mode": "expert", "dependencies": ["source"]},
        ]},
        "node_lineage": {
            "synthesis": {"status": "complete", "evidence": [{"ref_id": "e1"}], "artifacts": []},
        },
        "node_results": {
            "synthesis": {"data": {"result_envelope": {
                "status": "completed",
                "outputs": {"finding": "ok"},
                "data_gaps": [],
            }}}
        },
    }
    manifest = build_report_analysis_manifest(snapshot)
    assert manifest["status"] == "completed"
    assert manifest["synthesis_outputs"]["finding"] == "ok"
    assert manifest["missing"] == []


def test_report_analysis_manifest_exposes_synthesis_gaps():
    snapshot = {
        "definition": {"nodes": [
            {"task_id": "source", "target_mode": "query"},
            {"task_id": "synthesis", "target_mode": "expert", "dependencies": ["source"]},
        ]},
        "node_lineage": {"synthesis": {"status": "complete"}},
        "node_results": {
            "synthesis": {"data": {"result_envelope": {
                "status": "needs_more_evidence",
                "outputs": {},
                "data_gaps": ["缺少气象数据"],
            }}}
        },
    }

    manifest = build_report_analysis_manifest(snapshot)

    assert manifest["status"] == "completed_with_gaps"
    assert manifest["synthesis_status"] == "needs_more_evidence"
    assert manifest["data_gaps"] == ["缺少气象数据"]
    assert manifest["missing"] == [
        "synthesis_status:needs_more_evidence",
        "synthesis_data_gaps",
    ]


def test_report_analysis_manifest_rejects_missing_synthesis_status():
    snapshot = {
        "definition": {"nodes": [
            {"task_id": "source", "target_mode": "query"},
            {"task_id": "synthesis", "target_mode": "expert", "dependencies": ["source"]},
        ]},
        "node_lineage": {"synthesis": {"status": "complete"}},
        "node_results": {
            "synthesis": {"data": {"result_envelope": {"outputs": {"finding": "ok"}}}}
        },
    }

    manifest = build_report_analysis_manifest(snapshot)

    assert manifest["status"] == "completed_with_gaps"
    assert manifest["missing"] == ["synthesis_status:missing"]

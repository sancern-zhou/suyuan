from app.tools.analysis.ops_work_order_audit.tool import _standard_success


def test_rules_result_declares_final_issue_list_and_data_refs(tmp_path):
    final_path = tmp_path / "latest_finished_work_orders_final_issue_list.json"
    audit_path = tmp_path / "audit.json"
    result = _standard_success(
        "ops_audit_run_rules",
        "done",
        {
            "final_issue_list_path": str(final_path),
            "audit_result_path": str(audit_path),
            "data_id": "ops_audit_rule_summary:v1:a",
        },
    )
    files = result["refs"]["files"]
    final_ref = next(ref for ref in files if ref.get("logical_key") == "ops_audit.final_issue_list")
    assert final_ref["path"] == str(final_path)
    assert final_ref["label"] == "Final issue list"
    assert final_ref["importance"] == "high"
    assert {ref["path"] for ref in files} == {str(final_path), str(audit_path)}
    assert result["refs"]["data"][0]["data_id"] == "ops_audit_rule_summary:v1:a"

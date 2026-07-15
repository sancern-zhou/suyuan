from app.agent.resources.models import ResourceKind
from app.agent.resources.normalizer import normalize_tool_result_refs


def test_explicit_refs_take_precedence_and_preserve_metadata():
    refs, rejected = normalize_tool_result_refs(
        tool_name="ops_audit_run_rules",
        run_id="run-1",
        turn_sequence=3,
        result={
            "refs": {"files": [{
                "path": "/tmp/final.json",
                "logical_key": "ops_audit.final_issue_list",
                "role": "output",
                "label": "Final issue list",
                "importance": "high",
            }]},
            "final_issue_list_path": "/tmp/ignored-compatibility.json",
        },
    )
    assert rejected == []
    assert len(refs) == 1
    assert refs[0].kind is ResourceKind.FILE
    assert refs[0].logical_key == "ops_audit.final_issue_list"
    assert refs[0].locator.path == "/tmp/final.json"


def test_known_nested_compatibility_fields_are_extracted():
    refs, rejected = normalize_tool_result_refs(
        tool_name="legacy_tool",
        run_id="run-2",
        turn_sequence=4,
        result={
            "data": {"data_id": "dataset:v1:abc", "file_path": "/tmp/output.csv"},
            "visuals": [{"id": "visual-a", "title": "Chart"}],
        },
    )
    assert rejected == []
    assert {ref.kind.value for ref in refs} == {"data", "file", "visual"}


def test_free_text_and_arbitrary_path_fields_are_not_extracted():
    refs, rejected = normalize_tool_result_refs(
        tool_name="text_tool",
        run_id="run-3",
        turn_sequence=5,
        result={
            "summary": "Saved at /tmp/not-a-structured-ref.json",
            "final_issue_list_path": "/tmp/not-explicit.json",
        },
    )
    assert refs == []
    assert rejected == []


def test_invalid_explicit_ref_does_not_hide_valid_ref():
    refs, rejected = normalize_tool_result_refs(
        tool_name="mixed_tool",
        run_id="run-4",
        turn_sequence=6,
        result={"refs": {"files": [{"label": "missing path"}], "data": [{"data_id": "ok:v1:1"}]}},
    )
    assert [ref.locator.data_id for ref in refs] == ["ok:v1:1"]
    assert len(rejected) == 1

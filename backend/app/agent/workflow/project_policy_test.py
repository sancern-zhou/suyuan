from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.agent.workflow import project_policy
from app.agent.workflow.delegation import delegation_error, is_leaf_mode
from app.agent.workflow.profiles import get_agent_profile
from app.agent.workflow.protocol import validate_result_schema
from app.agent.workflow.target_mode_contract import target_mode_values
from app.project_config.models import BackendManifest


def configuration():
    return {
        "agent_mode_tools": {"manager": ["run_agent_workflow"], "internal_data": ["read_file"]},
        "mode_prompt_files": {"internal_data": "projects/sample/data.md"},
        "agent_workflow_modes": {"internal_data": {
            "positioning": "data", "scope": "bounded data", "boundary": "no report", "outputs": "data and gaps",
            "max_iterations": 6, "timeout_seconds": 120,
        }},
        "agent_workflow_parents": {"manager": {"child_modes": ["internal_data"]}},
    }


@pytest.fixture
def policy(monkeypatch):
    backend = BackendManifest.model_validate(configuration())
    monkeypatch.setattr(project_policy, "active_backend", lambda: backend)
    return backend


def node():
    return {"target_mode": "internal_data", "task_contract": {
        "protocol_version": "workflow.v1", "question": "count failures",
        "scope": {"time_range": "September", "objects": ["station-a"]},
        "required_evidence": ["source records"], "deliverables": ["data", "gaps"],
    }}


def test_project_children_are_scoped_and_cannot_delegate_or_override_profile(policy):
    assert "internal_data" in target_mode_values()
    assert delegation_error("manager", ["internal_data"]) is None
    assert delegation_error("manager", ["assistant"])
    assert delegation_error("assistant", ["internal_data"])
    assert delegation_error("internal_data", ["query"])
    assert is_leaf_mode("internal_data")
    assert not get_agent_profile("internal_data", profile="orchestrator").allow_delegation
    assert get_agent_profile("manager").allow_delegation


def test_project_modes_do_not_leak_after_switching_project(policy, monkeypatch):
    monkeypatch.setattr(project_policy, "active_backend", lambda: BackendManifest())
    assert "internal_data" not in target_mode_values()
    assert not is_leaf_mode("internal_data")


def test_invalid_manifest_fails_before_runtime():
    for mutate in (
        lambda c: c["agent_mode_tools"]["internal_data"].append("run_agent_workflow"),
        lambda c: c["mode_prompt_files"].clear(),
        lambda c: c["agent_workflow_parents"]["manager"]["child_modes"].append("unknown"),
    ):
        config = configuration()
        mutate(config)
        with pytest.raises(ValidationError):
            BackendManifest.model_validate(config)


def test_node_contract_and_budget_cannot_be_weakened(policy):
    value = node()
    value.update(max_iterations=120, timeout_seconds=3600, result_schema={})
    project_policy.prepare_node(value)
    assert value["max_iterations"] == 6
    assert value["timeout_seconds"] == 120
    from app.agent.workflow.coordinator import WorkflowNodeSpec

    value["task_id"] = "data"
    retry = WorkflowNodeSpec.from_mapping(value).expanded_budget(3)
    assert retry.max_iterations == 6
    assert retry.timeout_seconds == 120
    assert value["result_schema"]["x-evidence-references"]
    for patch in ({"scope": {}}, {"deliverables": ["a", "b", "c", "d"]}, {"required_evidence": "anything"}):
        invalid = node()
        invalid["task_contract"].update(patch)
        with pytest.raises(ValueError):
            project_policy.prepare_node(invalid)
    definition = {"budget": {"max_nodes": 100, "max_retries": 100, "timeout_seconds": 9999}}
    assert project_policy.apply_workflow_limits("manager", definition, 8) == 3
    assert definition["budget"] == {"max_nodes": 12, "max_retries": 3, "max_extensions": 2, "timeout_seconds": 900}


def test_findings_must_reference_unique_locatable_evidence(policy):
    value = node()
    project_policy.prepare_node(value)
    result = {"status": "completed", "findings": [{"statement": "failure", "evidence_ids": ["e1"]}],
              "evidence": [{"id": "e1", "source": "work orders", "locator": "orders.csv row 2"}],
              "uncertainties": [], "data_gaps": []}
    schema = value["result_schema"]
    assert validate_result_schema(result, schema) == []
    for mutate in (
        lambda r: r["findings"][0].update(evidence_ids=["invented"]),
        lambda r: r["evidence"][0].update(locator=""),
        lambda r: r["evidence"].append(deepcopy(r["evidence"][0])),
    ):
        invalid = deepcopy(result)
        mutate(invalid)
        assert validate_result_schema(invalid, schema)

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
    return {"target_mode": "internal_data", "goal": "按指定时间和站点统计故障，交付数据与证据"}


def test_project_children_are_scoped_and_cannot_delegate_or_override_profile(policy):
    assert "internal_data" in target_mode_values()
    assert delegation_error("manager", ["internal_data"]) is None
    assert delegation_error("manager", ["assistant"])
    assert delegation_error("assistant", ["internal_data"])
    assert delegation_error("internal_data", ["query"])
    assert is_leaf_mode("internal_data")
    assert not get_agent_profile("internal_data", profile="orchestrator").allow_delegation
    assert get_agent_profile("manager").allow_delegation


def test_hybrid_parent_keeps_shared_children_and_direct_tool_description(monkeypatch):
    """assistant 这类混合父模式：项目子模式叠加在共享父边界之上，不替换。"""
    config = configuration()
    # 父模式校验要求声明 run_agent_workflow；assistant 共享白名单本就含它。
    config["agent_mode_tools"]["assistant"] = ["run_agent_workflow"]
    config["agent_workflow_parents"]["assistant"] = {"child_modes": ["internal_data"]}
    backend = BackendManifest.model_validate(config)
    monkeypatch.setattr(project_policy, "active_backend", lambda: backend)

    assert delegation_error("assistant", ["internal_data"]) is None
    assert delegation_error("assistant", ["office"]) is None
    assert delegation_error("assistant", ["query_monitoring_station"]) is None
    # 未列入共享父边界或项目清单的目标仍然拒收
    assert delegation_error("assistant", ["query"])
    assert delegation_error("assistant", ["manager"])

    direct = {
        "name": "call_sub_agent",
        "description": "direct delegation tool",
        "parameters": {"type": "object", "properties": {
            "target_mode": {"enum": ["x"], "description": "d"},
        }},
    }
    dag = {
        "name": "run_agent_workflow",
        "description": "dag orchestration tool",
        "parameters": {"type": "object", "properties": {
            "workflow": {"type": "object", "properties": {"nodes": {"type": "array", "items": {
                "type": "object", "properties": {"target_mode": {"enum": ["x"], "description": "d"}},
            }}}},
        }},
    }
    scoped_direct = project_policy.scope_delegation_schema(direct, "assistant")
    direct_target = scoped_direct["parameters"]["properties"]["target_mode"]
    assert "internal_data" in direct_target["enum"]
    assert {"office", "knowledge", "ppt", "board", "ops"} <= set(direct_target["enum"])
    # 一行制定位进 target 描述；原工具描述保留并追加项目子模式契约要求
    assert direct_target["description"].startswith("- internal_data：data；边界：no report")
    assert "direct delegation tool" in scoped_direct["description"]
    assert "goal" in scoped_direct["description"]

    # DAG 工具只收窄 enum：描述与 target 描述原样保留（避免与 call_sub_agent 双份计费）
    scoped_dag = project_policy.scope_delegation_schema(dag, "assistant")
    dag_target = scoped_dag["parameters"]["properties"]["workflow"]["properties"]["nodes"]["items"]["properties"]["target_mode"]
    assert scoped_dag["description"] == "dag orchestration tool"
    assert dag_target["description"] == "d"
    assert set(dag_target["enum"]) == set(direct_target["enum"])

    # 纯项目父模式行为不变：工具描述整体替换为编排契约
    scoped_manager = project_policy.scope_delegation_schema(deepcopy(direct), "manager")
    assert "direct delegation tool" not in scoped_manager["description"]
    assert "项目内部子 Agent 工作流" in scoped_manager["description"]
    assert "internal_data" in scoped_manager["parameters"]["properties"]["target_mode"]["enum"]


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


def test_project_budget_is_bounded_without_replacing_result_schema(policy):
    value = node()
    caller_schema = {"type": "object", "required": ["route_value"]}
    value.update(max_iterations=120, timeout_seconds=3600, result_schema=caller_schema)
    project_policy.prepare_node(value)
    assert value["max_iterations"] == 6
    assert value["timeout_seconds"] == 120
    assert value["result_schema"] is caller_schema
    value["task_id"] = "data"
    from app.agent.workflow.coordinator import WorkflowNodeSpec

    retry = WorkflowNodeSpec.from_mapping(value).expanded_budget(3)
    assert retry.max_iterations == 6
    assert retry.timeout_seconds == 120
    definition = {"budget": {"max_nodes": 100, "max_retries": 100, "timeout_seconds": 9999}}
    assert project_policy.apply_workflow_limits("manager", definition, 8) == 3
    assert definition["budget"] == {"max_nodes": 12, "max_retries": 3, "max_extensions": 2, "timeout_seconds": 900}


def test_project_counter_evidence_is_an_explicit_opt_in_schema(monkeypatch):
    config = configuration()
    config["agent_workflow_modes"]["internal_data"]["require_counter_evidence"] = True
    monkeypatch.setattr(project_policy, "active_backend", lambda: BackendManifest.model_validate(config))
    value = node()
    project_policy.prepare_node(value)
    result = {
        "findings": [{
            "statement": "failure",
            "evidence_ids": ["e1"],
            "counter_evidence": [],
            "alternative_explanations": [],
        }],
        "evidence": [{"id": "e1", "source": "work orders", "locator": "orders.csv row 2"}],
    }
    assert validate_result_schema(result, value["result_schema"]) == []


def test_evidence_reference_validation_remains_available_to_explicit_schemas():
    schema = {"type": "object", "x-evidence-references": True}
    result = {"findings": [{"statement": "failure", "evidence_ids": ["e1"]}],
              "evidence": [{"id": "e1", "source": "work orders", "locator": "orders.csv row 2"}]}
    assert validate_result_schema(result, schema) == []
    for mutate in (
        lambda r: r["findings"][0].update(evidence_ids=["invented"]),
        lambda r: r["evidence"][0].update(locator=""),
        lambda r: r["evidence"].append(deepcopy(r["evidence"][0])),
    ):
        invalid = deepcopy(result)
        mutate(invalid)
        assert validate_result_schema(invalid, schema)

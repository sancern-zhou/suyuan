"""固定问数工作流与 target_mode 契约的项目声明通道契约。

项目专属工具元组与子代理契约只允许出现在 projects/<id>/project.yaml
（backend.fixed_query_workflow_tools / backend.target_mode_contracts），
共享层在导入时合并：已注册 id 并集合并/字段级覆盖，未注册 id 注册新条目。
"""

from types import SimpleNamespace

import pytest

from app.agent.workflow import mode_workflows as mw
from app.agent.workflow import target_mode_contract as tmc
from app.project_config import ProjectConfigError
from app.project_config.models import FixedQueryWorkflowToolsDeclaration


def _manifest_context(backend):
    return SimpleNamespace(manifest=SimpleNamespace(project="demo-project", backend=backend))


def test_fixed_query_workflow_tools_union_into_existing_workflow(monkeypatch):
    declaration = {
        "query_monitoring_station": FixedQueryWorkflowToolsDeclaration(
            tools=["declared_tool_x", "declared_tool_y"]
        )
    }
    base_tools = mw._QUERY_TOOL_SETS["query_monitoring_station"]

    mw._apply_declared_fixed_query_workflows(declaration)

    merged = mw._QUERY_TOOL_SETS["query_monitoring_station"]
    assert "declared_tool_x" in merged and "declared_tool_y" in merged
    # 并集保序：共享基础工具保留在前
    assert list(merged)[: len(base_tools)] == list(base_tools)
    workflow = mw.get_mode_workflow("query_monitoring_station")
    assert "declared_tool_x" in workflow.phases[0].allowed_tools


def test_fixed_query_workflow_declaration_registers_new_workflow(monkeypatch):
    declaration = {
        "test_query_flow_decl": FixedQueryWorkflowToolsDeclaration(
            tools=["execute_python"],
            title="测试项目固定问数流程",
            scope_line="测试范围说明。",
            contract_tables=["StationHour"],
        )
    }

    mw._apply_declared_fixed_query_workflows(declaration)

    workflow = mw.get_mode_workflow("test_query_flow_decl")
    assert workflow is not None
    assert workflow.description == "测试项目固定问数流程"
    assert "测试范围说明。" in workflow.phases[0].description
    assert "StationHour" in workflow.phases[0].description
    assert list(workflow.phases[0].allowed_tools) == ["execute_python"]


def test_fixed_query_workflow_declaration_idempotent(monkeypatch):
    declaration = {
        "query_monitoring_city": FixedQueryWorkflowToolsDeclaration(tools=["declared_tool_z"])
    }
    mw._apply_declared_fixed_query_workflows(declaration)
    once = mw._QUERY_TOOL_SETS["query_monitoring_city"]
    mw._apply_declared_fixed_query_workflows(declaration)
    assert mw._QUERY_TOOL_SETS["query_monitoring_city"] == once
    assert once.count("declared_tool_z") == 1


def test_target_mode_contracts_merge_field_override_and_new_entry(monkeypatch):
    declared = {
        "test_component_decl": {
            "positioning": "测试组分 Agent", "scope": "取数", "boundary": "不研判",
            "outputs": "file_path", "warning": "口径以工具描述为准",
        },
        "query": {"boundary": "字段级覆盖后的边界"},
    }
    original_query = dict(tmc.TARGET_MODE_CONTRACTS["query"])
    try:
        monkeypatch.setattr(
            "app.project_config.loader.load_project_context",
            lambda pid=None, **kwargs: _manifest_context(
                SimpleNamespace(target_mode_contracts=declared)
            ),
        )
        tmc._apply_declared_target_mode_contracts()

        assert tmc.TARGET_MODE_CONTRACTS["test_component_decl"]["positioning"] == "测试组分 Agent"
        assert tmc.TARGET_MODE_CONTRACTS["query"]["boundary"] == "字段级覆盖后的边界"
        # 字段级合并：未声明字段保留共享默认
        assert tmc.TARGET_MODE_CONTRACTS["query"]["positioning"] == original_query["positioning"]
    finally:
        tmc.TARGET_MODE_CONTRACTS["query"] = original_query
        tmc.TARGET_MODE_CONTRACTS.pop("test_component_decl", None)


def test_prompt_fragment_files_still_fail_fast_for_bad_path():
    """声明了片段文件但路径越界时保持 fail-fast（防吞配置错误）。"""
    from app.agent.prompts.project_prompt import load_project_prompt_fragment

    context = _manifest_context(
        SimpleNamespace(
            prompt_fragment_files={"query_monitoring_city": "/etc/passwd.md"}
        )
    )
    with pytest.raises(ProjectConfigError):
        load_project_prompt_fragment("query_monitoring_city", context)

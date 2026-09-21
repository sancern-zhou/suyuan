"""项目专属工具隔离守卫。

广东省数据源工具（PROJECT_SCOPED_TOOL_NAMES）必须满足：
1. 不出现在任何共享模式白名单中；
2. 工具实例仅对在 manifest 中声明启用的项目注册；
3. 项目通过 backend.agent_mode_extra_tools 按模式追加；
4. 项目 manifest 缺失或损坏时必须显式报错（fail-closed），
   而不是静默回退到完整共享白名单。
"""
import pytest

from app.agent.prompts import tool_registry
from app.agent.prompts.tool_registry import (
    PROJECT_SCOPED_TOOL_NAMES,
    get_tools_by_mode,
)
from app.project_config.loader import ProjectConfigError, load_project_context
from app.tools import create_global_tool_registry
from config.settings import settings


SHARED_MODE_TOOL_NAME_LISTS = [
    tool_registry.ASSISTANT_TOOL_NAMES,
    tool_registry.PPT_TOOL_NAMES,
    tool_registry.EXPERT_TOOL_NAMES,
    tool_registry.QUERY_TOOL_NAMES,
    tool_registry.KNOWLEDGE_TOOL_NAMES,
    tool_registry.REPORT_TOOL_NAMES,
    tool_registry.CHART_TOOL_NAMES,
    tool_registry.BOARD_TOOL_NAMES,
    tool_registry.OPS_TOOL_NAMES,
    tool_registry.GRAPH_TOOL_NAMES,
    tool_registry.SOCIAL_TOOL_NAMES,
    tool_registry.MEMORY_CONSOLIDATOR_TOOL_NAMES,
    tool_registry.ENFORCEMENT_EXAM_TOOL_NAMES,
    tool_registry.DELIBERATION_METEOROLOGY_TOOL_NAMES,
    tool_registry.DELIBERATION_MONITORING_TOOL_NAMES,
    tool_registry.DELIBERATION_CHEMISTRY_TOOL_NAMES,
    tool_registry.DELIBERATION_REVIEWER_TOOL_NAMES,
]

# 与 app/tools/__init__.py 中 is_project_tool_enabled(context, "legacy", ...)
# 的 gate 一一对应（query_gd_suncere 为 query_gd_suncere 工具族的启用开关名）。
REGISTERED_PROJECT_TOOLS = [
    "query_gd_suncere_city_hour",
    "query_gd_suncere_station_hour_new",
    "query_gd_suncere_station_day_new",
    "query_gd_suncere_regional_comparison",
    "query_gd_suncere_city_day",
    "query_gd_suncere_district_day",
    "query_gd_suncere_district_report",
    "query_gd_suncere_report_compare",
    "query_city_standard_report",
    "query_city_standard_yoy_report",
    "query_station_standard_report",
    "query_station_standard_yoy_report",
    "analyze_city_pollutant_rankings",
    "get_5min_data",
]


def test_shared_mode_whitelists_contain_no_project_scoped_tools():
    for mode_tools in SHARED_MODE_TOOL_NAME_LISTS:
        leaked = PROJECT_SCOPED_TOOL_NAMES.intersection(mode_tools)
        assert not leaked, f"project-scoped tools leaked into shared whitelist: {sorted(leaked)}"


def test_default_manifest_enables_all_project_tools():
    manifest = load_project_context("default").manifest

    assert manifest.project == "default"
    assert "legacy" in manifest.modules
    assert set(REGISTERED_PROJECT_TOOLS).issubset(manifest.backend.tools)


def test_default_manifest_appends_project_tools_per_mode():
    extras = load_project_context("default").manifest.backend.agent_mode_extra_tools

    for mode in (
        "expert",
        "query",
        "report",
        "chart",
        "ops",
        "deliberation_meteorology",
        "deliberation_monitoring",
    ):
        declared = set(extras.get(mode, []))
        assert declared, f"mode {mode} must append project tools explicitly"
        assert declared.issubset(PROJECT_SCOPED_TOOL_NAMES)


def test_project_tools_surface_only_for_declaring_project(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "default")
    assert "query_city_standard_report" in get_tools_by_mode("expert")
    assert "get_5min_data" in get_tools_by_mode("query")
    assert "query_gd_suncere_station_day_new" in get_tools_by_mode("ops")

    monkeypatch.setattr(settings, "project_id", "xuchang")
    assert "query_city_standard_report" not in get_tools_by_mode("expert")
    assert "get_5min_data" not in get_tools_by_mode("query")
    assert "query_gd_suncere_station_day_new" not in get_tools_by_mode("ops")


def test_project_tool_instances_register_only_for_declaring_project():
    default_registry = create_global_tool_registry(context=load_project_context("default"))
    xuchang_registry = create_global_tool_registry(context=load_project_context("xuchang"))

    for tool_name in REGISTERED_PROJECT_TOOLS:
        assert tool_name in default_registry.list_tools()
        assert tool_name not in xuchang_registry.list_tools()


def test_missing_project_manifest_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "nonexistent-project")

    with pytest.raises(ProjectConfigError):
        get_tools_by_mode("expert")

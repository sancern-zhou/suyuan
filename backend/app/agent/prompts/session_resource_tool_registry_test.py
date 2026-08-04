import importlib.util
from pathlib import Path

import pytest

from app.agent.prompts import tool_registry
from app.agent.prompts.report_prompt import build_report_prompt


ALL_MODE_LISTS = [
    tool_registry.ASSISTANT_TOOL_NAMES,
    tool_registry.PPT_TOOL_NAMES,
    tool_registry.EXPERT_TOOL_NAMES,
    tool_registry.QUERY_TOOL_NAMES,
    tool_registry.REPORT_TOOL_NAMES,
    tool_registry.CHART_TOOL_NAMES,
    tool_registry.BOARD_TOOL_NAMES,
    tool_registry.OPS_TOOL_NAMES,
    tool_registry.GRAPH_TOOL_NAMES,
    tool_registry.SOCIAL_TOOL_NAMES,
    tool_registry.MEMORY_CONSOLIDATOR_TOOL_NAMES,
    tool_registry.DELIBERATION_METEOROLOGY_TOOL_NAMES,
    tool_registry.DELIBERATION_MONITORING_TOOL_NAMES,
    tool_registry.DELIBERATION_CHEMISTRY_TOOL_NAMES,
    tool_registry.DELIBERATION_REVIEWER_TOOL_NAMES,
]

USER_FACING_MODE_LISTS = [
    tool_names
    for tool_names in ALL_MODE_LISTS
    if tool_names is not tool_registry.MEMORY_CONSOLIDATOR_TOOL_NAMES
]

RETIRED_CHART_TOOL_NAMES = {
    "generate_chart",
    "smart_chart_generator",
    "revise_chart",
}

RETIRED_COMPLEX_QUERY_PLANNER = "complex_query_planner"


@pytest.mark.parametrize("tool_names", ALL_MODE_LISTS)
def test_resource_discovery_is_available_exactly_once_in_every_mode(tool_names):
    assert tool_names.count("list_session_resources") == 1


@pytest.mark.parametrize("tool_names", ALL_MODE_LISTS)
def test_retired_chart_tools_are_not_exposed_by_any_agent_mode(tool_names):
    assert RETIRED_CHART_TOOL_NAMES.isdisjoint(tool_names)


@pytest.mark.parametrize("tool_names", USER_FACING_MODE_LISTS)
def test_existing_files_can_be_published_through_the_resource_catalog(tool_names):
    assert tool_names.count("publish_session_file") == 1


def test_background_memory_consolidation_cannot_publish_user_files():
    assert "publish_session_file" not in tool_registry.MEMORY_CONSOLIDATOR_TOOL_NAMES


def test_retired_chart_modules_and_runtime_references_are_removed():
    assert importlib.util.find_spec("app.tools.visualization.generate_chart") is None
    assert importlib.util.find_spec("app.tools.analysis.smart_chart_generator") is None
    assert importlib.util.find_spec("app.prompts.chart_generation") is None

    current_file = Path(__file__).resolve()
    backend_root = current_file.parents[3]
    retired_paths = (
        backend_root / "app/utils/chart_converters",
        backend_root / "app/utils/chart_data_converter.py",
        backend_root / "app/agent/core/smart_visualization_recommender.py",
    )
    assert all(not path.exists() for path in retired_paths)

    scan_roots = (backend_root / "app", backend_root / "config", backend_root / "schemas")
    source_suffixes = {".py", ".md", ".yaml", ".yml", ".json"}
    stale_references = []
    for root in scan_roots:
        for path in root.rglob("*"):
            if path == current_file or path.suffix not in source_suffixes:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(tool_name in text for tool_name in RETIRED_CHART_TOOL_NAMES):
                stale_references.append(path.relative_to(backend_root).as_posix())

    assert stale_references == []


def test_current_chart_tools_remain_exposed_after_legacy_cleanup():
    assert "execute_echarts_python" in tool_registry.CHART_TOOL_NAMES
    assert "create_report_chart" in tool_registry.CHART_TOOL_NAMES


def test_retired_complex_query_planner_is_fully_removed():
    current_file = Path(__file__).resolve()
    backend_root = current_file.parents[3]

    assert not (backend_root / "app/tools/planning/complex_query_planner").exists()
    assert all(
        RETIRED_COMPLEX_QUERY_PLANNER not in tool_names
        for tool_names in ALL_MODE_LISTS
    )
    assert RETIRED_COMPLEX_QUERY_PLANNER not in build_report_prompt(
        tool_registry.REPORT_TOOL_NAMES
    )

    scan_roots = (backend_root / "app", backend_root / "config", backend_root / "schemas")
    source_suffixes = {".py", ".md", ".yaml", ".yml", ".json"}
    stale_references = []
    for root in scan_roots:
        for path in root.rglob("*"):
            if path == current_file or path.suffix not in source_suffixes:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if RETIRED_COMPLEX_QUERY_PLANNER in text:
                stale_references.append(path.relative_to(backend_root).as_posix())

    assert stale_references == []

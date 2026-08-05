from pathlib import Path

import pytest

import app.tools as tools_module
from app.project_config.loader import ProjectConfigError, load_project_context

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_default_project_loads_legacy_module():
    context = load_project_context("default", repo_root=REPO_ROOT)

    assert context.manifest.project == "default"
    assert context.enabled_modules == frozenset({"core", "legacy"})
    assert context.manifest.frontend.theme == "default"
    assert context.manifest.frontend.brand_name == "风清气智"
    assert context.manifest.frontend.agent_modes == [
        "assistant",
        "ppt",
        "expert",
        "query",
        "report",
        "chart",
        "board",
        "ops",
    ]
    assert context.manifest.frontend.agent_platform_layout == "scenes"
    assert context.manifest.backend.tools == []
    assert context.manifest.backend.fetchers_enabled is True
    assert context.manifest.knowledge.collections == []


def test_jiangxi_project_disables_data_fetchers():
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    assert context.manifest.frontend.brand_name == "江西省噪声智能分析平台"
    assert context.manifest.frontend.agent_modes == [
        "query",
        "expert",
        "report",
    ]
    assert context.manifest.frontend.default_agent_mode == "query"
    assert (
        context.manifest.frontend.agent_mode_overrides["query"]["name"]
        == "智能问数生图智能体"
    )
    assert context.manifest.frontend.agent_platform_layout == "environment-grid"
    assert context.manifest.backend.fetchers_enabled is False
    assert context.manifest.backend.tools == [
        "query_jiangxi_noise_city_hour",
        "query_jiangxi_noise_station_minute",
        "query_jiangxi_noise_station_hour",
        "query_jiangxi_noise_station_day",
        "query_jiangxi_noise_station_statistics",
    ]
    query_tools = context.manifest.backend.agent_mode_tools["query"]
    assert "create_report_chart" in query_tools
    assert "execute_echarts_python" in query_tools
    assert "get_jiangxi_noise_data" not in query_tools


def test_xuchang_project_composes_shared_and_customer_modules():
    context = load_project_context("xuchang", repo_root=REPO_ROOT)

    assert context.enabled_modules == frozenset(
        {
            "core",
            "legacy",
            "satellite",
            "xuchang-air-quality",
            "xuchang-satellite",
        }
    )
    assert context.manifest.frontend.brand_name == "许昌市AI应用智能体"
    assert context.manifest.frontend.agent_modes == [
        "query",
        "expert",
        "report",
        "chart",
    ]
    assert context.manifest.frontend.agent_platform_layout == "environment-grid"
    assert context.manifest.backend.tools == [
        "get_gems_image",
        "get_sentinel5p_image",
    ]
    assert context.manifest.knowledge.collections == ["xuchang"]


def test_default_project_does_not_enable_satellite_project_tools():
    context = load_project_context("default", repo_root=REPO_ROOT)

    assert not tools_module.is_project_tool_enabled(
        context, "satellite", "get_gems_image"
    )
    assert not tools_module.is_project_tool_enabled(
        context, "satellite", "get_sentinel5p_image"
    )


def test_xuchang_project_enables_only_declared_satellite_tools():
    context = load_project_context("xuchang", repo_root=REPO_ROOT)

    assert tools_module.is_project_tool_enabled(
        context, "satellite", "get_gems_image"
    )
    assert tools_module.is_project_tool_enabled(
        context, "satellite", "get_sentinel5p_image"
    )
    assert not tools_module.is_project_tool_enabled(
        context, "satellite", "undeclared_satellite_tool"
    )


def test_unknown_module_fails_closed(tmp_path: Path):
    (tmp_path / "projects" / "broken").mkdir(parents=True)
    (tmp_path / "modules").mkdir()
    (tmp_path / "projects" / "broken" / "project.yaml").write_text(
        "schema_version: 1\nproject: broken\nmodules: [missing]\n",
        encoding="utf-8",
    )

    with pytest.raises(ProjectConfigError, match="unknown module: missing"):
        load_project_context("broken", repo_root=tmp_path)


def test_missing_dependency_fails_closed(tmp_path: Path):
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    (tmp_path / "modules" / "noise").mkdir(parents=True)
    (tmp_path / "projects" / "demo" / "project.yaml").write_text(
        "schema_version: 1\nproject: demo\nmodules: [noise]\n",
        encoding="utf-8",
    )
    (tmp_path / "modules" / "noise" / "module.yaml").write_text(
        "schema_version: 1\nmodule: noise\ndependencies: [atmosphere]\n",
        encoding="utf-8",
    )

    with pytest.raises(ProjectConfigError, match="noise requires atmosphere"):
        load_project_context("demo", repo_root=tmp_path)


@pytest.mark.parametrize("project_id", ["../secret", "a/b", "", "UPPER CASE"])
def test_unsafe_project_identifier_is_rejected(project_id: str, tmp_path: Path):
    with pytest.raises(ProjectConfigError, match="invalid project identifier"):
        load_project_context(project_id, repo_root=tmp_path)

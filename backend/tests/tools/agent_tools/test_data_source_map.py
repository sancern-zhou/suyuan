"""数据源地图守卫：目录引用真实性与提示词注入。"""

from pathlib import Path

import pytest

from app.agent.prompts import data_source_map
from app.agent.prompts.data_source_map import (
    load_data_source_catalog,
    render_data_source_map,
)


@pytest.fixture(autouse=True)
def _reset_catalog_cache():
    data_source_map.reset_cache()
    yield
    data_source_map.reset_cache()


def _write_catalog(tmp_path: Path, content: str) -> None:
    path = tmp_path / data_source_map.CATALOG_FILENAME
    path.write_text(content, encoding="utf-8")


def test_render_map_formats_entries(tmp_path, monkeypatch):
    _write_catalog(
        tmp_path,
        """
sources:
  - domain: 气象（历史实况/再分析）
    route: tool
    locator: get_weather_data
    usage: "lat/lon + past_days 取历史"
    caveats: "平台 SQL 库无气象实况表"
  - domain: 空气质量（国控站点历史数据）
    route: sql
    locator: city_aqi_publish_history
""",
    )
    monkeypatch.setattr(data_source_map, "_catalog_path", lambda: tmp_path / data_source_map.CATALOG_FILENAME)

    rendered = render_data_source_map()
    assert "## 数据源地图" in rendered
    assert "**气象（历史实况/再分析）** → `get_weather_data`" in rendered
    assert "lat/lon + past_days 取历史" in rendered
    assert "注意：平台 SQL 库无气象实况表" in rendered
    assert "**空气质量（国控站点历史数据）** → `city_aqi_publish_history`" in rendered


def test_render_map_empty_when_catalog_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        data_source_map,
        "_candidate_paths",
        lambda: [tmp_path / "absent.yaml"],
    )
    assert render_data_source_map() == ""


def test_invalid_entries_are_skipped(tmp_path, monkeypatch):
    _write_catalog(
        tmp_path,
        """
sources:
  - domain: 缺少locator
  - locator: 缺少domain
  - "不是字典"
  - domain: 有效条目
    route: tool
    locator: get_weather_data
""",
    )
    monkeypatch.setattr(data_source_map, "_catalog_path", lambda: tmp_path / data_source_map.CATALOG_FILENAME)

    entries = load_data_source_catalog()
    assert [item["domain"] for item in entries] == ["有效条目"]
    assert "get_weather_data" in render_data_source_map()


def test_deployment_catalog_references_registered_tools():
    """部署 registry 里若配置了地图，route=tool 的 locator 必须是真实工具名。"""
    path = data_source_map._catalog_path()
    if not path.exists():
        pytest.skip("部署 registry 未配置 data_source_catalog.yaml")
    entries = load_data_source_catalog(refresh=True)
    assert entries, "目录文件存在但未解析出有效条目"

    from app.tools import global_tool_registry

    for item in entries:
        locator = str(item.get("locator") or "")
        if item.get("route") != "tool":
            continue
        # locator 允许"主工具"单值；主工具名必须已注册
        primary = locator.split("/")[0].strip()
        assert global_tool_registry.get_tool(primary) is not None, (
            f"数据源地图引用了未注册工具: {primary}（条目: {item.get('domain')}）"
        )


def test_config_fallback_loads_when_registry_absent(tmp_path, monkeypatch):
    """registry 覆盖缺失时回落到随代码入库的 config 基准目录。"""
    config_path = data_source_map._config_catalog_path()
    if not config_path.exists():
        pytest.skip("config 基准目录未入库")
    monkeypatch.setattr(
        data_source_map,
        "_candidate_paths",
        lambda: [tmp_path / "absent.yaml", config_path],
    )
    entries = load_data_source_catalog(refresh=True)
    assert entries, "config 基准目录存在但未解析出有效条目"


def test_config_baseline_covers_key_routing_domains():
    """入库基准必须包含踩坑迭代出的关键路由域（防回退）。"""
    config_path = data_source_map._config_catalog_path()
    assert config_path.exists(), "data_source_catalog.yaml 必须随代码入库"
    domains = {
        str(item.get("domain") or "")
        for item in load_data_source_catalog(refresh=True)
    }
    assert any("国控" in d for d in domains)
    assert any("预报" in d for d in domains)
    assert any("气象" in d for d in domains)

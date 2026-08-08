from unittest.mock import Mock

import pytest

from app.agent.context.context_builder import SimplifiedContextBuilder
from app.agent.prompts.project_prompt import load_project_mode_prompt
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.query_prompt import build_query_prompt
from app.project_config import ProjectConfigError, load_project_context
from config.settings import settings


def test_jiangxi_query_prompt_is_project_owned_role_policy():
    context = load_project_context("jiangxi")
    prompt = load_project_mode_prompt("query", context)

    assert prompt is not None
    assert "数据查询与分析智能体" in prompt
    assert "数据真实性原则" in prompt
    for prohibited in (
        "Agentic GIS",
        "地图视觉",
        "map_context",
        "visual_interaction",
        "工具",
        "schema",
        "file_path",
        "记忆文件路径",
    ):
        assert prohibited not in prompt


def test_default_project_keeps_shared_query_prompt():
    context = load_project_context("default")

    assert load_project_mode_prompt("query", context) is None
    assert "Agentic GIS 视觉交互" in build_query_prompt([])


def test_jiangxi_query_system_prompt_uses_exact_project_override(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangxi")

    prompt = build_react_system_prompt("query")

    assert prompt == load_project_mode_prompt("query")
    assert "文件系统路径约定" not in prompt
    assert "publish_session_file" not in prompt


def test_jiangxi_query_map_context_does_not_add_gis_instructions(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangxi")
    builder = SimplifiedContextBuilder(Mock(), Mock(), {})
    builder.current_mode = "query"
    builder.map_context = {"session_id": "session-1", "events": []}

    mode_policy = builder._build_system_context_layers()["mode_policy"]

    assert "Agentic GIS" not in mode_policy
    assert "visual_interaction" not in mode_policy
    assert "map_program" not in mode_policy


def test_project_prompt_cannot_escape_its_project_directory():
    context = load_project_context("jiangxi")
    context.manifest.backend.mode_prompt_files["query"] = "backend/.env"

    with pytest.raises(ProjectConfigError, match="must be inside projects/jiangxi"):
        load_project_mode_prompt("query", context)

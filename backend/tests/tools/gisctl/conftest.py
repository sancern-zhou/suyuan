import pytest


@pytest.fixture
def gis_enabled_project(monkeypatch):
    """Pin a test to a deployment project that keeps Agentic GIS enabled.

    Projects are free to turn Agentic GIS off (``backend.gis_tools_enabled:
    false``; xuchang and jiangxi both do). Tests that exercise the shared
    Agentic GIS implementation must therefore pin the project context
    explicitly instead of inheriting whichever project the local deployment
    selects via ``.env``.
    """
    from config.settings import settings

    monkeypatch.setattr(settings, "project_id", "default")

    from app.tools import create_global_tool_registry

    registry = create_global_tool_registry()
    monkeypatch.setattr("app.agent.tool_adapter.global_tool_registry", registry)

    from app.project_config.loader import load_project_context

    return load_project_context("default")

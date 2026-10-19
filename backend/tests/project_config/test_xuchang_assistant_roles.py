from pathlib import Path

import yaml

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.utils.path_config import PROJECT_ROOT
from config.settings import settings


def test_xuchang_manifest_separates_coordinator_and_office():
    manifest = yaml.safe_load(
        (Path(PROJECT_ROOT) / "projects/xuchang/project.yaml").read_text(encoding="utf-8")
    )["backend"]
    prompts = manifest["mode_prompt_files"]
    assert "assistant" not in prompts
    assert prompts["office"] == "projects/xuchang/prompts/office.md"
    assert (Path(PROJECT_ROOT) / prompts["office"]).is_file()
    tools = manifest["agent_mode_tools"]["social"]
    assert {"call_sub_agent", "run_agent_workflow"}.issubset(tools)
    assert "manage_assistant_schedule" in tools
    assert {"manage_assistant_memory", "manage_assistant_runs"}.issubset(tools)
    assert {"read_file", "edit_file"}.issubset(tools)
    assert {"wait_task", "bash"}.isdisjoint(tools)
    assert {"schedule_task", "create_scheduled_task", "manage_scheduled_tasks"}.isdisjoint(tools)
    assert {
        "execute_sql_query",
        "get_weather_data",
        "get_weather_forecast",
        "execute_python",
        "create_business_chart",
        "create_report_package",
        "knowledge_qa_workflow",
        "knowledge_document_reader",
    }.isdisjoint(tools)


def test_xuchang_prompts_route_office_and_keep_professional_boundaries(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")
    social = build_react_system_prompt("social")
    office = build_react_system_prompt("office")
    assert "问数分析助理" not in social
    assert 'target_mode="office"' in social
    assert "不直接查询业务或气象数据" in social
    assert "办公模式（office）" in office
    assert "不再次委派" in office
    assert build_react_system_prompt("assistant") == office

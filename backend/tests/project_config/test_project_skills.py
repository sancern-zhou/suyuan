from pathlib import Path

from app.agent.selection_context import active_skills_dir, load_skill_selection
from app.project_config.loader import load_project_context
from app.project_config.paths import project_skills_dir
from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool
from config.settings import settings


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_jiangsu_skill_directory_contains_only_project_skill():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)
    skills_dir = project_skills_dir(context)

    selection = load_skill_selection("station-alarm-diagnosis", skills_dir=skills_dir)
    assert selection.skill_id == "station-alarm-diagnosis"
    assert "江苏站点告警诊断" in selection.content
    try:
        load_skill_selection("ops_work_order_audit", skills_dir=skills_dir)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("shared skills must not be visible to Jiangsu")


def test_runtime_skill_resolution_uses_the_jiangsu_directory(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangsu-ops")

    tool = ListSkillsTool()
    assert tool.skills_dir == active_skills_dir()

    result = __import__("asyncio").run(tool.execute())

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["skills"][0]["file"].endswith(
        "station-alarm-diagnosis/SKILL.md"
    )

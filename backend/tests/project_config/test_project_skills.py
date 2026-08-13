from pathlib import Path

from app.agent.selection_context import active_skills_dir, load_skill_selection
from app.project_config.loader import load_project_context
from app.project_config.paths import project_skills_dir
from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool
from config.settings import settings


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_jiangsu_skill_directory_is_empty_and_does_not_fall_back_to_shared_skills():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)
    skills_dir = project_skills_dir(context)

    assert list(skills_dir.glob("*.md")) == []
    assert list(skills_dir.glob("SKILLS_INDEX.md")) == []
    try:
        load_skill_selection("ops_work_order_audit", skills_dir=skills_dir)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("shared skills must not be visible to Jiangsu")


def test_runtime_skill_resolution_uses_the_empty_jiangsu_directory(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangsu-ops")

    tool = ListSkillsTool()
    assert tool.skills_dir == active_skills_dir()

    result = __import__("asyncio").run(tool.execute())

    assert result["success"] is True
    assert result["data"]["count"] == 0

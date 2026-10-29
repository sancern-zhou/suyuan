import pytest

from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool
from app.tools.utility.skill_management.view_skill_tool import ViewSkillTool


@pytest.mark.asyncio
async def test_shared_guides_are_published_official_skills():
    listed = await ListSkillsTool().execute()

    assert listed["success"] is True
    skill_files = {skill["file"] for skill in listed["data"]["skills"]}
    assert any(file.endswith("analysis_report_workflow.md") for file in skill_files)
    assert any(file.endswith("archify.md") for file in skill_files)

    analysis = await ViewSkillTool().execute(name="analysis_report_workflow")
    archify = await ViewSkillTool().execute(name="archify")

    assert analysis["success"] is True
    assert archify["success"] is True
    assert analysis["data"]["is_draft"] is False
    assert archify["data"]["is_draft"] is False

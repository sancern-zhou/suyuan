import pytest

from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool
from app.tools.utility.skill_management.view_skill_tool import ViewSkillTool


@pytest.mark.asyncio
async def test_expert_guides_are_published_official_skills():
    listed = await ListSkillsTool().execute(keyword="expert")

    assert listed["success"] is True
    skill_files = {skill["file"] for skill in listed["data"]["skills"]}
    assert any(file.endswith("weather_analysis_expert.md") for file in skill_files)
    assert any(file.endswith("routine_monitoring_analysis_expert.md") for file in skill_files)

    weather = await ViewSkillTool().execute(name="weather_analysis_expert")
    routine = await ViewSkillTool().execute(name="routine_monitoring_analysis_expert")

    assert weather["success"] is True
    assert routine["success"] is True
    assert weather["data"]["is_draft"] is False
    assert routine["data"]["is_draft"] is False

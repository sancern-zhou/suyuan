from pathlib import Path

import pytest

from app.agent.prompts.tool_registry import ASSISTANT_TOOL_NAMES
from app.agent.selection_context import load_skill_selection
from app.agent.skill_metadata import SKILL_METADATA
from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "backend/docs/skills/archify.md"


@pytest.mark.asyncio
async def test_shared_archify_skill_is_published_for_assistant_mode():
    content = SKILL_PATH.read_text(encoding="utf-8")

    assert "$CODEX_HOME/skills/archify/bin/archify.mjs" in content
    assert "validate <type> <candidate.json>" in content
    assert "deliver <type> <candidate.json> <output.html>" in content
    assert "visual-check <output.html>" in content

    name, description = ListSkillsTool()._parse_skill_file(SKILL_PATH)
    listing = await ListSkillsTool().execute(keyword="archify")
    selection = load_skill_selection(
        "archify",
        skills_dir=SKILL_PATH.parent,
        available_tools=set(ASSISTANT_TOOL_NAMES),
    )

    assert name == "Archify 图技能"
    assert "standalone HTML 图" in description
    assert "候选 JSON" in description
    assert any(
        skill["name"] == "Archify 图技能" and Path(skill["file"]).name == "archify.md"
        for skill in listing["data"]["skills"]
    )
    assert selection.skill_id == "archify"
    assert selection.required_tools == SKILL_METADATA["archify"]["required_tools"]
    assert set(selection.required_tools) <= set(ASSISTANT_TOOL_NAMES)

from pathlib import Path

from app.agent.prompts.tool_registry import OFFICE_TOOL_NAMES
from app.agent.selection_context import load_skill_selection
from app.agent.skill_metadata import SKILL_METADATA
from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_SKILLS = REPO_ROOT / "backend/docs/skills"

SKILLS = {
    "docx_authoring": {
        "name": "Word 文档创作技能",
        "required_tools": ["read_file", "execute_python", "validate_office"],
        "entry_tokens": ("python-docx", "validate_office", "artifact_path"),
        "design_tokens": ("Noto Sans CJK SC", "5.8"),
        "recipe_tokens": ("eastAsia", "artifact_path("),
        "contract_tokens": ("artifact_path(", "create_business_chart"),
    },
    "xlsx_authoring": {
        "name": "Excel 表格设计技能",
        "required_tools": ["read_file", "execute_python", "validate_office"],
        "entry_tokens": ("openpyxl", "validate_office", "artifact_path"),
        "design_tokens": ("31", "freeze_panes"),
        "recipe_tokens": ('freeze_panes = "A2"', "artifact_path("),
        "contract_tokens": ("EXCEL_SAVED", "save_data"),
    },
}


def test_entries_are_concise_and_reference_progressive_docs():
    for skill_id, spec in SKILLS.items():
        entry = SHARED_SKILLS / f"{skill_id}.md"
        content = entry.read_text(encoding="utf-8")

        assert len(content.splitlines()) < 100, skill_id
        for token in spec["entry_tokens"]:
            assert token in content, (skill_id, token)
        for doc in ("design-rules", "code-recipes", "qa-loop", "output-contract"):
            assert f"backend/docs/skills/{skill_id}/references/{doc}.md" in content, (skill_id, doc)
            assert (SHARED_SKILLS / skill_id / "references" / f"{doc}.md").is_file(), (skill_id, doc)


def test_frontmatter_visible_to_skill_listing_and_office_mode_compatible():
    for skill_id, spec in SKILLS.items():
        skill_path = SHARED_SKILLS / f"{skill_id}.md"
        name, description = ListSkillsTool()._parse_skill_file(skill_path)
        selection = load_skill_selection(
            skill_id, skills_dir=skill_path.parent, available_tools=set(OFFICE_TOOL_NAMES)
        )

        assert name == spec["name"]
        assert description and description != "暂无描述"
        assert selection.skill_id == skill_id
        assert selection.required_tools == spec["required_tools"]
        # 办公子代理（OFFICE_TOOL_NAMES）必须齐备技能声明的工具
        assert set(selection.required_tools) <= set(OFFICE_TOOL_NAMES), skill_id


def test_metadata_registry_entries_match_frontmatter():
    for skill_id, spec in SKILLS.items():
        metadata = SKILL_METADATA[skill_id]

        assert metadata["enabled"] is True
        assert metadata["required_tools"] == spec["required_tools"]
        assert metadata["aliases"]


def test_reference_contracts_are_preserved():
    for skill_id, spec in SKILLS.items():
        refs = SHARED_SKILLS / skill_id / "references"
        design = (refs / "design-rules.md").read_text(encoding="utf-8")
        recipes = (refs / "code-recipes.md").read_text(encoding="utf-8")
        qa_loop = (refs / "qa-loop.md").read_text(encoding="utf-8")
        contract = (refs / "output-contract.md").read_text(encoding="utf-8")

        for token in spec["design_tokens"]:
            assert token in design, (skill_id, token)
        for token in spec["recipe_tokens"]:
            assert token in recipes, (skill_id, token)
        for token in ("passed", "needs_revision", "qa_failed", "structured_issues"):
            assert token in qa_loop, (skill_id, token)
        if skill_id == "docx_authoring":
            # docx 有渲染产物：视觉自评协议（挂载通道）必须存在
            for token in ("视觉自评", "as_multimodal_attachment", "montage_path"):
                assert token in qa_loop, (skill_id, token)
        for token in spec["contract_tokens"]:
            assert token in contract, (skill_id, token)

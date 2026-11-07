from pathlib import Path

from app.agent.prompts.tool_registry import OFFICE_TOOL_NAMES
from app.agent.selection_context import load_skill_selection
from app.agent.skill_metadata import SKILL_METADATA
from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "backend/docs/skills/pptx_authoring.md"
REFERENCES_DIR = REPO_ROOT / "backend/docs/skills/pptx_authoring/references"


def test_shared_pptx_authoring_skill_is_concise_and_uses_progressive_references():
    content = SKILL_PATH.read_text(encoding="utf-8")

    assert len(content.splitlines()) < 100
    for token in ("execute_python", "validate_pptx", "artifact_path", "python-pptx"):
        assert token in content
    # 密度红线随技能声明，与 validate_pptx 检查阈值联动
    assert "620" in content and "24pt" in content
    # 渐进式参考文档路由（正文不内联长文档）
    for doc in ("design-rules.md", "code-recipes.md", "qa-loop.md", "output-contract.md"):
        assert f"backend/docs/skills/pptx_authoring/references/{doc}" in content
        assert (REFERENCES_DIR / doc).is_file()


def test_shared_pptx_authoring_frontmatter_is_visible_to_skill_listing():
    name, description = ListSkillsTool()._parse_skill_file(SKILL_PATH)
    selection = load_skill_selection(
        "pptx_authoring",
        skills_dir=SKILL_PATH.parent,
        available_tools=set(OFFICE_TOOL_NAMES),
    )

    assert name == "PPT 设计与生成技能"
    assert "渲染验收" in description or "验收闭环" in description
    assert selection.skill_id == "pptx_authoring"
    assert selection.required_tools == ["read_file", "execute_python", "validate_pptx"]
    # 办公子代理（OFFICE_TOOL_NAMES）必须齐备技能声明的工具
    assert set(selection.required_tools) <= set(OFFICE_TOOL_NAMES)


def test_shared_pptx_authoring_metadata_registry_entry_matches_frontmatter():
    metadata = SKILL_METADATA["pptx_authoring"]

    assert metadata["enabled"] is True
    assert metadata["required_tools"] == ["read_file", "execute_python", "validate_pptx"]
    assert metadata["aliases"]


def test_shared_pptx_authoring_reference_contracts_are_preserved():
    design = (REFERENCES_DIR / "design-rules.md").read_text(encoding="utf-8")
    recipes = (REFERENCES_DIR / "code-recipes.md").read_text(encoding="utf-8")
    qa_loop = (REFERENCES_DIR / "qa-loop.md").read_text(encoding="utf-8")
    contract = (REFERENCES_DIR / "output-contract.md").read_text(encoding="utf-8")

    # 设计阈值与 validate_pptx 检查逻辑对齐（改任一侧必须同步）
    for token in ("620", "24pt", "8pt", "Noto Sans CJK SC", "repeated_layout_pattern"):
        assert token in design
    # 中文字体必须写 eastasia 节点，否则服务器渲染漂移
    assert 'qn("a:ea")' in recipes
    assert "artifact_path(" in recipes
    # QA 协议覆盖 gate 三态与修复对照
    for token in ("passed", "needs_revision", "qa_failed", "structured_issues"):
        assert token in qa_loop
    # 视觉自评协议：挂载通道与最差页定位（多模态看图，非可选）
    for token in ("视觉自评", "as_multimodal_attachment", "worst_pages", "montage"):
        assert token in qa_loop
    # 交付契约：归档路径与业务图嵌入约定
    assert "artifact_path(" in contract
    assert "create_business_chart" in contract

from pathlib import Path

import pytest

from app.tools.utility.skill_management.skill_paths import (
    DRAFTS_DIR,
    SKILLS_DIR,
    render_skill_draft_markdown,
    resolve_skill_file,
    sanitize_skill_filename,
)


def test_default_skill_paths_are_under_backend_directory():
    backend_dir = Path(__file__).resolve().parents[2]

    assert SKILLS_DIR == backend_dir / "docs" / "skills"
    assert DRAFTS_DIR == backend_dir / "docs" / "skills" / ".drafts"


def test_sanitize_skill_filename_blocks_path_traversal():
    assert sanitize_skill_filename("../bad") == "bad.md"
    assert sanitize_skill_filename("..\\bad") == "bad.md"
    assert sanitize_skill_filename("/tmp/bad.md") == "bad.md"


def test_sanitize_skill_filename_keeps_chinese_and_adds_md():
    assert sanitize_skill_filename("污染过程复盘") == "污染过程复盘.md"


def test_render_skill_draft_markdown_contains_required_sections():
    content = render_skill_draft_markdown(
        title="污染过程复盘",
        description="复用污染过程分析步骤。",
        applicable_scenarios=["城市出现连续污染过程"],
        required_tools=[{"name": "query_city_standard_report", "purpose": "查询城市报表"}],
        workflow_steps=[{"title": "查询数据", "purpose": "获取基础数据", "operation": "按城市和日期查询"}],
        notes=["核对时间范围"],
        source_summary="用户完成了一次污染过程复盘。",
        source_session_id="session-a",
    )

    assert content.startswith("# 污染过程复盘")
    assert "status: draft" in content
    assert "source_mode: assistant" in content
    assert "source_session_id: session-a" in content
    assert "## 概述" in content
    assert "## 适用场景" in content
    assert "## 所需工具" in content
    assert "## 详细流程" in content
    assert "## 验证方式" in content


def test_resolve_skill_file_rejects_unsafe_name(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    drafts_dir = skills_dir / ".drafts"
    skills_dir.mkdir()
    drafts_dir.mkdir()

    with pytest.raises(ValueError):
        resolve_skill_file("../secret", include_drafts=True, skills_dir=skills_dir, drafts_dir=drafts_dir)


from app.tools.utility.skill_management.view_skill_tool import ViewSkillTool


@pytest.mark.asyncio
async def test_view_skill_reads_official_skill(monkeypatch, tmp_path: Path):
    skills_dir = tmp_path / "skills"
    drafts_dir = skills_dir / ".drafts"
    skills_dir.mkdir()
    drafts_dir.mkdir()
    (skills_dir / "excel.md").write_text("# Excel 技能\n\n## 概述\n处理 Excel。", encoding="utf-8")

    import app.tools.utility.skill_management.view_skill_tool as module

    monkeypatch.setattr(module, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "DRAFTS_DIR", drafts_dir)

    result = await ViewSkillTool().execute(name="excel")

    assert result["success"] is True
    assert result["data"]["name"] == "Excel 技能"
    assert result["data"]["is_draft"] is False
    assert "处理 Excel" in result["data"]["content"]


@pytest.mark.asyncio
async def test_view_skill_reads_draft_when_requested(monkeypatch, tmp_path: Path):
    skills_dir = tmp_path / "skills"
    drafts_dir = skills_dir / ".drafts"
    skills_dir.mkdir()
    drafts_dir.mkdir()
    (drafts_dir / "draft.md").write_text("# 草稿技能\n\n## 概述\n草稿内容。", encoding="utf-8")

    import app.tools.utility.skill_management.view_skill_tool as module

    monkeypatch.setattr(module, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(module, "DRAFTS_DIR", drafts_dir)

    result = await ViewSkillTool().execute(name="draft", include_drafts=True)

    assert result["success"] is True
    assert result["data"]["is_draft"] is True
    assert result["data"]["name"] == "草稿技能"


@pytest.mark.asyncio
async def test_view_skill_rejects_path_traversal():
    result = await ViewSkillTool().execute(name="../secret", include_drafts=True)

    assert result["success"] is False
    assert "路径" in result["summary"] or "名称" in result["summary"]


from app.tools.utility.skill_management.create_skill_draft_tool import CreateSkillDraftTool


def _draft_payload():
    return {
        "title": "污染过程复盘",
        "description": "复用污染过程分析步骤。",
        "applicable_scenarios": ["城市出现连续污染过程"],
        "required_tools": [{"name": "query_city_standard_report", "purpose": "查询城市报表"}],
        "workflow_steps": [{"title": "查询数据", "purpose": "获取基础数据", "operation": "按城市和日期查询"}],
        "notes": ["核对时间范围"],
        "source_summary": "用户完成了一次污染过程复盘。",
        "source_session_id": "session-a",
    }


@pytest.mark.asyncio
async def test_create_skill_draft_writes_to_drafts(monkeypatch, tmp_path: Path):
    skills_dir = tmp_path / "skills"
    drafts_dir = skills_dir / ".drafts"
    skills_dir.mkdir()

    import app.tools.utility.skill_management.create_skill_draft_tool as module

    monkeypatch.setattr(module, "DRAFTS_DIR", drafts_dir)

    result = await CreateSkillDraftTool().execute(**_draft_payload())

    assert result["success"] is True
    created = Path(result["data"]["file"])
    assert created.parent == drafts_dir
    assert created.exists()
    assert "污染过程复盘" in created.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_create_skill_draft_rejects_duplicate_without_overwrite(monkeypatch, tmp_path: Path):
    drafts_dir = tmp_path / "skills" / ".drafts"
    drafts_dir.mkdir(parents=True)
    (drafts_dir / "污染过程复盘.md").write_text("# old", encoding="utf-8")

    import app.tools.utility.skill_management.create_skill_draft_tool as module

    monkeypatch.setattr(module, "DRAFTS_DIR", drafts_dir)

    result = await CreateSkillDraftTool().execute(**_draft_payload())

    assert result["success"] is False
    assert "已存在" in result["summary"]


@pytest.mark.asyncio
async def test_create_skill_draft_requires_workflow_steps(monkeypatch, tmp_path: Path):
    drafts_dir = tmp_path / "skills" / ".drafts"

    import app.tools.utility.skill_management.create_skill_draft_tool as module

    monkeypatch.setattr(module, "DRAFTS_DIR", drafts_dir)
    payload = _draft_payload()
    payload["workflow_steps"] = []

    result = await CreateSkillDraftTool().execute(**payload)

    assert result["success"] is False
    assert "workflow_steps" in result["error"]

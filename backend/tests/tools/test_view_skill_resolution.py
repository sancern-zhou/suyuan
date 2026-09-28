from pathlib import Path

import pytest

from app.tools.utility.skill_management.skill_paths import (
    find_skill_by_title,
    list_skill_titles,
    resolve_skill_file,
)
from app.tools.utility.skill_management.view_skill_tool import ViewSkillTool


def _seed_skills(tmp_path: Path) -> tuple[Path, Path]:
    skills_dir = tmp_path / "skills"
    drafts_dir = skills_dir / ".drafts"
    skills_dir.mkdir(parents=True)
    drafts_dir.mkdir(parents=True)
    (skills_dir / "analysis_report_workflow.md").write_text(
        "# 分析报告通用工作流\n\n## 概述\n通用分析报告流程。",
        encoding="utf-8",
    )
    (skills_dir / "SKILLS_INDEX.md").write_text("# 技能索引\n", encoding="utf-8")
    return skills_dir, drafts_dir


def test_resolve_skill_file_by_title(tmp_path: Path):
    skills_dir, drafts_dir = _seed_skills(tmp_path)

    path = resolve_skill_file("分析报告通用工作流", skills_dir=skills_dir, drafts_dir=drafts_dir)

    assert path.name == "analysis_report_workflow.md"


def test_resolve_skill_file_by_title_with_brackets_and_spaces(tmp_path: Path):
    skills_dir, drafts_dir = _seed_skills(tmp_path)

    path = resolve_skill_file(
        "「 分析报告 通用工作流 」", skills_dir=skills_dir, drafts_dir=drafts_dir
    )

    assert path.name == "analysis_report_workflow.md"


def test_resolve_skill_file_keeps_filename_lookup(tmp_path: Path):
    skills_dir, drafts_dir = _seed_skills(tmp_path)

    by_stem = resolve_skill_file(
        "analysis_report_workflow", skills_dir=skills_dir, drafts_dir=drafts_dir
    )
    by_file = resolve_skill_file(
        "analysis_report_workflow.md", skills_dir=skills_dir, drafts_dir=drafts_dir
    )

    assert by_stem == by_file == skills_dir / "analysis_report_workflow.md"


def test_resolve_skill_file_unknown_name_raises(tmp_path: Path):
    skills_dir, drafts_dir = _seed_skills(tmp_path)

    with pytest.raises(FileNotFoundError):
        resolve_skill_file("不存在的技能", skills_dir=skills_dir, drafts_dir=drafts_dir)


def test_title_lookup_respects_draft_flag(tmp_path: Path):
    skills_dir, drafts_dir = _seed_skills(tmp_path)
    (drafts_dir / "draft.md").write_text("# 草稿标题\n", encoding="utf-8")

    assert find_skill_by_title("草稿标题", skills_dir=skills_dir, drafts_dir=drafts_dir) is None
    assert (
        find_skill_by_title(
            "草稿标题", skills_dir=skills_dir, drafts_dir=drafts_dir, include_drafts=True
        )
        == drafts_dir / "draft.md"
    )


def test_title_lookup_ignores_skill_index(tmp_path: Path):
    skills_dir, drafts_dir = _seed_skills(tmp_path)

    assert find_skill_by_title("技能索引", skills_dir=skills_dir, drafts_dir=drafts_dir) is None


def test_list_skill_titles_reports_available_skills(tmp_path: Path):
    skills_dir, drafts_dir = _seed_skills(tmp_path)

    assert list_skill_titles(skills_dir=skills_dir, drafts_dir=drafts_dir) == ["分析报告通用工作流"]


@pytest.mark.asyncio
async def test_view_skill_reads_by_title(monkeypatch, tmp_path: Path):
    skills_dir, drafts_dir = _seed_skills(tmp_path)
    import app.tools.utility.skill_management.view_skill_tool as module

    monkeypatch.setattr(module, "active_skill_paths", lambda: (skills_dir, drafts_dir))

    result = await ViewSkillTool().execute(name="分析报告通用工作流")

    assert result["success"] is True
    assert result["data"]["name"] == "分析报告通用工作流"
    assert "通用分析报告流程" in result["data"]["content"]


@pytest.mark.asyncio
async def test_view_skill_not_found_lists_available_titles(monkeypatch, tmp_path: Path):
    skills_dir, drafts_dir = _seed_skills(tmp_path)
    import app.tools.utility.skill_management.view_skill_tool as module

    monkeypatch.setattr(module, "active_skill_paths", lambda: (skills_dir, drafts_dir))

    result = await ViewSkillTool().execute(name="不存在的技能")

    assert result["success"] is False
    assert "未找到技能文档" in result["summary"]
    assert "分析报告通用工作流" in result["summary"]

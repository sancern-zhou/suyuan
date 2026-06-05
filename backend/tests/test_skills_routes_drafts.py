from pathlib import Path

import pytest

from app.api import skills_routes


@pytest.mark.asyncio
async def test_list_skill_drafts(monkeypatch, tmp_path: Path):
    drafts_dir = tmp_path / "skills" / ".drafts"
    drafts_dir.mkdir(parents=True)
    (drafts_dir / "draft.md").write_text("# 草稿技能\n\n## 概述\n草稿内容。", encoding="utf-8")

    monkeypatch.setattr(skills_routes, "DRAFTS_DIR", drafts_dir)

    result = await skills_routes.list_skill_drafts()

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["drafts"][0]["name"] == "草稿技能"


@pytest.mark.asyncio
async def test_get_skill_draft_detail(monkeypatch, tmp_path: Path):
    drafts_dir = tmp_path / "skills" / ".drafts"
    drafts_dir.mkdir(parents=True)
    (drafts_dir / "draft.md").write_text("# 草稿技能\n\n## 概述\n草稿内容。", encoding="utf-8")

    monkeypatch.setattr(skills_routes, "DRAFTS_DIR", drafts_dir)

    result = await skills_routes.get_skill_draft_detail("draft")

    assert result["success"] is True
    assert result["data"]["is_draft"] is True
    assert "草稿内容" in result["data"]["content"]


@pytest.mark.asyncio
async def test_update_skill_draft_detail(monkeypatch, tmp_path: Path):
    drafts_dir = tmp_path / "skills" / ".drafts"
    drafts_dir.mkdir(parents=True)
    draft_file = drafts_dir / "draft.md"
    draft_file.write_text("# 草稿技能\n\n## 概述\n旧内容。", encoding="utf-8")

    monkeypatch.setattr(skills_routes, "DRAFTS_DIR", drafts_dir)

    result = await skills_routes.update_skill_draft_detail(
        "draft",
        {"content": "# 草稿技能\n\n## 概述\n新内容。"},
    )

    assert result["success"] is True
    assert result["data"]["is_draft"] is True
    assert draft_file.read_text(encoding="utf-8") == "# 草稿技能\n\n## 概述\n新内容。"

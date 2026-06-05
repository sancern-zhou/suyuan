from pathlib import Path

import pytest

from app.tools.utility.skill_management.skill_paths import (
    render_skill_draft_markdown,
    resolve_skill_file,
    sanitize_skill_filename,
)


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

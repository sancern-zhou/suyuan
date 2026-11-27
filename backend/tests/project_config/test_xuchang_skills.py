# -*- coding: utf-8 -*-
"""许昌项目技能目录（skills_dir）与共享技能库的组合解析契约。"""
from __future__ import annotations

import pytest

from app.agent.selection_context import (
    SKILLS_DIR,
    active_skill_dirs,
    describe_skill_item,
    load_skill_selection,
)
from app.project_config.loader import load_project_context
from app.project_config.paths import project_skills_dir
from app.tools.utility.skill_management.skill_paths import resolve_skill_file


def test_xuchang_composes_project_and_shared_skill_dirs(monkeypatch):
    monkeypatch.setattr(settings_module(), "project_id", "xuchang")

    dirs = active_skill_dirs()

    assert dirs[0] == project_skills_dir(load_project_context("xuchang")).resolve()
    assert dirs[1] == SKILLS_DIR.resolve()
    assert len(dirs) == 2


def test_default_project_keeps_shared_dir_only(monkeypatch):
    monkeypatch.setattr(settings_module(), "project_id", "default")

    assert active_skill_dirs() == [SKILLS_DIR.resolve()]


def test_xuchang_resolves_project_skill_and_shared_skill(monkeypatch):
    monkeypatch.setattr(settings_module(), "project_id", "xuchang")
    dirs = active_skill_dirs()

    project_skill = resolve_skill_file("xuchang_station_daily_source_report", skills_dir=dirs)
    shared_skill = resolve_skill_file("analysis_report_workflow", skills_dir=dirs)

    assert project_skill.resolve().parent == dirs[0] / "xuchang_station_daily_source_report"
    assert shared_skill.resolve().parent == SKILLS_DIR.resolve()


def test_project_skill_frontmatter_drives_selection_contract(monkeypatch):
    monkeypatch.setattr(settings_module(), "project_id", "xuchang")

    selection = load_skill_selection(
        "xuchang_station_daily_source_report",
        available_tools={"read_file", "execute_python", "create_report_package"},
    )
    assert selection.name == "许昌市昨日污染回顾分析"
    assert selection.required_tools == [
        "read_file",
        "execute_python",
        "create_report_package",
    ]

    with pytest.raises(ValueError, match="missing required tools"):
        load_skill_selection(
            "xuchang_station_daily_source_report",
            available_tools={"read_file"},
        )


def test_lightweight_environment_skills_are_project_scoped(monkeypatch):
    monkeypatch.setattr(settings_module(), "project_id", "xuchang")
    dirs = active_skill_dirs()

    database = load_skill_selection("environment-database-lookup", skills_dir=dirs)
    evidence = load_skill_selection("environment-evidence-lookup", skills_dir=dirs)

    assert "最多两个来源" in database.content
    assert "最多两条核心来源" in evidence.content
    assert database.description.startswith("当用户需要从环境监测")
    assert evidence.description.startswith("当用户明确需要污染机理")


def test_optional_spatial_and_document_skills_keep_lightweight_boundaries(monkeypatch):
    monkeypatch.setattr(settings_module(), "project_id", "xuchang")
    dirs = active_skill_dirs()

    spatial = load_skill_selection("environment-spatial-audit", skills_dir=dirs)
    document = load_skill_selection("evidence-document-extraction", skills_dir=dirs)

    assert "不把空间邻近直接写成污染贡献或责任归因" in spatial.content
    assert "默认最多处理两份文档" in document.content


def test_describe_skill_item_reads_project_frontmatter(monkeypatch):
    monkeypatch.setattr(settings_module(), "project_id", "xuchang")
    skill_file = (
        project_skills_dir(load_project_context("xuchang"))
        / "xuchang_station_daily_source_report"
        / "SKILL.md"
    )

    descriptor = describe_skill_item(
        {"name": "许昌市昨日污染回顾分析", "file": str(skill_file)},
        available_tools={"read_file"},
    )

    assert descriptor["aliases"] == ["许昌市昨日污染回顾分析"]
    assert descriptor["enabled"] is True
    assert descriptor["compatible"] is False
    assert descriptor["missing_tools"] == ["execute_python", "create_report_package"]


def settings_module():
    from config import settings

    return settings

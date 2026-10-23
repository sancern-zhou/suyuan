# -*- coding: utf-8 -*-
"""SKILL.md frontmatter 自声明解析：aliases / required_tools / enabled。"""
from app.tools.utility.skill_management.skill_paths import parse_skill_metadata


def test_frontmatter_declarations_are_parsed():
    content = (
        "---\n"
        "name: 许昌市昨日污染回顾分析 Skill\n"
        "description: 以冻结证据生成日报。\n"
        "aliases:\n"
        "  - 许昌市昨日污染回顾分析\n"
        "required_tools:\n"
        "  - read_file\n"
        "  - execute_python\n"
        "enabled: true\n"
        "---\n"
        "\n"
        "# 许昌市昨日污染回顾分析 Skill\n"
    )

    metadata = parse_skill_metadata(content, "xuchang_station_daily_source_report/SKILL.md")

    assert metadata["title"] == "许昌市昨日污染回顾分析 Skill"
    assert metadata["description"] == "以冻结证据生成日报。"
    assert metadata["aliases"] == ["许昌市昨日污染回顾分析"]
    assert metadata["required_tools"] == ["read_file", "execute_python"]
    assert metadata["enabled"] is True


def test_frontmatter_accepts_inline_list_and_disabled_flag():
    content = (
        "---\n"
        "name: 演示技能\n"
        "description: 内联列表写法。\n"
        "aliases: 别名一, 别名二、别名三\n"
        "required_tools: read_file, write_file\n"
        "enabled: false\n"
        "---\n"
    )

    metadata = parse_skill_metadata(content, "demo.md")

    assert metadata["aliases"] == ["别名一", "别名二", "别名三"]
    assert metadata["required_tools"] == ["read_file", "write_file"]
    assert metadata["enabled"] is False


def test_legacy_document_without_frontmatter_keeps_defaults():
    content = "# 老技能\n\n## 概述\n旧的概述段落。\n"

    metadata = parse_skill_metadata(content, "legacy.md")

    assert metadata["title"] == "老技能"
    assert metadata["description"] == "旧的概述段落。"
    assert metadata["aliases"] == []
    assert metadata["required_tools"] == []
    assert metadata["enabled"] is True


def test_broken_frontmatter_falls_back_to_headings():
    content = "---\nname: [未闭合\n\n# 兜底标题\n"

    metadata = parse_skill_metadata(content, "broken.md")

    assert metadata["title"] == "兜底标题"
    assert metadata["enabled"] is True


def test_frontmatter_metadata_wins_over_legacy_headings():
    content = (
        "---\n"
        "name: 声明名称\n"
        "description: 声明描述。\n"
        "---\n\n"
        "# 正文标题\n\n"
        "## 概述\n正文概述。\n"
    )

    metadata = parse_skill_metadata(content, "demo/SKILL.md")

    assert metadata["title"] == "声明名称"
    assert metadata["description"] == "声明描述。"


def test_non_mapping_frontmatter_falls_back_to_legacy_metadata():
    content = "---\n- invalid\n---\n\n# 兜底标题\n\n## 概述\n兜底描述。\n"

    metadata = parse_skill_metadata(content, "demo/SKILL.md")

    assert metadata["title"] == "兜底标题"
    assert metadata["description"] == "兜底描述。"

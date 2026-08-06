from pathlib import Path

from app.services.skills_index import generate_skills_index
from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool


def test_generate_skills_index_writes_sorted_parseable_entries(tmp_path: Path):
    (tmp_path / "zeta.md").write_text(
        "# Zeta Skill\n\n## 概述\nSecond skill.\n",
        encoding="utf-8",
    )
    (tmp_path / "alpha.md").write_text(
        "# Alpha Skill\n\n## 概述\nFirst skill.\n",
        encoding="utf-8",
    )

    result = generate_skills_index(tmp_path)
    index_path = tmp_path / "SKILLS_INDEX.md"
    content = index_path.read_text(encoding="utf-8")
    tool = ListSkillsTool()
    tool.skills_dir = tmp_path
    tool.index_file = index_path

    assert result == {"count": 2, "index_path": str(index_path)}
    assert content.index("alpha.md") < content.index("zeta.md")
    assert tool._load_skills_from_index() == [
        {
            "name": "Alpha Skill",
            "file": str(tmp_path / "alpha.md"),
            "description": "First skill.",
        },
        {
            "name": "Zeta Skill",
            "file": str(tmp_path / "zeta.md"),
            "description": "Second skill.",
        },
    ]


def test_generate_skills_index_excludes_existing_index(tmp_path: Path):
    (tmp_path / "SKILLS_INDEX.md").write_text("stale", encoding="utf-8")

    result = generate_skills_index(tmp_path)

    assert result["count"] == 0
    assert "SKILLS_INDEX.md)(" not in (tmp_path / "SKILLS_INDEX.md").read_text(encoding="utf-8")

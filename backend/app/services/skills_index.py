from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.tools.utility.skill_management.skill_paths import parse_skill_metadata
from app.utils.path_config import format_agent_path, resolve_agent_path


DEFAULT_SKILLS_DIR = resolve_agent_path("backend/docs/skills")
INDEX_FILENAME = "SKILLS_INDEX.md"


def _single_line(value: str) -> str:
    return " ".join(str(value).split())


def generate_skills_index(skills_dir: Path | None = None) -> dict[str, object]:
    if skills_dir is None:
        from app.agent.selection_context import active_skills_dir
        skills_dir = active_skills_dir()
    skills_dir = skills_dir.resolve()
    if not skills_dir.is_dir():
        raise FileNotFoundError(format_agent_path(skills_dir))

    entries: list[tuple[str, str, str]] = []
    skill_paths = list(skills_dir.glob("*.md")) + list(skills_dir.glob("*/SKILL.md"))
    for skill_path in sorted(skill_paths, key=lambda path: str(path.relative_to(skills_dir)).lower()):
        if skill_path.name == INDEX_FILENAME:
            continue
        metadata = parse_skill_metadata(
            skill_path.read_text(encoding="utf-8"),
            skill_path.name,
        )
        title = _single_line(metadata["title"]).replace("[", "").replace("]", "")
        description = _single_line(metadata["description"])
        entries.append((title, skill_path.relative_to(skills_dir).as_posix(), description))

    lines = [
        "# 技能索引",
        "",
        "此文件由技能管理服务自动生成，请勿手动编辑。",
        "",
    ]
    lines.extend(
        f"- [{title}]({filename}) - {description}"
        for title, filename, description in entries
    )
    content = "\n".join(lines).rstrip() + "\n"

    index_path = skills_dir / INDEX_FILENAME
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=skills_dir,
            prefix=f".{INDEX_FILENAME}.",
            delete=False,
        ) as handle:
            handle.write(content)
            temporary_path = Path(handle.name)
        os.replace(temporary_path, index_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return {
        "count": len(entries),
        "index_path": format_agent_path(index_path),
    }

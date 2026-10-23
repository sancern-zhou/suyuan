from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.tools.utility.skill_management.skill_paths import (
    iter_skill_documents,
    normalize_skill_dirs,
    parse_skill_metadata,
)
from app.utils.path_config import format_agent_path, resolve_agent_path


DEFAULT_SKILLS_DIR = resolve_agent_path("backend/docs/skills")
INDEX_FILENAME = "SKILLS_INDEX.md"


def _single_line(value: str) -> str:
    return " ".join(str(value).split())


def generate_skills_index(skills_dir: Path | None = None) -> dict[str, object]:
    """Rebuild SKILLS_INDEX.md in the primary skills directory.

    When ``skills_dir`` is omitted the composed view of every active skills
    directory is indexed (project dir first, then the shared library); entry
    links are repo-relative agent paths so one index can span both.
    """
    if skills_dir is None:
        from app.agent.selection_context import active_skill_dirs

        dirs = active_skill_dirs()
    else:
        dirs = normalize_skill_dirs(skills_dir)
    primary = dirs[0].resolve()
    if not primary.is_dir():
        raise FileNotFoundError(format_agent_path(primary))

    entries: list[tuple[str, str, str]] = []
    seen_ids: set[str] = set()
    for directory in dirs:
        for skill_path in iter_skill_documents(directory):
            skill_id = (
                skill_path.parent.name
                if skill_path.name == "SKILL.md"
                else skill_path.stem
            )
            if skill_id in seen_ids:
                continue
            seen_ids.add(skill_id)
            metadata = parse_skill_metadata(
                skill_path.read_text(encoding="utf-8"),
                skill_path.name,
            )
            title = _single_line(metadata["title"]).replace("[", "").replace("]", "")
            description = _single_line(metadata["description"])
            entries.append((title, format_agent_path(skill_path), description))

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

    index_path = primary / INDEX_FILENAME
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=primary,
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

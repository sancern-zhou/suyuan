from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any, Iterable


BACKEND_DIR = Path(__file__).resolve().parents[4]
SKILLS_DIR = BACKEND_DIR / "docs" / "skills"
DRAFTS_DIR = SKILLS_DIR / ".drafts"


def active_skill_paths() -> tuple[Path, Path]:
    """Return the active project's published skills and draft directory."""
    from app.agent.selection_context import active_skills_dir

    skills_dir = active_skills_dir()
    return skills_dir, skills_dir / ".drafts"


_UNSAFE_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


def sanitize_skill_filename(name: str) -> str:
    raw = (name or "").strip().replace("\\", "/")
    raw = raw.split("/")[-1]
    raw = raw.replace("..", "")
    raw = _UNSAFE_CHARS.sub("_", raw).strip(" .")
    if not raw:
        raise ValueError("技能名称不能为空")
    if not raw.endswith(".md"):
        raw = f"{raw}.md"
    return raw


def ensure_within_directory(path: Path, directory: Path) -> Path:
    resolved_path = path.resolve()
    resolved_dir = directory.resolve()
    if resolved_path != resolved_dir and resolved_dir not in resolved_path.parents:
        raise ValueError(f"路径越界: {path}")
    return resolved_path


def resolve_skill_file(
    name: str,
    *,
    include_drafts: bool = False,
    skills_dir: Path = SKILLS_DIR,
    drafts_dir: Path = DRAFTS_DIR,
) -> Path:
    if any(part in (name or "") for part in ("../", "..\\", "/", "\\")):
        raise ValueError("技能名称不能包含路径分隔符")

    filename = sanitize_skill_filename(name)
    official_path = ensure_within_directory(skills_dir / filename, skills_dir)
    if official_path.exists() and official_path.is_file():
        return official_path

    if include_drafts:
        draft_path = ensure_within_directory(drafts_dir / filename, drafts_dir)
        if draft_path.exists() and draft_path.is_file():
            return draft_path

    raise FileNotFoundError(filename)


def parse_skill_metadata(content: str, fallback_name: str) -> dict[str, str]:
    title = Path(fallback_name).stem
    description = "暂无描述"
    lines = content.splitlines()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip() or title
        if stripped.startswith("## 概述") and index + 1 < len(lines):
            candidate = lines[index + 1].strip()
            if candidate and not candidate.startswith("#"):
                description = candidate
                break

    return {"title": title, "description": description}


def _render_bullets(values: Iterable[str]) -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    return "\n".join(f"- {item}" for item in items) if items else "- 未提供"


def _render_required_tools(required_tools: list[Any]) -> str:
    lines: list[str] = []
    for item in required_tools:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            purpose = str(item.get("purpose", "")).strip()
        else:
            name = str(item).strip()
            purpose = ""
        if name:
            lines.append(f"- `{name}`：{purpose or '用途待审核确认'}")
    return "\n".join(lines) if lines else "- 未提供"


def _render_steps(workflow_steps: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for index, step in enumerate(workflow_steps, start=1):
        title = str(step.get("title") or f"步骤{index}").strip()
        purpose = str(step.get("purpose") or "说明该步骤的目的").strip()
        operation = str(step.get("operation") or "说明该步骤的具体操作").strip()
        sections.append(
            f"### 步骤{index}：{title}\n"
            f"- **目的**: {purpose}\n"
            f"- **操作**: {operation}"
        )
    return "\n\n".join(sections)


def render_skill_draft_markdown(
    *,
    title: str,
    description: str,
    applicable_scenarios: list[str],
    required_tools: list[Any],
    workflow_steps: list[dict[str, Any]],
    notes: list[str] | None = None,
    source_summary: str | None = None,
    source_session_id: str | None = None,
) -> str:
    created_at = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    source_session_line = (
        f"source_session_id: {source_session_id}" if source_session_id else "source_session_id: 未提供"
    )
    source_summary_text = source_summary or "未提供"

    return (
        f"# {title.strip()}\n\n"
        "<!--\n"
        "status: draft\n"
        f"created_at: {created_at}\n"
        "source_mode: assistant\n"
        f"{source_session_line}\n"
        "-->\n\n"
        "## 概述\n"
        f"{description.strip()}\n\n"
        "## 适用场景\n"
        f"{_render_bullets(applicable_scenarios)}\n\n"
        "## 所需工具\n"
        f"{_render_required_tools(required_tools)}\n\n"
        "## 详细流程\n\n"
        f"{_render_steps(workflow_steps)}\n\n"
        "## 注意事项\n"
        "- 文件系统相对路径统一以 suyuan 项目根目录为基准；后端路径必须包含 `backend/` 前缀。\n"
        f"{_render_bullets(notes or [])}\n\n"
        "## 验证方式\n"
        "- 核对输入条件、关键中间结果和最终产物是否符合用户目标。\n"
        "- 复用前确认城市、时间、文件路径、数据口径等上下文已经更新。\n\n"
        "## 来源摘要\n"
        f"{source_summary_text}\n"
    )

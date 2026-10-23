"""Resolve explicit skill and conversation-file selections for one agent turn."""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.agent.resources.contracts import ResourceStatus
from app.agent.resources.resource_map import resource_access_path
from app.agent.resources.resource_service import StoredResource

SKILLS_DIR = Path(__file__).resolve().parents[2] / "docs" / "skills"


def active_skill_dirs() -> list[Path]:
    """Ordered skill search path: the project dir first, then the shared legacy dir.

    Projects which do not configure ``backend.skills_dir`` keep serving the
    shared ``backend/docs/skills`` directory only.
    """
    from app.project_config.loader import load_project_context
    from app.project_config.paths import project_skills_dir
    from config.settings import settings

    project_dir = project_skills_dir(load_project_context(settings.project_id)).resolve()
    shared = SKILLS_DIR.resolve()
    if project_dir == shared:
        return [shared]
    return [project_dir, shared]


def active_skills_dir() -> Path:
    """Primary skills directory (project-owned when configured) for writes/index."""
    return active_skill_dirs()[0]


class InvalidContextReference(ValueError):
    """Raised when a requested resource is absent, inactive, or not a file."""


@dataclass(frozen=True)
class SkillSelection:
    skill_id: str
    name: str
    description: str
    content: str
    required_tools: list[str]


def _registry_declaration(metadata_root: Path, skill_id: str) -> dict:
    """Deployment-level registry entry for one skill, keyed by its owning dir."""
    metadata_path = metadata_root / "skills_metadata.json"
    if not metadata_path.is_file():
        if metadata_root.resolve() == SKILLS_DIR.resolve():
            from app.agent.skill_metadata import SKILL_METADATA

            return dict(SKILL_METADATA.get(skill_id) or {})
        return {}
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata = (payload.get("skills") or {}).get(skill_id) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"invalid skill metadata: {skill_id}")
    return metadata


def _skill_declaration(skill_file: Path, skill_id: str, content: str | None = None) -> dict:
    """Merge a skill's frontmatter self-declaration with its registry entry.

    The frontmatter carries the asset's own SKILL.md declarations; the owning
    directory's registry (``skills_metadata.json``, or the legacy hardcoded map
    for the shared directory) stays authoritative where it defines a key.
    """
    from app.tools.utility.skill_management.skill_paths import parse_skill_metadata

    is_package = skill_file.name == "SKILL.md"
    metadata_root = skill_file.parent.parent if is_package else skill_file.parent
    if content is None:
        content = skill_file.read_text(encoding="utf-8")
    parsed = parse_skill_metadata(content, skill_file.name)
    declaration: dict = {
        "aliases": list(parsed.get("aliases") or []),
        "required_tools": list(parsed.get("required_tools") or []),
        "enabled": bool(parsed.get("enabled", True)),
    }
    registry = _registry_declaration(metadata_root, skill_id)
    for key in ("aliases", "required_tools", "enabled"):
        if key in registry:
            declaration[key] = registry[key]
    for key, value in registry.items():
        declaration.setdefault(key, value)
    return declaration


def _resolve_published_skill(skill_id: str, skills_dirs: Sequence[Path]) -> Path:
    if not skill_id or any(part in skill_id for part in ("/", "\\", "..")):
        raise ValueError("invalid skill id")
    normalized_id = skill_id[:-3] if skill_id.endswith(".md") else skill_id
    for skills_dir in skills_dirs:
        root = skills_dir.resolve()
        candidates = [
            (skills_dir / f"{normalized_id}.md").resolve(),
            (skills_dir / normalized_id / "SKILL.md").resolve(),
        ]
        for path in candidates:
            if root in path.parents and path.is_file():
                return path
    raise FileNotFoundError(f"{normalized_id}.md or {normalized_id}/SKILL.md")


def describe_skill_item(
    item: dict,
    *,
    available_tools: set[str] | None = None,
) -> dict:
    """Add stable selection metadata and current-mode compatibility to a skill item."""
    path = Path(str(item.get("file") or ""))
    is_package = path.name == "SKILL.md" and path.parent.name
    skill_id = (
        path.parent.name if is_package else path.stem
    ) or str(item.get("id") or item.get("name") or "")
    declared: dict = {}
    if path.is_file():
        try:
            declared = _skill_declaration(path, skill_id)
        except (OSError, ValueError, json.JSONDecodeError):
            declared = {}
    required_tools = list(declared.get("required_tools") or [])
    missing_tools = (
        [name for name in required_tools if name not in available_tools]
        if available_tools is not None
        else []
    )
    return {
        **item,
        "id": skill_id,
        "aliases": list(declared.get("aliases") or item.get("aliases") or []),
        "enabled": bool(declared.get("enabled", item.get("enabled", True))),
        "required_tools": required_tools,
        "missing_tools": missing_tools,
        "compatible": not missing_tools,
    }


def load_skill_selection(
    skill_id: str,
    *,
    skills_dir: Path | Sequence[Path] | None = None,
    available_tools: set[str] | None = None,
) -> SkillSelection:
    """Load one published skill and optionally enforce current-mode dependencies."""
    skills_dirs = (
        [skills_dir] if isinstance(skills_dir, Path) else list(skills_dir or [])
    ) or active_skill_dirs()
    path = _resolve_published_skill(skill_id, skills_dirs)
    normalized_id = skill_id[:-3] if skill_id.endswith(".md") else skill_id
    content = path.read_text(encoding="utf-8")
    from app.tools.utility.skill_management.skill_paths import parse_skill_metadata

    metadata = parse_skill_metadata(content, path.name)
    declared = _skill_declaration(path, normalized_id, content=content)
    if declared.get("enabled", True) is False:
        raise ValueError(f"skill is disabled: {normalized_id}")
    required_tools = list(declared.get("required_tools") or [])
    if available_tools is not None:
        missing = [name for name in required_tools if name not in available_tools]
        if missing:
            raise ValueError("missing required tools: " + ", ".join(missing))
    return SkillSelection(
        skill_id=normalized_id,
        name=metadata["title"],
        description=metadata["description"],
        content=content,
        required_tools=required_tools,
    )


def resource_refs_to_runtime_attachments(
    refs: Sequence[StoredResource],
) -> list[dict[str, str]]:
    """Convert selected image refs into native multimodal planner attachments."""
    attachments: list[dict[str, str]] = []
    for ref in refs:
        mime_type = str(ref.media_type or ref.metadata.get("mime_type") or "")
        path = ref.locator.get("path")
        if not mime_type.startswith("image/"):
            continue
        if ref.status != ResourceStatus.ACTIVE.value:
            raise ValueError(f"current_turn_image_invalid: {ref.resource_id}")
        if not path:
            raise ValueError(f"current_turn_image_invalid: {ref.resource_id}")
        resolved_path = Path(path).resolve()
        if not resolved_path.exists() or not resolved_path.is_file():
            raise ValueError(f"current_turn_image_missing: {ref.resource_id}")
        attachments.append({
            "file_id": str(ref.metadata.get("file_id") or ref.resource_id),
            "name": ref.label,
            "type": "image",
            "mime_type": mime_type,
            "local_path": str(resolved_path),
            "url": str(resolved_path),
        })
    return attachments


def select_conversation_resources(
    resources: Sequence[StoredResource],
    requested_ids: Sequence[str],
) -> list[StoredResource]:
    """Resolve active file resources in the order submitted by the user."""
    by_id = {resource.resource_id: resource for resource in resources}
    selected: list[StoredResource] = []
    for resource_id in dict.fromkeys(requested_ids):
        resource = by_id.get(resource_id)
        if (
            resource is None
            or resource.status != ResourceStatus.ACTIVE.value
            or resource.kind not in {"file", "artifact"}
        ):
            raise InvalidContextReference(
                f"invalid conversation file reference: {resource_id}"
            )
        selected.append(resource)
    return selected


def resource_refs_to_current_turn_context(
    refs: Sequence[StoredResource],
) -> str:
    """Render server-authorized current-turn file facts for the planner."""
    lines: list[str] = []
    for index, ref in enumerate(refs, 1):
        access_path = resource_access_path(ref)
        if not access_path:
            raise InvalidContextReference(
                f"current turn resource path is unavailable: {ref.resource_id}"
            )
        lines.extend([
            f"{index}. {ref.label}",
            f"   资源 ID: {ref.resource_id}",
            "   类型: "
            f"{ref.media_type or ref.metadata.get('mime_type') or 'application/octet-stream'}",
            f"   路径: {access_path}",
        ])
    return "\n".join(lines)

def resource_refs_to_message_attachments(
    refs: Sequence[StoredResource],
) -> list[dict[str, str]]:
    """Project selected refs into the public attachment contract used by chat UI."""
    attachments: list[dict[str, str]] = []
    for ref in refs:
        mime_type = str(ref.media_type or ref.metadata.get("mime_type") or "")
        file_id = str(ref.metadata.get("file_id") or "")
        attachment = {
            "resource_id": ref.resource_id,
            "name": ref.label,
            "type": "image" if file_id and mime_type.startswith("image/") else "file",
        }
        if file_id:
            attachment["file_id"] = file_id
            attachment["url"] = f"/api/upload/{file_id}"
        if mime_type:
            attachment["mime_type"] = mime_type
        attachments.append(attachment)
    return attachments

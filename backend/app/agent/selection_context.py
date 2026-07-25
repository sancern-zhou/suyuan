"""Resolve explicit skill and conversation-file selections for one agent turn."""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.agent.resources.models import (
    ResourceKind,
    ResourceLocator,
    ResourceRole,
    ResourceStatus,
    SessionResourceRef,
)
from app.agent.resources.resource_service import StoredResource

SKILLS_DIR = Path(__file__).resolve().parents[2] / "docs" / "skills"


class InvalidContextReference(ValueError):
    """Raised when a requested resource is absent, inactive, or not a file."""


@dataclass(frozen=True)
class SkillSelection:
    skill_id: str
    name: str
    description: str
    content: str
    required_tools: list[str]


def _declared_skill_metadata(skills_dir: Path, skill_id: str) -> dict:
    metadata_path = skills_dir / "skills_metadata.json"
    if not metadata_path.is_file() and skills_dir.resolve() == SKILLS_DIR.resolve():
        from app.agent.skill_metadata import SKILL_METADATA

        return dict(SKILL_METADATA.get(skill_id) or {})
    if not metadata_path.is_file():
        return {}
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata = (payload.get("skills") or {}).get(skill_id) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"invalid skill metadata: {skill_id}")
    return metadata


def _resolve_published_skill(skill_id: str, skills_dir: Path) -> Path:
    if not skill_id or any(part in skill_id for part in ("/", "\\", "..")):
        raise ValueError("invalid skill id")
    filename = skill_id if skill_id.endswith(".md") else f"{skill_id}.md"
    path = (skills_dir / filename).resolve()
    root = skills_dir.resolve()
    if root not in path.parents or not path.is_file():
        raise FileNotFoundError(filename)
    return path


def _skill_metadata(content: str, fallback_name: str) -> tuple[str, str]:
    name = Path(fallback_name).stem
    description = "暂无描述"
    lines = content.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            name = stripped[2:].strip() or name
        if stripped == "## 概述" and index + 1 < len(lines):
            candidate = lines[index + 1].strip()
            if candidate and not candidate.startswith("#"):
                description = candidate
                break
    return name, description


def describe_skill_item(
    item: dict,
    *,
    available_tools: set[str] | None = None,
) -> dict:
    """Add stable selection metadata and current-mode compatibility to a skill item."""
    path = Path(str(item.get("file") or ""))
    skill_id = path.stem or str(item.get("id") or item.get("name") or "")
    declared = _declared_skill_metadata(path.parent, skill_id) if path.parent else {}
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
    skills_dir: Path = SKILLS_DIR,
    available_tools: set[str] | None = None,
) -> SkillSelection:
    """Load one published skill and optionally enforce current-mode dependencies."""
    path = _resolve_published_skill(skill_id, skills_dir)
    content = path.read_text(encoding="utf-8")
    name, description = _skill_metadata(content, path.name)
    declared = _declared_skill_metadata(skills_dir, path.stem)
    if declared.get("enabled", True) is False:
        raise ValueError(f"skill is disabled: {path.stem}")
    required_tools = list(declared.get("required_tools") or [])
    if available_tools is not None:
        missing = [name for name in required_tools if name not in available_tools]
        if missing:
            raise ValueError("missing required tools: " + ", ".join(missing))
    return SkillSelection(
        skill_id=path.stem,
        name=name,
        description=description,
        content=content,
        required_tools=required_tools,
    )


def select_conversation_files(
    refs: list[SessionResourceRef], requested_ids: list[str]
) -> list[SessionResourceRef]:
    """Resolve active file/artifact refs in the exact order requested by the user."""
    by_id = {ref.ref_id: ref for ref in refs}
    selected: list[SessionResourceRef] = []
    for ref_id in dict.fromkeys(requested_ids):
        ref = by_id.get(ref_id)
        if (
            ref is None
            or ref.status is not ResourceStatus.ACTIVE
            or ref.kind not in {ResourceKind.FILE, ResourceKind.ARTIFACT}
        ):
            raise InvalidContextReference(f"invalid conversation file reference: {ref_id}")
        selected.append(ref)
    return selected


def selected_resource_projection(
    selected_refs: list[SessionResourceRef] | None,
    *,
    saved_refs: list[SessionResourceRef] | None = None,
) -> list[SessionResourceRef]:
    """Keep the complete manifest; explicit refs affect ranking, not visibility."""
    del selected_refs
    return list(saved_refs or [])


def build_uploaded_file_ref(
    *,
    file_id: str,
    file_path: str,
    filename: str,
    mime_type: str,
) -> SessionResourceRef:
    """Create the canonical manifest entry for a completed chat upload."""
    return SessionResourceRef.create(
        kind=ResourceKind.FILE,
        locator=ResourceLocator(path=file_path),
        logical_key=f"upload:{file_id}",
        role=ResourceRole.ATTACHMENT,
        label=filename,
        tool_name="upload_chat_file",
        run_id=f"upload:{file_id}",
        turn_sequence=0,
        metadata={
            "source": "user_upload",
            "file_id": file_id,
            "mime_type": mime_type,
        },
    )


def serialize_conversation_files(refs: list[SessionResourceRef]) -> list[dict]:
    """Return active file-like resources suitable for the composer menu."""
    return [
        {
            "ref_id": ref.ref_id,
            "kind": ref.kind.value,
            "role": ref.role.value,
            "label": ref.label,
            "tool_name": ref.tool_name,
            "turn_sequence": ref.turn_sequence,
            "status": ref.status.value,
            "created_at": ref.created_at.isoformat(),
            "last_used_at": ref.last_used_at.isoformat() if ref.last_used_at else None,
            "metadata": ref.metadata,
        }
        for ref in refs
        if ref.status is ResourceStatus.ACTIVE
        and ref.kind in {ResourceKind.FILE, ResourceKind.ARTIFACT}
    ]


def resource_refs_to_runtime_attachments(
    refs: Sequence[StoredResource],
) -> list[dict[str, str]]:
    """Convert selected image refs into native multimodal planner attachments."""
    attachments: list[dict[str, str]] = []
    for ref in refs:
        mime_type = str(ref.metadata.get("mime_type") or "")
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


def resource_refs_to_message_attachments(
    refs: Sequence[StoredResource],
) -> list[dict[str, str]]:
    """Project selected refs into the public attachment contract used by chat UI."""
    attachments: list[dict[str, str]] = []
    for ref in refs:
        mime_type = str(ref.metadata.get("mime_type") or "")
        file_id = str(ref.metadata.get("file_id") or "")
        attachment = {
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


def mark_uploaded_file_missing(
    refs: list[SessionResourceRef], file_id: str
) -> list[SessionResourceRef]:
    """Return manifest updates that invalidate a deleted uploaded file."""
    return [
        ref.model_copy(update={"status": ResourceStatus.MISSING})
        for ref in refs
        if ref.metadata.get("file_id") == file_id
        and ref.status is ResourceStatus.ACTIVE
    ]

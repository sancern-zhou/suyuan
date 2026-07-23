from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def editable_ppt_project_root(pptx_path: str | Path) -> Path | None:
    resolved = Path(pptx_path).resolve()
    for candidate in (resolved.parent, *resolved.parents):
        if (candidate / ".editable-ppt" / "state.json").is_file():
            return candidate
    return None


def validate_editable_ppt_delivery(pptx_path: str | Path) -> dict[str, Any]:
    target = Path(pptx_path).resolve()
    project = editable_ppt_project_root(target)
    if project is None:
        return {"managed": False, "allowed": True}

    metadata = project / ".editable-ppt"
    state = _read_json(metadata / "state.json")
    finalized = _read_json(metadata / "finalized.json")
    if not finalized:
        return {
            "managed": True,
            "allowed": False,
            "code": "EDITABLE_PPT_NOT_FINALIZED",
            "message": "可编辑 PPT 尚未通过当前 revision 的 finalize，禁止交付旧编译产物",
            "project_dir": str(project),
        }

    expected_path = Path(str(finalized.get("pptxPath", ""))).resolve()
    stale = (
        bool(state.get("dirty_slides"))
        or finalized.get("sourceRevision") != state.get("revision")
        or finalized.get("sourceHashes") != state.get("hashes")
        or expected_path != target
        or not target.is_file()
        or finalized.get("pptxSha256") != (_sha256(target) if target.is_file() else None)
    )
    if stale:
        return {
            "managed": True,
            "allowed": False,
            "code": "EDITABLE_PPT_FINALIZATION_STALE",
            "message": "可编辑 PPT 源码、revision 或文件哈希已变化，必须重新 strict 编译并 finalize",
            "project_dir": str(project),
        }
    return {"managed": True, "allowed": True, "project_dir": str(project)}

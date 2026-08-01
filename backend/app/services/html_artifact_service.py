"""Service for standalone HTML presentation artifacts."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import structlog

from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

HTML_ARTIFACT_ROOT = (get_data_registry() / "html_artifacts").resolve()
HTML_ARTIFACT_ID_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")
RESERVED_META_KEYS = {
    "artifact_id",
    "artifact_type",
    "created_at",
    "updated_at",
    "files",
    "assets",
    "version",
    "preview_version",
    "html_url",
    "download_url",
    "history",
    "share_token",
    "shared_at",
}


def _safe_artifact_id(raw_id: str | None) -> str:
    artifact_id = HTML_ARTIFACT_ID_PATTERN.sub("_", str(raw_id or "").strip()).strip("_")
    return artifact_id or f"html_artifact_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _now_iso() -> str:
    return datetime.now().isoformat()


def _file_fingerprint(path: Path) -> Dict[str, Any]:
    stat = path.stat()
    return {
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "preview_version": f"{stat.st_mtime_ns}-{stat.st_size}",
    }


def _copy_asset(source: str, artifact_dir: Path, preferred_name: str | None = None) -> Dict[str, Any]:
    src = Path(source).expanduser().resolve()
    if not src.exists():
        return {"source": source, "success": False, "error": "asset not found"}

    assets_dir = artifact_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    target = assets_dir / (preferred_name or src.name)
    target = target.resolve()
    target.relative_to(assets_dir.resolve())

    if src.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)
    else:
        shutil.copy2(src, target)

    return {
        "source": str(src),
        "success": True,
        "path": str(target),
        "relative_path": str(target.relative_to(artifact_dir)),
    }


class HtmlArtifactService:
    """Create, serve, download, and share HTML presentation artifacts."""

    def __init__(self, root: Path = HTML_ARTIFACT_ROOT) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def get_artifact_dir(self, artifact_id: str) -> Path:
        if not artifact_id or any(sep in artifact_id for sep in ("/", "\\")) or ".." in artifact_id:
            raise ValueError("Invalid artifact_id")
        artifact_dir = (self.root / artifact_id).resolve()
        artifact_dir.relative_to(self.root)
        return artifact_dir

    def get_index_path(self, artifact_id: str) -> Path:
        index_path = self.get_artifact_dir(artifact_id) / "index.html"
        if not index_path.exists():
            raise FileNotFoundError(f"index.html not found for artifact_id={artifact_id}")
        return index_path

    def get_artifact_id_from_index_path(self, path: str | Path) -> Optional[str]:
        """Return artifact_id when path is html_artifacts/{artifact_id}/index.html."""
        try:
            index_path = Path(path).expanduser().resolve()
            relative = index_path.relative_to(self.root)
        except (OSError, ValueError):
            return None

        if len(relative.parts) == 2 and relative.parts[1] == "index.html":
            return relative.parts[0]
        return None

    def get_meta_path(self, artifact_id: str) -> Path:
        return self.get_artifact_dir(artifact_id) / "meta.json"

    def read_meta(self, artifact_id: str) -> Dict[str, Any]:
        meta_path = self.get_meta_path(artifact_id)
        if not meta_path.exists():
            return {}
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("html_artifact_meta_read_failed", artifact_id=artifact_id, error=str(exc))
            return {}

    def write_meta(self, artifact_id: str, meta: Dict[str, Any]) -> None:
        meta_path = self.get_meta_path(artifact_id)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def build_html_preview(self, artifact_id: str) -> Dict[str, Any]:
        index_path = self.get_index_path(artifact_id)
        fingerprint = _file_fingerprint(index_path)
        return {
            "html_id": artifact_id,
            "file_type": "html_artifact",
            "schema_version": "html_artifact.v1",
            "preview_version": fingerprint["preview_version"],
        }

    def record_update(self, artifact_id: str, *, source: str = "file_edit") -> Dict[str, Any]:
        """Update artifact metadata after managed edits so previews/downloads track revisions."""
        index_path = self.get_index_path(artifact_id)
        fingerprint = _file_fingerprint(index_path)
        meta = self.read_meta(artifact_id)
        now = _now_iso()
        previous_version = int(meta.get("version") or 0)
        history = list(meta.get("history") or [])
        history.append(
            {
                "version": previous_version + 1,
                "updated_at": now,
                "source": source,
                "preview_version": fingerprint["preview_version"],
                "size": fingerprint["size"],
            }
        )

        meta.update(
            {
                "artifact_id": artifact_id,
                "artifact_type": "html_artifact",
                "updated_at": now,
                "version": previous_version + 1,
                "files": {"html": str(index_path)},
                "preview_version": fingerprint["preview_version"],
                "history": history[-20:],
            }
        )
        meta.setdefault("title", artifact_id)
        meta.setdefault("created_at", now)
        self.write_meta(artifact_id, meta)
        return meta

    def create_artifact(
        self,
        artifact_id: str | None,
        html_content: str,
        *,
        title: str | None = None,
        assets: Optional[Iterable[Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        safe_id = _safe_artifact_id(artifact_id)
        artifact_dir = self.get_artifact_dir(safe_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        copied_assets = []
        for item in assets or []:
            if isinstance(item, str):
                copied_assets.append(_copy_asset(item, artifact_dir))
            elif isinstance(item, dict) and item.get("path"):
                copied_assets.append(_copy_asset(item["path"], artifact_dir, item.get("name")))

        index_path = artifact_dir / "index.html"
        index_path.write_text(html_content, encoding="utf-8")

        existing_meta = self.read_meta(safe_id)
        now = _now_iso()
        meta = {
            "artifact_id": safe_id,
            "title": title or safe_id,
            "artifact_type": "html_artifact",
            "created_at": existing_meta.get("created_at") or now,
            "updated_at": now,
            "files": {"html": str(index_path)},
            "assets": copied_assets,
            "version": int(existing_meta.get("version") or 0) + 1,
        }
        fingerprint = _file_fingerprint(index_path)
        meta["preview_version"] = fingerprint["preview_version"]
        history = list(existing_meta.get("history") or [])
        history.append(
            {
                "version": meta["version"],
                "updated_at": now,
                "source": "create_html_artifact",
                "preview_version": fingerprint["preview_version"],
                "size": fingerprint["size"],
            }
        )
        meta["history"] = history[-20:]
        if metadata:
            for key, value in metadata.items():
                if key not in RESERVED_META_KEYS:
                    meta[key] = value
        self.write_meta(safe_id, meta)

        logger.info("html_artifact_created", artifact_id=safe_id, index_path=str(index_path))
        return {
            "artifact_id": safe_id,
            "file_path": str(index_path),
            "artifact_dir": str(artifact_dir),
            "file_type": "html_artifact",
            "html_preview": self.build_html_preview(safe_id),
            "copied_assets": copied_assets,
        }


html_artifact_service = HtmlArtifactService()

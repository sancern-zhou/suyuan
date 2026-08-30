"""Persist image evidence produced by operations work-order visual audits."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from app.services.ops_audit.remote_fetch import guarded_get


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".heic"}


def archive_visual_evidence(audit: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Archive all image sources linked to visual findings and enrich evidence."""

    evidence_root = output_dir.resolve() / "visual_evidence"
    items: list[dict[str, Any]] = []
    persisted_by_source: dict[str, dict[str, Any]] = {}
    for record in audit.get("records", []):
        for issue in record.get("scoring_issues", []):
            evidence = _parse_evidence(issue.get("evidence"))
            if not _is_visual_finding(issue, evidence):
                continue
            archived = []
            for source_item in _image_sources(evidence):
                archived_item = _archive_one(
                    source_item,
                    evidence_root=evidence_root,
                    working_order_code=str(
                        record.get("working_order_code")
                        or evidence.get("working_order_code")
                        or "unknown"
                    ),
                    rule_id=str(issue.get("rule_id") or "UNKNOWN_VISUAL_RULE"),
                    persisted_by_source=persisted_by_source,
                )
                archived.append(archived_item)
                items.append(
                    {
                        "working_order_code": record.get("working_order_code"),
                        "rule_id": issue.get("rule_id"),
                        **archived_item,
                    }
                )
            evidence["evidence_images"] = archived
            issue["evidence"] = json.dumps(evidence, ensure_ascii=False, default=str)

    manifest_path = evidence_root / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "item_count": len(items),
        "success_count": sum(item["status"] == "success" for item in items),
        "failed_count": sum(item["status"] == "failed" for item in items),
        "unique_file_count": len(
            {item.get("local_path") for item in items if item.get("local_path")}
        ),
        "items": items,
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {**payload, "manifest_path": str(manifest_path)}


def _parse_evidence(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_visual_finding(issue: dict[str, Any], evidence: dict[str, Any]) -> bool:
    field = str(issue.get("field") or "")
    rule_id = str(issue.get("rule_id") or "")
    return bool(
        field.startswith("attachment.vision")
        or rule_id == "ATTACHMENT_MULTIPOINT_GRADIENT_REVIEW"
        or evidence.get("needs_visual_review") is True
        or evidence.get("needs_manual_review") is True
    )


def _image_sources(evidence: dict[str, Any]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    top_source = next(
        (
            str(evidence.get(key) or "").strip()
            for key in (
                "attachment_local_path",
                "attachment_url",
                "attachment_original_path",
                "source",
            )
            if str(evidence.get(key) or "").strip()
        ),
        "",
    )
    if top_source:
        sources.append(
            {
                "source": top_source,
                "filename": str(
                    evidence.get("attachment_filename")
                    or evidence.get("filename")
                    or Path(top_source).name
                ),
            }
        )
    for reviewed in evidence.get("reviewed_images", []):
        if not isinstance(reviewed, dict):
            continue
        source = next(
            (
                str(reviewed.get(key) or "").strip()
                for key in (
                    "attachment_local_path",
                    "attachment_url",
                    "attachment_original_path",
                    "source",
                )
                if str(reviewed.get(key) or "").strip()
            ),
            "",
        )
        if source:
            sources.append(
                {
                    "source": source,
                    "filename": str(
                        reviewed.get("attachment_filename")
                        or reviewed.get("filename")
                        or Path(source).name
                    ),
                }
            )
    deduplicated = []
    seen = set()
    for item in sources:
        source = item["source"]
        if source in seen:
            continue
        seen.add(source)
        deduplicated.append(item)
    return deduplicated


def _archive_one(
    source_item: dict[str, str],
    *,
    evidence_root: Path,
    working_order_code: str,
    rule_id: str,
    persisted_by_source: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source = source_item["source"]
    filename = source_item.get("filename") or Path(source).name
    if Path(filename).suffix.lower() not in IMAGE_EXTENSIONS:
        return {"source": source, "filename": filename, "status": "failed", "error": "非支持的图片格式"}
    if source in persisted_by_source:
        return dict(persisted_by_source[source])
    target_dir = evidence_root / _safe_component(working_order_code) / _safe_component(rule_id)
    safe_filename = _safe_filename(filename)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:10]
    target = target_dir / f"{Path(safe_filename).stem}_{digest}{Path(safe_filename).suffix.lower()}"
    try:
        source_type, resolved_source = _resolve_source(source)
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            if source_type == "local":
                shutil.copy2(Path(resolved_source), target)
            else:
                response = guarded_get(str(resolved_source), timeout=30)
                response.raise_for_status()
                target.write_bytes(response.content)
        if target.stat().st_size == 0:
            raise ValueError("图片内容为空")
    except Exception as exc:
        return {
            "source": source,
            "filename": filename,
            "status": "failed",
            "error": str(exc),
        }
    result = {
        "source": source,
        "filename": filename,
        "status": "success",
        "local_path": str(target.resolve()),
        "relative_path": str(target.relative_to(evidence_root.parent)).replace("\\", "/"),
    }
    persisted_by_source[source] = result
    return dict(result)


def _resolve_source(source: str) -> tuple[str, Path | str]:
    direct = Path(source).expanduser()
    if direct.is_file():
        return "local", direct.resolve()
    attachment_root = str(
        os.getenv("OPS_ATTACHMENT_ROOT") or os.getenv("ATTACHMENT_ROOT") or ""
    ).strip()
    if attachment_root:
        rooted = Path(attachment_root).expanduser() / source.lstrip("/")
        if rooted.is_file():
            return "local", rooted.resolve()
    if source.startswith(("http://", "https://")):
        return "remote", source
    base_url = str(
        os.getenv("OPS_ATTACHMENT_BASE_URL")
        or os.getenv("ATTACHMENT_BASE_URL")
        or ""
    ).strip()
    if source.startswith("/") and base_url:
        return "remote", urljoin(base_url.rstrip("/") + "/", source.lstrip("/"))
    raise FileNotFoundError(f"无法解析视觉证据来源: {source}")


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip(" .")
    return cleaned or "evidence.jpg"


def _safe_component(value: str) -> str:
    return _safe_filename(value).replace(".", "_")

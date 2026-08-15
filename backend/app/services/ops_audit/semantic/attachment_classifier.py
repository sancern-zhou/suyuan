"""Attachment metadata classifier for semantic review routing."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any


DEFAULT_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".heic"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}


def classify_attachment_metadata(
    descriptor: str,
    *,
    filename: str | None = None,
    global_keywords: dict[str, list[str]] | None = None,
    photo_extensions: list[str] | None = None,
) -> dict[str, Any]:
    """Return coarse attachment types and a confidence hint from metadata only."""

    text = f"{filename or ''} {descriptor or ''}".lower()
    keywords = global_keywords or {}
    types: set[str] = set()
    matched_keywords: dict[str, list[str]] = {}

    for attachment_type, values in keywords.items():
        matches = [str(keyword) for keyword in values if str(keyword).lower() in text]
        if matches:
            types.add(str(attachment_type))
            matched_keywords[str(attachment_type)] = matches

    suffix = _suffix_from_attachment_text(filename or descriptor)
    normalized_photo_extensions = {str(item).lower() for item in (photo_extensions or list(DEFAULT_PHOTO_EXTENSIONS))}
    if suffix in normalized_photo_extensions:
        types.add("photo")
    if suffix in DOCUMENT_EXTENSIONS:
        # “现场/图片”等通用关键词不能把文档附件误判成照片；
        # 文档类附件仍按其扩展名归入 report。
        types.discard("photo")
    if suffix == ".pdf" and "photo" not in types:
        types.add("certificate")
    if suffix in DOCUMENT_EXTENSIONS and "photo" not in types:
        types.add("report")
    if not types and filename:
        types.add("unknown")

    confidence = 0.9 if len(types) >= 2 else 0.7 if types else 0.2
    return {
        "types": sorted(types),
        "matched_keywords": matched_keywords,
        "confidence_hint": round(confidence, 2),
    }


def _file_name_from_text(text: str) -> str:
    if not text:
        return ""
    return text.replace("\\", "/").split("/")[-1].strip()


def _suffix_from_attachment_text(text: str) -> str:
    """Extract an extension even when metadata contains spaces or extra fields."""

    normalized = str(text or "").replace("\\", "/")
    extension_pattern = r"\.(?:jpg|jpeg|png|bmp|gif|webp|heic|pdf|doc|docx|xls|xlsx)(?=\s|$|/)"
    matches = re.findall(extension_pattern, normalized, flags=re.IGNORECASE)
    if matches:
        return matches[-1].lower()
    return Path(_file_name_from_text(normalized).lower()).suffix

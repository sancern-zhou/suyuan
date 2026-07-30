from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlencode

BASE_URL = "https://permit.mee.gov.cn"
PAGE_PATH = "/perxxgkinfo/syssb/xkgg/xkgg!downFilePng.action"


@dataclass(frozen=True)
class CopyViewer:
    page_count: int
    page_urls: tuple[str, ...]


def detect_document_kind(content_type: str, body: bytes) -> str:
    """Identify downloaded content using magic bytes before server metadata."""
    sample = body[:32].lstrip()
    if sample.startswith(b"%PDF-"):
        return "pdf"
    if sample.startswith(b"\x89PNG\r\n\x1a\n") or sample.startswith(b"\xff\xd8\xff"):
        return "image"
    if sample.lower().startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        return "html"
    media_type = content_type.partition(";")[0].strip().lower()
    if media_type == "application/pdf":
        return "pdf"
    if media_type.startswith("image/"):
        return "image"
    if media_type in {"text/html", "application/xhtml+xml"}:
        return "html"
    return "unknown"


def _input_value(html: str, element_id: str) -> str:
    patterns = (
        rf'<input[^>]*\bid=["\']{re.escape(element_id)}["\'][^>]*\bvalue=["\']([^"\']*)',
        rf'<input[^>]*\bvalue=["\']([^"\']*)["\'][^>]*\bid=["\']{re.escape(element_id)}["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def parse_copy_viewer(html: str) -> CopyViewer:
    count_text = _input_value(html, "imgCount")
    pkid = _input_value(html, "pkid")
    data_id = _input_value(html, "dataid")
    if not count_text.isdigit() or int(count_text) < 1 or not pkid or not data_id:
        raise ValueError("copy viewer does not contain usable page metadata")
    page_count = int(count_text)
    urls = tuple(
        f"{BASE_URL}{PAGE_PATH}?"
        + urlencode(
            {
                "datafileid": f"{pkid}_{page_no}",
                "fileType": "pdffile",
                "dataid": data_id,
            }
        )
        for page_no in range(1, page_count + 1)
    )
    return CopyViewer(page_count=page_count, page_urls=urls)

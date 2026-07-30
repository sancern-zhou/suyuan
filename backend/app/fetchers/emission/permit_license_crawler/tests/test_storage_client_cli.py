from __future__ import annotations

import argparse
from pathlib import Path

import httpx
import pytest
from PIL import Image
from pypdf import PdfReader

from app.fetchers.emission.permit_license_crawler.cli import validate_args
from app.fetchers.emission.permit_license_crawler.client import (
    PermitPlatformClient,
    PlatformBlockedError,
)
from app.fetchers.emission.permit_license_crawler.document_downloader import (
    detect_document_kind,
)
from app.fetchers.emission.permit_license_crawler.pdf_builder import build_pdf
from app.fetchers.emission.permit_license_crawler.storage import FileStorage


def test_storage_rejects_path_escape_and_writes_with_checksum(tmp_path: Path):
    storage = FileStorage(tmp_path)

    with pytest.raises(ValueError, match="unsafe path"):
        storage.write_bytes(Path("../outside.txt"), b"bad")

    result = storage.write_bytes(Path("permit") / "detail.html", b"hello")
    assert result.path == tmp_path / "permit" / "detail.html"
    assert result.size_bytes == 5
    assert result.sha256 == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert not list(tmp_path.rglob("*.part"))


def test_pdf_builder_preserves_page_order(tmp_path: Path):
    first = tmp_path / "001.png"
    second = tmp_path / "002.png"
    Image.new("RGB", (10, 20), "red").save(first)
    Image.new("RGB", (20, 10), "blue").save(second)

    output = build_pdf([first, second], tmp_path / "copy.pdf")

    reader = PdfReader(str(output))
    assert len(reader.pages) == 2
    assert reader.pages[0].mediabox.height > reader.pages[0].mediabox.width
    assert reader.pages[1].mediabox.width > reader.pages[1].mediabox.height


@pytest.mark.parametrize(
    ("content_type", "body", "expected"),
    [
        ("application/pdf", b"%PDF-1.7\n", "pdf"),
        ("image/png", b"\x89PNG\r\n\x1a\n", "image"),
        ("text/html; charset=UTF-8", b"<html></html>", "html"),
        ("text/html", b"%PDF-1.4\n", "pdf"),
    ],
)
def test_document_kind_uses_signature_before_header(content_type, body, expected):
    assert detect_document_kind(content_type, body) == expected


@pytest.mark.asyncio
async def test_client_stops_immediately_on_403():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request, text="forbidden")

    client = PermitPlatformClient(
        min_delay_seconds=0,
        max_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(PlatformBlockedError, match="HTTP 403"):
        await client.get("https://permit.mee.gov.cn/test")
    await client.aclose()


@pytest.mark.asyncio
async def test_client_detects_challenge_body_with_success_status():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, text="请输入验证码后继续访问")

    client = PermitPlatformClient(
        min_delay_seconds=0,
        max_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(PlatformBlockedError, match="challenge page"):
        await client.get("https://permit.mee.gov.cn/test")
    await client.aclose()


def _args(phase: str, max_pages: int | None, max_licenses: int | None):
    return argparse.Namespace(
        phase=phase,
        max_pages=max_pages,
        max_licenses=max_licenses,
        min_delay_seconds=2.0,
        max_delay_seconds=5.0,
    )


def test_cli_requires_explicit_phase_limit():
    with pytest.raises(ValueError, match="--max-pages"):
        validate_args(_args("list", None, None))
    with pytest.raises(ValueError, match="--max-licenses"):
        validate_args(_args("detail", None, None))


def test_cli_rejects_invalid_delay_range():
    args = _args("list", 2, None)
    args.min_delay_seconds = 5.0
    args.max_delay_seconds = 2.0
    with pytest.raises(ValueError, match="delay"):
        validate_args(args)

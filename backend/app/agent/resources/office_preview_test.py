import asyncio
from pathlib import Path

from app.agent.resources import office_preview
from app.agent.resources.contracts import (
    ResourceCapability,
    ResourceDeclaration,
    ResourceKind,
    ResourceLocator,
    ResourceRelation,
    ResourceRenderer,
    ResourceRole,
)
from app.agent.resources.office_preview import attach_office_preview_declarations


def _primary(path: Path) -> ResourceDeclaration:
    return ResourceDeclaration(
        kind=ResourceKind.FILE,
        group_key="report:current",
        resource_key="docx",
        relation=ResourceRelation.PRIMARY,
        role=ResourceRole.OUTPUT,
        label="报告.docx",
        locator=ResourceLocator(path=str(path)),
        format="docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        renderer=ResourceRenderer.FILE,
        capabilities={ResourceCapability.DOWNLOAD},
    )


def _fake_converter(pdf_dir: Path):
    def _convert(source: Path):
        out_dir = source.parent / office_preview._PREVIEW_DIRNAME
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{source.stem}.pdf"
        target.write_bytes(b"%PDF-1.4 fake")
        return target

    return _convert


def test_attaches_pdf_preview_for_docx_primary(tmp_path):
    docx = tmp_path / "报告.docx"
    docx.write_bytes(b"docx-bytes")
    primary = _primary(docx)

    async def run():
        return await attach_office_preview_declarations([primary])

    original = office_preview._convert_to_pdf
    office_preview._convert_to_pdf = _fake_converter(pdf_dir=tmp_path)
    try:
        result = asyncio.run(run())
    finally:
        office_preview._convert_to_pdf = original

    assert len(result) == 2
    preview = result[1]
    assert preview.relation is ResourceRelation.PREVIEW
    assert preview.parent_key == primary.resource_key
    assert preview.media_type == "application/pdf"
    assert preview.renderer.value == "pdf"
    assert preview.locator.path.endswith("报告.pdf")
    assert preview.group_key == primary.group_key


def test_skips_when_preview_already_present(tmp_path):
    docx = tmp_path / "报告.docx"
    docx.write_bytes(b"docx-bytes")
    primary = _primary(docx)
    existing = ResourceDeclaration(
        kind=ResourceKind.FILE,
        group_key=primary.group_key,
        resource_key="docx-html-preview",
        parent_key=primary.resource_key,
        relation=ResourceRelation.PREVIEW,
        label="报告.html",
        locator=ResourceLocator(path=str(tmp_path / "报告.html")),
        format="html",
        media_type="text/html",
        renderer=ResourceRenderer.HTML,
        capabilities={ResourceCapability.PREVIEW},
    )

    async def run():
        return await attach_office_preview_declarations([primary, existing])

    def _fail(source):
        raise AssertionError("must not convert when a preview already exists")

    original = office_preview._convert_to_pdf
    office_preview._convert_to_pdf = _fail
    try:
        result = asyncio.run(run())
    finally:
        office_preview._convert_to_pdf = original

    assert result == [primary, existing]


def test_conversion_failure_keeps_original_declarations(tmp_path):
    docx = tmp_path / "报告.docx"
    docx.write_bytes(b"docx-bytes")
    primary = _primary(docx)

    async def run():
        return await attach_office_preview_declarations([primary])

    def _fail(source):
        return None

    original = office_preview._convert_to_pdf
    office_preview._convert_to_pdf = _fail
    try:
        result = asyncio.run(run())
    finally:
        office_preview._convert_to_pdf = original

    assert result == [primary]


def test_non_office_primary_is_untouched(tmp_path):
    docx = tmp_path / "数据.csv"
    docx.write_text("a,b\n1,2")
    primary = _primary(docx)

    async def run():
        return await attach_office_preview_declarations([primary])

    def _fail(source):
        raise AssertionError("must not convert non-office files")

    original = office_preview._convert_to_pdf
    office_preview._convert_to_pdf = _fail
    try:
        result = asyncio.run(run())
    finally:
        office_preview._convert_to_pdf = original

    assert result == [primary]

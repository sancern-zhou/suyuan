import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.agent.resources import office_preview
from app.tools.office import soffice as soffice_module
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


def _fake_soffice(args, **kwargs):
    """Mimic soffice: write `<stem>.pdf` into the --outdir directory."""
    out_dir = Path(args[args.index("--outdir") + 1])
    source = Path(args[-1])
    (out_dir / f"{source.stem}.pdf").write_bytes(b"pdf-of-" + source.read_bytes())
    return SimpleNamespace(returncode=0, stderr="")


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
    assert preview.locator.path.endswith(".pdf")
    assert preview.label == "报告.pdf"
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


def test_attaches_pdf_preview_for_xlsx_primary(tmp_path):
    xlsx = tmp_path / "统计表.xlsx"
    xlsx.write_bytes(b"xlsx-bytes")
    primary = ResourceDeclaration(
        kind=ResourceKind.FILE,
        group_key="analysis:current",
        resource_key="xlsx",
        relation=ResourceRelation.PRIMARY,
        role=ResourceRole.OUTPUT,
        label="统计表.xlsx",
        locator=ResourceLocator(path=str(xlsx)),
        format="xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        renderer=ResourceRenderer.SPREADSHEET,
        capabilities={ResourceCapability.PREVIEW, ResourceCapability.DOWNLOAD},
    )

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
    assert preview.format == "pdf"
    assert preview.locator.path.endswith(".pdf")
    assert preview.label == "统计表.pdf"


def test_regenerates_preview_when_source_is_rewritten(tmp_path, monkeypatch):
    docx = tmp_path / "报告.docx"
    docx.write_bytes(b"docx-v1")
    monkeypatch.setattr(soffice_module, "run_soffice", _fake_soffice)

    first = office_preview._convert_to_pdf(docx)
    assert first is not None
    assert first.read_bytes() == b"pdf-of-docx-v1"

    docx.write_bytes(b"docx-v2-with-longer-content")
    second = office_preview._convert_to_pdf(docx)
    assert second is not None
    assert second != first
    assert second.read_bytes() == b"pdf-of-docx-v2-with-longer-content"
    assert not first.exists()


def test_reuses_preview_while_source_unchanged(tmp_path, monkeypatch):
    docx = tmp_path / "报告.docx"
    docx.write_bytes(b"docx-stable")
    monkeypatch.setattr(soffice_module, "run_soffice", _fake_soffice)

    first = office_preview._convert_to_pdf(docx)
    calls = []

    def _counting(*args, **kwargs):
        calls.append(args)
        return _fake_soffice(*args, **kwargs)

    monkeypatch.setattr(soffice_module, "run_soffice", _counting)
    second = office_preview._convert_to_pdf(docx)
    assert second == first
    assert calls == []


def test_same_stem_docx_and_xlsx_get_distinct_previews(tmp_path, monkeypatch):
    (tmp_path / "报告.docx").write_bytes(b"docx-bytes")
    (tmp_path / "报告.xlsx").write_bytes(b"xlsx-bytes")
    monkeypatch.setattr(soffice_module, "run_soffice", _fake_soffice)

    docx_pdf = office_preview._convert_to_pdf(tmp_path / "报告.docx")
    xlsx_pdf = office_preview._convert_to_pdf(tmp_path / "报告.xlsx")

    assert docx_pdf is not None and xlsx_pdf is not None
    assert docx_pdf != xlsx_pdf
    assert docx_pdf.read_bytes() == b"pdf-of-docx-bytes"
    assert xlsx_pdf.read_bytes() == b"pdf-of-xlsx-bytes"
    assert docx_pdf.exists() and xlsx_pdf.exists()


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

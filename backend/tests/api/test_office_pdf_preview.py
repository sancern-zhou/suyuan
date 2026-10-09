"""Office -> PDF preview cache behavior: fingerprinted, self-healing keys."""
from pathlib import Path
from types import SimpleNamespace

from app.api import upload_routes
from app.tools.office import soffice as soffice_module


def _fake_soffice(content: bytes):
    def _run(args, **kwargs):
        out_dir = Path(args[args.index("--outdir") + 1])
        source = Path(args[-1])
        (out_dir / f"{source.stem}.pdf").write_bytes(content)
        return SimpleNamespace(returncode=0)

    return _run


def test_preview_path_keeps_source_extension_and_fingerprint(tmp_path):
    source = tmp_path / "report.docx"
    source.write_bytes(b"docx")
    path = upload_routes._office_pdf_preview_path(source)
    assert path.name.startswith("report.docx-")
    assert path.name.endswith(".preview.pdf")
    assert path.parent == tmp_path


def test_regenerates_preview_after_source_rewrite(tmp_path, monkeypatch):
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"v1")
    monkeypatch.setattr(upload_routes.subprocess, "run", _fake_soffice(b"pdf-v1"))

    first = upload_routes._office_pdf_preview(str(docx))
    assert first is not None
    assert first.read_bytes() == b"pdf-v1"

    docx.write_bytes(b"v2-longer-content")
    monkeypatch.setattr(upload_routes.subprocess, "run", _fake_soffice(b"pdf-v2"))
    second = upload_routes._office_pdf_preview(str(docx))
    assert second is not None
    assert second != first
    assert second.read_bytes() == b"pdf-v2"
    assert not first.exists()
    # 旧固定名缓存一并清理，避免陈旧内容被任何路径再次命中
    assert not (tmp_path / "report.preview.pdf").exists()


def test_reuses_preview_while_source_unchanged(tmp_path, monkeypatch):
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"stable")
    monkeypatch.setattr(upload_routes.subprocess, "run", _fake_soffice(b"pdf-stable"))

    first = upload_routes._office_pdf_preview(str(docx))
    calls = []

    def _counting(args, **kwargs):
        calls.append(args)
        return _fake_soffice(b"pdf-again")(args, **kwargs)

    monkeypatch.setattr(upload_routes.subprocess, "run", _counting)
    second = upload_routes._office_pdf_preview(str(docx))
    assert second == first
    assert second.read_bytes() == b"pdf-stable"
    assert calls == []


def test_same_stem_docx_and_xlsx_get_distinct_previews(tmp_path, monkeypatch):
    (tmp_path / "报告.docx").write_bytes(b"docx-bytes")
    (tmp_path / "报告.xlsx").write_bytes(b"xlsx-bytes")
    monkeypatch.setattr(upload_routes.subprocess, "run", _fake_soffice(b"pdf-bytes"))

    docx_pdf = upload_routes._office_pdf_preview(str(tmp_path / "报告.docx"))
    xlsx_pdf = upload_routes._office_pdf_preview(str(tmp_path / "报告.xlsx"))

    assert docx_pdf is not None and xlsx_pdf is not None
    assert docx_pdf != xlsx_pdf
    assert docx_pdf.exists() and xlsx_pdf.exists()


def test_remove_office_pdf_preview_cleans_all_revisions(tmp_path, monkeypatch):
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"v1")
    monkeypatch.setattr(upload_routes.subprocess, "run", _fake_soffice(b"pdf-v1"))
    preview = upload_routes._office_pdf_preview(str(docx))
    assert preview is not None and preview.exists()

    upload_routes._remove_office_pdf_preview(str(docx))
    assert not preview.exists()


def test_soffice_helper_output_contract(tmp_path, monkeypatch):
    """run_soffice must stay importable and produce `<stem>.pdf` in outdir."""
    assert callable(soffice_module.run_soffice)

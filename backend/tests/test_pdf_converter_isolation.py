"""pdf_converter 并发串味回归测试：产出必须取自本次调用的私有工作目录。"""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import pdf_converter as pdf_converter_module
from app.services.pdf_converter import PDFConverter


def _converter(tmp_path: Path) -> PDFConverter:
    converter = PDFConverter()
    converter.output_dir = tmp_path / "office_pdf_cache"
    converter.output_dir.mkdir(parents=True, exist_ok=True)
    return converter


def test_convert_to_pdf_picks_own_output_not_shared_cache(tmp_path, monkeypatch):
    converter = _converter(tmp_path)
    stale = converter.output_dir / "stale-uuid.pdf"
    stale.write_bytes(b"pdf-of-some-other-document")

    seen = {}

    def fake_run_soffice(args, **kwargs):
        seen["args"] = args
        out_dir = Path(args[args.index("--outdir") + 1])
        source = Path(args[-1])
        (out_dir / f"{source.stem}.pdf").write_bytes(b"pdf-of-" + source.read_bytes())
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(pdf_converter_module, "run_soffice", fake_run_soffice)

    source = tmp_path / "河南省18地市空气质量逐小时数据.xlsx"
    source.write_bytes(b"xlsx-bytes")

    result = asyncio.run(converter.convert_to_pdf(str(source)))

    produced = Path(result["pdf_path"])
    assert produced == converter.output_dir / f"{result['pdf_id']}.pdf"
    assert produced.read_bytes() == b"pdf-of-xlsx-bytes"
    assert any(
        argument.startswith("-env:UserInstallation=file://")
        for argument in seen["args"]
    )
    assert stale.read_bytes() == b"pdf-of-some-other-document"


def test_convert_to_pdf_without_output_raises_instead_of_stealing(tmp_path, monkeypatch):
    converter = _converter(tmp_path)
    stale = converter.output_dir / "stale-uuid.pdf"
    stale.write_bytes(b"pdf-of-some-other-document")

    # 模拟 soffice 单实例让位：returncode=0 但没有任何产出
    monkeypatch.setattr(
        pdf_converter_module,
        "run_soffice",
        lambda args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )

    source = tmp_path / "表格.xlsx"
    source.write_bytes(b"xlsx-bytes")

    with pytest.raises(Exception, match="No PDF file generated"):
        asyncio.run(converter.convert_to_pdf(str(source)))

    assert [item.name for item in converter.output_dir.glob("*.pdf")] == [
        "stale-uuid.pdf"
    ]


def test_rebuild_pdf_picks_own_output(tmp_path, monkeypatch):
    converter = _converter(tmp_path)
    pdf_id = "target-uuid"
    (converter.output_dir / f"{pdf_id}.pdf").unlink(missing_ok=True)
    other = converter.output_dir / "other-uuid.pdf"
    other.write_bytes(b"pdf-of-another-document")

    def fake_run_soffice(args, **kwargs):
        out_dir = Path(args[args.index("--outdir") + 1])
        source = Path(args[-1])
        (out_dir / f"{source.stem}.pdf").write_bytes(b"pdf-of-" + source.read_bytes())
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(pdf_converter_module, "run_soffice", fake_run_soffice)

    source = tmp_path / "报告.xlsx"
    source.write_bytes(b"report-xlsx-bytes")

    result = asyncio.run(converter.rebuild_pdf(pdf_id, str(source)))

    produced = Path(result["pdf_path"])
    assert produced == converter.output_dir / f"{pdf_id}.pdf"
    assert produced.read_bytes() == b"pdf-of-report-xlsx-bytes"
    assert other.read_bytes() == b"pdf-of-another-document"

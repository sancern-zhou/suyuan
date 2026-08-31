import fitz
import pytest

from app.knowledge_base.document_processor import DocumentProcessor


def test_fast_pdf_parse_does_not_load_unstructured(tmp_path, monkeypatch):
    pdf_path = tmp_path / "text.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "knowledge base PDF text " * 40)
        document.save(pdf_path)

    processor = DocumentProcessor.__new__(DocumentProcessor)
    monkeypatch.setattr(processor, "OCR_FORCE_MIN_TEXT_LENGTH", 10)
    monkeypatch.setattr(
        processor,
        "_get_unstructured",
        lambda: (_ for _ in ()).throw(
            AssertionError("PDF fast parsing must not load Unstructured")
        ),
    )
    monkeypatch.setattr(processor, "_extract_tables_with_pdfplumber", lambda _path: [])

    content, is_scanned = processor._try_fast_pdf_parse(str(pdf_path))

    assert is_scanned is False
    assert "knowledge base PDF text" in content


@pytest.mark.asyncio
async def test_pdf_parse_forces_ocr_when_fast_text_is_too_short(tmp_path, monkeypatch):
    pdf_path = tmp_path / "short.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "short text")
        document.save(pdf_path)

    processor = DocumentProcessor()
    monkeypatch.setattr(
        processor,
        "_extract_tables_with_pdfplumber",
        lambda _path: ["[表格 - 第1页]\n|  |"],
    )

    async def fake_process_pdf_with_ocr(_path: str) -> str:
        return "ocr-text"

    monkeypatch.setattr(processor, "_process_pdf_with_ocr", fake_process_pdf_with_ocr)

    content = await processor.parse(str(pdf_path))

    assert content == "ocr-text"

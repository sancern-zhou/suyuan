import fitz

from app.knowledge_base.document_processor import DocumentProcessor


def test_fast_pdf_parse_does_not_load_unstructured(tmp_path, monkeypatch):
    pdf_path = tmp_path / "text.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "knowledge base PDF text")
        document.save(pdf_path)

    processor = DocumentProcessor.__new__(DocumentProcessor)
    monkeypatch.setattr(
        processor,
        "_get_unstructured",
        lambda: (_ for _ in ()).throw(
            AssertionError("PDF fast parsing must not load Unstructured")
        ),
    )
    monkeypatch.setattr(processor, "_extract_tables_with_gmft", lambda _path: [])

    content, is_scanned = processor._try_fast_pdf_parse(str(pdf_path))

    assert is_scanned is False
    assert "knowledge base PDF text" in content

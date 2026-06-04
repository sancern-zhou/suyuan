import base64

import fitz

from app.services.ops_audit.semantic import ocr_adapter


def _write_pdf(path):
    doc = fitz.open()
    page = doc.new_page(width=240, height=120)
    page.insert_text((24, 60), "first page")
    doc.save(path)
    doc.close()


def test_build_image_payload_renders_local_pdf_first_page(tmp_path):
    pdf_path = tmp_path / "cert.pdf"
    _write_pdf(pdf_path)

    payload = ocr_adapter._build_image_url_payload(
        {"status": "success", "kind": "file", "path": str(pdf_path)}
    )

    assert payload["status"] == "success"
    assert payload["url"].startswith("data:image/png;base64,")
    image_bytes = base64.b64decode(payload["url"].split(",", 1)[1])
    assert image_bytes.startswith(b"\x89PNG")


def test_build_image_payload_renders_url_pdf_first_page(tmp_path, monkeypatch):
    pdf_path = tmp_path / "cert.pdf"
    _write_pdf(pdf_path)

    class _Response:
        content = pdf_path.read_bytes()

        def raise_for_status(self):
            return None

    monkeypatch.setattr(ocr_adapter.requests, "get", lambda *args, **kwargs: _Response())

    payload = ocr_adapter._build_image_url_payload(
        {"status": "success", "kind": "url", "url": "http://example.test/cert.pdf"}
    )

    assert payload["status"] == "success"
    assert payload["url"].startswith("data:image/png;base64,")
    image_bytes = base64.b64decode(payload["url"].split(",", 1)[1])
    assert image_bytes.startswith(b"\x89PNG")

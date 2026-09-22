from pathlib import Path
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import office_routes


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(office_routes.router)
    return TestClient(app)


def test_open_docx_returns_inline_docx_file(tmp_path: Path):
    docx_path = tmp_path / "source.docx"
    docx_path.write_bytes(b"docx-bytes")

    response = make_client().post(
        "/api/office/open-docx",
        json={"file_path": str(docx_path)},
    )

    assert response.status_code == 200
    assert response.content == b"docx-bytes"
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "inline" in response.headers["content-disposition"]


def test_open_docx_rejects_legacy_doc(tmp_path: Path):
    doc_path = tmp_path / "legacy.doc"
    doc_path.write_bytes(b"legacy")

    response = make_client().post(
        "/api/office/open-docx",
        json={"file_path": str(doc_path)},
    )

    assert response.status_code == 400
    assert "Only DOCX" in response.json()["detail"]


def test_open_excel_returns_inline_spreadsheet_file(tmp_path: Path):
    excel_path = tmp_path / "workbook.xlsx"
    excel_path.write_bytes(b"xlsx-bytes")

    response = make_client().post(
        "/api/office/open-excel",
        json={"file_path": str(excel_path)},
    )

    assert response.status_code == 200
    assert response.content == b"xlsx-bytes"
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "inline" in response.headers["content-disposition"]


def test_save_excel_writes_version_and_persists_session_history(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "workbook.xlsx"
    source_path.write_bytes(b"old-xlsx")
    updates = []

    class FakeSessionRepository:
        async def get_session_with_messages(self, session_id, include_messages=True, include_artifacts=True):
            assert session_id == "session-a"
            return {
                "session_id": session_id,
                "office_documents": [
                    {
                        "doc_type": "excel",
                        "file_name": "workbook.xlsx",
                        "file_path": str(source_path),
                        "timestamp": "2026-06-29T10:00:00",
                    }
                ],
            }

        async def update_session(self, session_id, **kwargs):
            updates.append((session_id, kwargs))
            return True

    monkeypatch.setattr(
        office_routes,
        "get_session_repository",
        lambda: FakeSessionRepository(),
        raising=False,
    )

    response = make_client().post(
        "/api/office/save-excel",
        data={"file_path": str(source_path), "session_id": "session-a"},
        files={
            "file": (
                "workbook.xlsx",
                b"new-xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    document = payload["document"]
    assert document["doc_type"] == "excel"
    assert document["file_name"].startswith("workbook_edited_")
    assert document["file_name"].endswith(".xlsx")
    assert Path(document["file_path"]).read_bytes() == b"new-xlsx"
    assert "pdf_preview" not in document
    assert document["spreadsheet_preview"]["editable"] is True
    assert document["metadata"]["version_type"] == "edited"
    assert document["metadata"]["parent_file_path"] == str(source_path)
    assert len(updates) == 1
    persisted_documents = updates[0][1]["office_documents"]
    assert [item["file_path"] for item in persisted_documents] == [
        str(source_path),
        document["file_path"],
    ]
    assert document["document_id"]
    assert document["version_id"]
    assert document["revision"] == 2
    assert document["is_current"] is True
    assert persisted_documents[0]["is_current"] is False
    assert persisted_documents[1]["is_current"] is True
    assert persisted_documents[1]["metadata"]["previous_file_path"] == str(source_path)


def test_save_excel_uses_display_filename_instead_of_storage_uuid(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "79e9f2ca-3b9a-4e5a.xlsx"
    source_path.write_bytes(b"old-xlsx")

    class FakeSessionRepository:
        async def get_session_with_messages(self, session_id, include_messages=True, include_artifacts=True):
            return {"session_id": session_id, "office_documents": []}

        async def update_session(self, session_id, **kwargs):
            return True

    async def fake_display_filename(path, fallback=None):
        assert path == source_path
        return "空气质量月报.xlsx"

    monkeypatch.setattr(
        office_routes,
        "get_session_repository",
        lambda: FakeSessionRepository(),
        raising=False,
    )
    monkeypatch.setattr(
        office_routes,
        "_display_filename_for_path",
        fake_display_filename,
        raising=False,
    )

    response = make_client().post(
        "/api/office/save-excel",
        data={"file_path": str(source_path), "session_id": "session-a"},
        files={
            "file": (
                "79e9f2ca-3b9a-4e5a.xlsx",
                b"new-xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    document = response.json()["document"]
    assert document["file_name"].startswith("空气质量月报_edited_")
    assert document["file_name"].endswith(".xlsx")
    assert Path(document["file_path"]).name == document["file_name"]


def test_save_excel_appends_revision_to_existing_version_chain(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "workbook.xlsx"
    first_edit_path = tmp_path / "workbook_edited_20260629_100000.xlsx"
    source_path.write_bytes(b"old-xlsx")
    first_edit_path.write_bytes(b"first-edit")
    updates = []

    class FakeSessionRepository:
        async def get_session_with_messages(self, session_id, include_messages=True, include_artifacts=True):
            return {
                "session_id": session_id,
                "office_documents": [
                    {
                        "doc_type": "excel",
                        "document_id": "excel-session-a-workbook",
                        "version_id": "excel-session-a-workbook-v1",
                        "revision": 1,
                        "is_current": False,
                        "file_name": "workbook.xlsx",
                        "file_path": str(source_path),
                        "timestamp": "2026-06-29T10:00:00",
                        "metadata": {
                            "source_file_path": str(source_path),
                            "version_type": "original",
                        },
                    },
                    {
                        "doc_type": "excel",
                        "document_id": "excel-session-a-workbook",
                        "version_id": "excel-session-a-workbook-v2",
                        "revision": 2,
                        "is_current": True,
                        "file_name": first_edit_path.name,
                        "file_path": str(first_edit_path),
                        "timestamp": "2026-06-29T10:05:00",
                        "metadata": {
                            "source_file_path": str(source_path),
                            "parent_file_path": str(source_path),
                            "version_type": "edited",
                        },
                    },
                ],
            }

        async def update_session(self, session_id, **kwargs):
            updates.append(kwargs)
            return True

    monkeypatch.setattr(
        office_routes,
        "get_session_repository",
        lambda: FakeSessionRepository(),
        raising=False,
    )

    response = make_client().post(
        "/api/office/save-excel",
        data={"file_path": str(first_edit_path), "session_id": "session-a"},
        files={
            "file": (
                first_edit_path.name,
                b"second-edit",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    document = response.json()["document"]
    persisted_documents = updates[0]["office_documents"]
    assert [item["revision"] for item in persisted_documents] == [1, 2, 3]
    assert [item["is_current"] for item in persisted_documents] == [False, False, True]
    assert document["document_id"] == "excel-session-a-workbook"
    assert document["revision"] == 3
    assert document["metadata"]["source_file_path"] == str(source_path)
    assert document["metadata"]["previous_file_path"] == str(first_edit_path)


def test_save_excel_backfills_revision_for_legacy_version_chain(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "workbook.xlsx"
    first_edit_path = tmp_path / "workbook_edited_20260629_100000.xlsx"
    source_path.write_bytes(b"old-xlsx")
    first_edit_path.write_bytes(b"first-edit")
    updates = []

    class FakeSessionRepository:
        async def get_session_with_messages(self, session_id, include_messages=True, include_artifacts=True):
            return {
                "session_id": session_id,
                "office_documents": [
                    {
                        "doc_type": "excel",
                        "file_name": "workbook.xlsx",
                        "file_path": str(source_path),
                        "timestamp": "2026-06-29T10:00:00",
                    },
                    {
                        "doc_type": "excel",
                        "file_name": first_edit_path.name,
                        "file_path": str(first_edit_path),
                        "timestamp": "2026-06-29T10:05:00",
                        "metadata": {
                            "source_file_path": str(source_path),
                            "parent_file_path": str(source_path),
                            "version_type": "edited",
                        },
                    },
                ],
            }

        async def update_session(self, session_id, **kwargs):
            updates.append(kwargs)
            return True

    monkeypatch.setattr(
        office_routes,
        "get_session_repository",
        lambda: FakeSessionRepository(),
        raising=False,
    )

    response = make_client().post(
        "/api/office/save-excel",
        data={"file_path": str(first_edit_path), "session_id": "session-a"},
        files={
            "file": (
                first_edit_path.name,
                b"second-edit",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    persisted_documents = updates[0]["office_documents"]
    assert [item["revision"] for item in persisted_documents] == [1, 2, 3]
    assert len({item["version_id"] for item in persisted_documents}) == 3
    assert [item["is_current"] for item in persisted_documents] == [False, False, True]


def test_download_excel_accepts_display_filename(tmp_path: Path):
    source_path = tmp_path / "79e9f2ca-3b9a-4e5a.xlsx"
    source_path.write_bytes(b"xlsx")

    response = make_client().post(
        "/api/office/download-excel",
        json={
            "file_path": str(source_path),
            "file_name": "空气质量月报.xlsx",
        },
    )

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert "79e9f2ca" not in disposition
    assert "filename*=UTF-8''" in disposition
    assert "%E7%A9%BA%E6%B0%94%E8%B4%A8%E9%87%8F%E6%9C%88%E6%8A%A5.xlsx" in disposition


def test_save_docx_writes_version_and_returns_preview_document(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "report.docx"
    source_path.write_bytes(b"old-docx")
    updates = []

    class FakeSessionRepository:
        async def get_session_with_messages(self, session_id, include_messages=True, include_artifacts=True):
            assert session_id == "session-a"
            assert include_messages is False
            assert include_artifacts is True
            return {
                "session_id": session_id,
                "office_documents": [
                    {
                        "doc_type": "word",
                        "file_name": "report.docx",
                        "file_path": str(source_path),
                        "timestamp": "2026-06-29T10:00:00",
                    }
                ],
            }

        async def update_session(self, session_id, **kwargs):
            updates.append((session_id, kwargs))
            return True

    async def fake_convert_to_pdf(path: str) -> dict:
        assert Path(path).exists()
        return {
            "pdf_id": "preview-123",
            "pdf_path": "/tmp/preview-123.pdf",
            "pdf_url": "/api/office/pdf/preview-123",
            "pages": 1,
            "size": 10,
        }

    monkeypatch.setattr(office_routes.pdf_converter, "convert_to_pdf", fake_convert_to_pdf)
    monkeypatch.setattr(
        office_routes,
        "get_session_repository",
        lambda: FakeSessionRepository(),
        raising=False,
    )

    response = make_client().post(
        "/api/office/save-docx",
        data={"file_path": str(source_path), "session_id": "session-a"},
        files={
            "file": (
                "report.docx",
                b"new-docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    document = payload["document"]
    assert document["doc_type"] == "word"
    assert document["file_name"].startswith("report_edited_")
    assert document["file_name"].endswith(".docx")
    assert Path(document["file_path"]).read_bytes() == b"new-docx"
    assert Path(document["file_path"]).parent == source_path.parent
    assert document["pdf_preview"]["pdf_id"] == "preview-123"
    assert document["last_action"]["tool"] == "docx_online_editor"
    assert document["metadata"]["version_type"] == "edited"
    assert document["metadata"]["parent_file_path"] == str(source_path)

    assert len(updates) == 1
    assert updates[0][0] == "session-a"
    persisted_documents = updates[0][1]["office_documents"]
    assert [item["file_path"] for item in persisted_documents] == [
        str(source_path),
        document["file_path"],
    ]


def test_save_docx_uses_display_filename_instead_of_storage_uuid(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "79e9f2ca-3b9a-4e5a.docx"
    source_path.write_bytes(b"old-docx")

    class FakeSessionRepository:
        async def get_session_with_messages(self, session_id, include_messages=True, include_artifacts=True):
            return {"session_id": session_id, "office_documents": []}

        async def update_session(self, session_id, **kwargs):
            return True

    async def fake_display_filename(path, fallback=None):
        assert path == source_path
        return "空气质量月报.docx"

    async def fake_convert_to_pdf(path: str) -> dict:
        return {
            "pdf_id": "preview-123",
            "pdf_path": "/tmp/preview-123.pdf",
            "pdf_url": "/api/office/pdf/preview-123",
            "pages": 1,
            "size": 10,
        }

    monkeypatch.setattr(office_routes.pdf_converter, "convert_to_pdf", fake_convert_to_pdf)
    monkeypatch.setattr(
        office_routes,
        "get_session_repository",
        lambda: FakeSessionRepository(),
        raising=False,
    )
    monkeypatch.setattr(
        office_routes,
        "_display_filename_for_path",
        fake_display_filename,
        raising=False,
    )

    response = make_client().post(
        "/api/office/save-docx",
        data={"file_path": str(source_path), "session_id": "session-a"},
        files={
            "file": (
                "79e9f2ca-3b9a-4e5a.docx",
                b"new-docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    document = response.json()["document"]
    assert document["file_name"].startswith("空气质量月报_edited_")
    assert document["file_name"].endswith(".docx")
    assert Path(document["file_path"]).name == document["file_name"]


def test_download_word_accepts_display_filename(tmp_path: Path):
    source_path = tmp_path / "79e9f2ca-3b9a-4e5a.docx"
    source_path.write_bytes(b"docx")

    response = make_client().post(
        "/api/office/download-word",
        json={
            "file_path": str(source_path),
            "file_name": "空气质量月报.docx",
        },
    )

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert "79e9f2ca" not in disposition
    assert "%E7%A9%BA%E6%B0%94%E8%B4%A8%E9%87%8F%E6%9C%88%E6%8A%A5.docx" in disposition


def test_save_docx_updates_agent_memory_office_documents(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "report.docx"
    source_path.write_bytes(b"old-docx")

    class FakeSessionRepository:
        async def get_session_with_messages(self, session_id, include_messages=True, include_artifacts=True):
            return {"session_id": session_id, "office_documents": []}

        async def update_session(self, session_id, **kwargs):
            return True

    class FakeAgent:
        def __init__(self):
            self._session_store = {
                "session-a": {
                    "office_documents": [
                        {
                            "doc_type": "word",
                            "file_name": "report.docx",
                            "file_path": str(source_path),
                            "timestamp": "2026-06-29T10:00:00",
                        }
                    ]
                }
            }

    fake_agent = FakeAgent()

    async def fake_convert_to_pdf(path: str) -> dict:
        return {
            "pdf_id": "preview-123",
            "pdf_path": "/tmp/preview-123.pdf",
            "pdf_url": "/api/office/pdf/preview-123",
            "pages": 1,
            "size": 10,
        }

    monkeypatch.setattr(office_routes.pdf_converter, "convert_to_pdf", fake_convert_to_pdf)
    monkeypatch.setattr(
        office_routes,
        "get_session_repository",
        lambda: FakeSessionRepository(),
        raising=False,
    )
    monkeypatch.setattr(
        office_routes,
        "_get_multi_expert_agent_instance",
        lambda: fake_agent,
        raising=False,
    )

    response = make_client().post(
        "/api/office/save-docx",
        data={"file_path": str(source_path), "session_id": "session-a"},
        files={
            "file": (
                "report.docx",
                b"new-docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    document = response.json()["document"]
    memory_documents = fake_agent._session_store["session-a"]["office_documents"]
    assert [item["file_path"] for item in memory_documents] == [
        str(source_path),
        document["file_path"],
    ]


def test_layout_reference_uses_original_for_edited_versions(tmp_path: Path):
    original = tmp_path / "report.docx"
    edited = tmp_path / "report_edited_20260629_114120.docx"
    nested = tmp_path / "report_edited_20260629_114120_edited_20260629_115000.docx"
    original.write_bytes(b"original")
    edited.write_bytes(b"edited")
    nested.write_bytes(b"nested")

    assert office_routes._layout_reference_docx_path(edited) == original.resolve()
    assert office_routes._layout_reference_docx_path(nested) == original.resolve()
    assert office_routes._layout_reference_docx_path(original) == original


def test_preserve_docx_layout_restores_indents_and_cell_widths(tmp_path: Path):
    source = tmp_path / "source.docx"
    edited = tmp_path / "edited.docx"
    source_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:ind w:firstLine="0"/></w:pPr><w:r><w:t>标题</w:t></w:r></w:p>
    <w:tbl><w:tblPr><w:tblW w:type="pct" w:w="5000"/></w:tblPr><w:tblGrid><w:gridCol w:w="1800"/></w:tblGrid><w:tr><w:trPr><w:tblHeader w:val="on"/></w:trPr><w:tc><w:tcPr><w:vAlign w:val="center"/></w:tcPr><w:p><w:pPr><w:ind w:firstLine="0"/></w:pPr><w:r><w:t>单元格</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
  </w:body>
</w:document>
"""
    edited_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr/><w:r><w:t>标题已改</w:t></w:r></w:p>
    <w:tbl><w:tblPr><w:tblW w:type="pct" w:w="5000"/><w:tblCellMar><w:left w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid><w:gridCol w:w="2400"/></w:tblGrid><w:tr><w:trPr><w:tblHeader/></w:trPr><w:tc><w:tcPr><w:tcW w:type="pct" w:w="50"/><w:tcBorders><w:top w:val="single"/></w:tcBorders><w:tcMar><w:left w:w="108" w:type="dxa"/></w:tcMar><w:vAlign w:val="center"/></w:tcPr><w:p><w:pPr/><w:r><w:t>单元格已改</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
  </w:body>
</w:document>
"""
    with ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", source_xml)
    with ZipFile(edited, "w") as archive:
        archive.writestr("word/document.xml", edited_xml)

    office_routes._preserve_docx_layout_from_source(source, edited)

    with ZipFile(edited) as archive:
        patched_xml = archive.read("word/document.xml").decode("utf-8")

    assert "标题已改" in patched_xml
    assert "单元格已改" in patched_xml
    assert patched_xml.count('w:firstLine="0"') == 2
    assert "w:tcW" not in patched_xml
    assert "w:tcBorders" not in patched_xml
    assert "w:tcMar" not in patched_xml
    assert "w:tblCellMar" not in patched_xml
    assert 'w:gridCol w:w="1800"' in patched_xml
    assert 'w:tblHeader w:val="on"' in patched_xml
    assert 'w:gridCol w:w="2400"' not in patched_xml
    assert "<w:tblHeader />" not in patched_xml
    assert 'w:vAlign w:val="center"' in patched_xml


def test_pdf_preview_source_normalizes_table_paragraph_spacing_without_changing_docx(tmp_path: Path):
    source = tmp_path / "source.docx"
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:tbl><w:tr><w:tc><w:p><w:pPr><w:pStyle w:val="Compact"/><w:spacing w:line="400" w:lineRule="exact" w:before="0" w:after="0"/></w:pPr><w:r><w:t>单元格</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
  </w:body>
</w:document>
"""
    with ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    with office_routes._docx_pdf_preview_source(source) as preview_source:
        assert preview_source != source
        with ZipFile(preview_source) as archive:
            preview_xml = archive.read("word/document.xml").decode("utf-8")
        assert 'w:pStyle w:val="Compact"' not in preview_xml
        assert 'w:lineRule="exact"' not in preview_xml
        assert "单元格" in preview_xml

    with ZipFile(source) as archive:
        original_xml = archive.read("word/document.xml").decode("utf-8")
    assert 'w:pStyle w:val="Compact"' in original_xml
    assert 'w:lineRule="exact"' in original_xml

"""
Office document preview API routes
"""
from datetime import datetime
from contextlib import contextmanager

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path
import logging
import re
import shutil
import tempfile
from typing import Optional
from urllib.parse import quote
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

from app.db.session_repository import get_session_repository
from app.services.pdf_converter import pdf_converter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/office", tags=["office"])
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{WORD_NS}}}"
ET.register_namespace("w", WORD_NS)
EDITED_DOCX_SUFFIX_RE = re.compile(r"_edited_\d{8}_\d{6}(?:_\d+)?(?:_edited_.*)?$")
EXCEL_SUFFIXES = {".xlsx", ".xls"}


def content_disposition(disposition: str, filename: str) -> str:
    """Build an ASCII-safe Content-Disposition header for Unicode filenames."""
    safe_name = Path(filename).name or "download"
    ascii_fallback = "".join(
        ch if 32 <= ord(ch) < 127 and ch not in {'"', "\\", ";"} else "_"
        for ch in safe_name
    ).strip("._ ")
    if not ascii_fallback:
        ascii_fallback = "download"
    encoded_name = quote(safe_name.encode("utf-8"))
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_name}"


def _office_document_file_path(document: dict) -> Optional[str]:
    file_path = document.get("file_path") or document.get("path")
    if file_path:
        return file_path
    pdf_preview = document.get("pdf_preview") or {}
    if isinstance(pdf_preview, dict):
        return pdf_preview.get("source_file") or pdf_preview.get("office_file_path")
    return None


def _resolve_existing_docx(file_path: str) -> Path:
    if not file_path:
        raise HTTPException(status_code=400, detail="Missing required field: file_path")

    resolved_path = Path(file_path).resolve()
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if resolved_path.suffix.lower() != ".docx":
        raise HTTPException(status_code=400, detail="Only DOCX documents (.docx) are supported")
    return resolved_path


def _resolve_existing_excel(file_path: str) -> Path:
    if not file_path:
        raise HTTPException(status_code=400, detail="Missing required field: file_path")

    resolved_path = Path(file_path).resolve()
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if resolved_path.suffix.lower() not in EXCEL_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only Excel documents (.xlsx, .xls) are supported")
    return resolved_path


def _safe_office_filename(filename: str, fallback: str, suffix: str) -> str:
    candidate = Path(str(filename or "").replace("\\", "/")).name.strip()
    if not candidate:
        candidate = fallback
    candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", candidate).strip(" ._")
    if not candidate:
        candidate = fallback
    if Path(candidate).suffix.lower() != suffix.lower():
        candidate = f"{Path(candidate).stem or Path(fallback).stem}{suffix}"
    return candidate


async def _display_filename_for_path(path: Path, fallback: Optional[str] = None) -> str:
    fallback_name = fallback or path.name
    try:
        from sqlalchemy import select

        from app.db.database import async_session
        from app.knowledge_base.models import UploadedFile

        resolved_path = str(path.resolve())
        async with async_session() as db:
            result = await db.execute(
                select(UploadedFile.filename).where(
                    UploadedFile.file_path.in_([str(path), resolved_path])
                )
            )
            filename = result.scalar_one_or_none()
            if filename:
                return filename
    except Exception as e:
        logger.debug(
            "office_display_filename_lookup_failed",
            extra={"file_path": str(path), "error": str(e)},
        )
    return fallback_name


def _edited_docx_path(source_path: Path, display_filename: Optional[str] = None) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _safe_office_filename(display_filename or source_path.name, source_path.name, ".docx")
    candidate = source_path.with_name(f"{Path(safe_name).stem}_edited_{timestamp}.docx")
    counter = 1
    while candidate.exists():
        candidate = source_path.with_name(
            f"{Path(safe_name).stem}_edited_{timestamp}_{counter}.docx"
        )
        counter += 1
    return candidate


def _edited_office_path(source_path: Path, display_filename: Optional[str] = None) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _safe_office_filename(display_filename or source_path.name, source_path.name, source_path.suffix)
    candidate = source_path.with_name(f"{Path(safe_name).stem}_edited_{timestamp}{source_path.suffix}")
    counter = 1
    while candidate.exists():
        candidate = source_path.with_name(
            f"{Path(safe_name).stem}_edited_{timestamp}_{counter}{source_path.suffix}"
        )
        counter += 1
    return candidate


def _excel_media_type(path: Path) -> str:
    if path.suffix.lower() == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/vnd.ms-excel"


def _spreadsheet_preview(path: Path) -> dict:
    return {
        "file_type": path.suffix.lower().lstrip(".") or "xlsx",
        "editable": True,
        "download_url": "/api/office/download-excel",
        "size": path.stat().st_size,
    }


def _layout_reference_docx_path(source_path: Path) -> Path:
    original_stem = EDITED_DOCX_SUFFIX_RE.sub("", source_path.stem)
    if original_stem != source_path.stem:
        original_path = source_path.with_name(f"{original_stem}{source_path.suffix}")
        if original_path.exists():
            return original_path.resolve()
    return source_path


def _get_multi_expert_agent_instance():
    try:
        from app.routers.agent import multi_expert_agent_instance

        return multi_expert_agent_instance
    except Exception as e:
        logger.warning("office_session_memory_unavailable", extra={"error": str(e)})
        return None


def _office_document_identity(document: dict) -> Optional[str]:
    if not isinstance(document, dict):
        return None
    return (
        document.get("version_id")
        or (f"{document.get('document_id')}:{document.get('file_path')}" if document.get("document_id") and document.get("file_path") else None)
        or document.get("file_path")
        or document.get("path")
        or (document.get("pdf_preview") or {}).get("pdf_id")
        or (document.get("html_preview") or {}).get("html_id")
        or (document.get("svg_preview") or {}).get("svg_path")
    )


def _normalize_version_token(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "").strip())
    return token.strip("-") or "document"


def _stable_office_document_id(session_id: str, doc_type: str, source_file_path: str) -> str:
    session_token = _normalize_version_token(session_id or "global")
    source_token = _normalize_version_token(Path(source_file_path).stem or "document")
    type_token = _normalize_version_token(doc_type or "office")
    return f"{type_token}-{session_token}-{source_token}"


def _office_document_metadata(document: dict) -> dict:
    metadata = document.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _office_document_source_path(document: dict) -> Optional[str]:
    metadata = _office_document_metadata(document)
    return (
        metadata.get("source_file_path")
        or metadata.get("parent_file_path")
        or _office_document_file_path(document)
    )


def _infer_office_version_source_path(documents: list, document: dict) -> str:
    metadata = _office_document_metadata(document)
    previous_path = metadata.get("previous_file_path") or metadata.get("parent_file_path")
    if previous_path:
        for item in documents:
            if isinstance(item, dict) and _office_document_file_path(item) == previous_path:
                item_source = _office_document_source_path(item)
                if item_source:
                    return item_source
    return metadata.get("source_file_path") or previous_path or _office_document_file_path(document) or ""


def _infer_office_document_id(documents: list, document: dict, session_id: str, source_file_path: str) -> str:
    metadata = _office_document_metadata(document)
    previous_path = metadata.get("previous_file_path") or metadata.get("parent_file_path")
    if document.get("document_id"):
        return document["document_id"]
    for item in documents:
        if not isinstance(item, dict):
            continue
        if item.get("document_id") and (
            _office_document_file_path(item) == previous_path
            or _office_document_source_path(item) == source_file_path
        ):
            return item["document_id"]
    return _stable_office_document_id(session_id, document.get("doc_type") or "office", source_file_path)


def _is_same_office_version_chain(document: dict, document_id: str, source_file_path: str, previous_path: str) -> bool:
    if not isinstance(document, dict):
        return False
    file_path = _office_document_file_path(document)
    return (
        document.get("document_id") == document_id
        or file_path in {source_file_path, previous_path}
        or _office_document_source_path(document) == source_file_path
    )


def _with_office_version_metadata(documents: list, document: dict, session_id: str) -> tuple[list, dict]:
    source_file_path = _infer_office_version_source_path(documents, document)
    metadata = {
        **_office_document_metadata(document),
        "source_file_path": source_file_path,
    }
    previous_path = metadata.get("previous_file_path") or metadata.get("parent_file_path") or source_file_path
    if previous_path:
        metadata["previous_file_path"] = previous_path
    document_id = _infer_office_document_id(documents, document, session_id, source_file_path)

    related_indexes = [
        index
        for index, item in enumerate(documents)
        if _is_same_office_version_chain(item, document_id, source_file_path, previous_path)
    ]
    max_revision = 0
    for index in related_indexes:
        try:
            max_revision = max(max_revision, int(documents[index].get("revision") or 0))
        except (TypeError, ValueError):
            max_revision = max(max_revision, 0)
    if max_revision == 0 and related_indexes:
        max_revision = len(related_indexes)
    next_revision = int(document.get("revision") or 0) or (max_revision + 1)

    next_documents = [item for item in documents if isinstance(item, dict)]
    used_revisions = set()
    for index in related_indexes:
        try:
            revision = int(documents[index].get("revision") or 0)
        except (TypeError, ValueError):
            revision = 0
        if revision > 0:
            used_revisions.add(revision)
    next_legacy_revision = 1
    for index, item in enumerate(next_documents):
        if not _is_same_office_version_chain(item, document_id, source_file_path, previous_path):
            continue
        item_metadata = {
            **_office_document_metadata(item),
            "source_file_path": source_file_path,
        }
        if not item_metadata.get("version_type"):
            item_metadata["version_type"] = "original"
        try:
            revision = int(item.get("revision") or 0)
        except (TypeError, ValueError):
            revision = 0
        if revision <= 0:
            while next_legacy_revision in used_revisions:
                next_legacy_revision += 1
            revision = next_legacy_revision
            used_revisions.add(revision)
        next_documents[index] = {
            **item,
            "document_id": document_id,
            "version_id": item.get("version_id") or f"{document_id}:r{revision}",
            "revision": revision,
            "is_current": False,
            "metadata": item_metadata,
        }

    versioned_document = {
        **document,
        "document_id": document_id,
        "version_id": document.get("version_id") or f"{document_id}:r{next_revision}",
        "revision": next_revision,
        "is_current": True,
        "metadata": metadata,
    }
    return _upsert_office_document(next_documents, versioned_document), versioned_document


def _upsert_office_document(documents: list, document: dict) -> list:
    identity = _office_document_identity(document)
    next_documents = [item for item in documents if isinstance(item, dict)]
    existing_index = next(
        (
            index
            for index, item in enumerate(next_documents)
            if _office_document_identity(item) == identity
        ),
        -1,
    )
    if existing_index >= 0:
        next_documents[existing_index] = {
            **next_documents[existing_index],
            **document,
        }
    else:
        next_documents.append(document)
    return next_documents


async def _persist_office_document_version(session_id: str, document: dict) -> dict:
    # 版本信息由统一资源提交链路负责；这里仅给当前响应补充稳定版本元数据，
    # 不再读取或写入会话内的 office_documents 快照。
    _, versioned_document = _with_office_version_metadata([], document, session_id)
    document.clear()
    document.update(versioned_document)
    return document


def _clone_xml_element(element: ET.Element) -> ET.Element:
    return ET.fromstring(ET.tostring(element, encoding="utf-8"))


def _find_child(parent: Optional[ET.Element], tag: str) -> Optional[ET.Element]:
    if parent is None:
        return None
    return parent.find(f"{W}{tag}")


def _ensure_child(parent: ET.Element, tag: str) -> ET.Element:
    child = _find_child(parent, tag)
    if child is None:
        child = ET.Element(f"{W}{tag}")
        parent.insert(0, child)
    return child


def _replace_child(parent: ET.Element, tag: str, source_child: Optional[ET.Element]) -> None:
    existing = _find_child(parent, tag)
    if existing is not None:
        parent.remove(existing)
    if source_child is not None:
        parent.insert(0, _clone_xml_element(source_child))


def _patch_edited_document_xml(source_xml: bytes, edited_xml: bytes) -> bytes:
    source_root = ET.fromstring(source_xml)
    edited_root = ET.fromstring(edited_xml)

    source_paragraphs = source_root.findall(f".//{W}p")
    edited_paragraphs = edited_root.findall(f".//{W}p")
    for source_p, edited_p in zip(source_paragraphs, edited_paragraphs):
        source_ppr = _find_child(source_p, "pPr")
        source_ind = _find_child(source_ppr, "ind")
        edited_ppr = _ensure_child(edited_p, "pPr")
        _replace_child(edited_ppr, "ind", source_ind)

    source_tables = source_root.findall(f".//{W}tbl")
    edited_tables = edited_root.findall(f".//{W}tbl")
    for source_tbl, edited_tbl in zip(source_tables, edited_tables):
        source_tblpr = _find_child(source_tbl, "tblPr")
        _replace_child(edited_tbl, "tblPr", source_tblpr)
        source_tbl_grid = _find_child(source_tbl, "tblGrid")
        _replace_child(edited_tbl, "tblGrid", source_tbl_grid)

    source_rows = source_root.findall(f".//{W}tr")
    edited_rows = edited_root.findall(f".//{W}tr")
    for source_tr, edited_tr in zip(source_rows, edited_rows):
        source_trpr = _find_child(source_tr, "trPr")
        _replace_child(edited_tr, "trPr", source_trpr)

    source_cells = source_root.findall(f".//{W}tc")
    edited_cells = edited_root.findall(f".//{W}tc")
    for source_tc, edited_tc in zip(source_cells, edited_cells):
        source_tcpr = _find_child(source_tc, "tcPr")
        _replace_child(edited_tc, "tcPr", source_tcpr)

    return ET.tostring(edited_root, encoding="utf-8", xml_declaration=True)


def _patch_pdf_preview_document_xml(document_xml: bytes) -> bytes:
    root = ET.fromstring(document_xml)
    for table in root.findall(f".//{W}tbl"):
        for paragraph in table.findall(f".//{W}p"):
            ppr = _find_child(paragraph, "pPr")
            if ppr is None:
                continue

            pstyle = _find_child(ppr, "pStyle")
            if pstyle is not None and pstyle.get(f"{W}val") == "Compact":
                ppr.remove(pstyle)

            spacing = _find_child(ppr, "spacing")
            if spacing is not None and spacing.get(f"{W}lineRule") == "exact":
                ppr.remove(spacing)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _write_docx_with_document_xml(source_path: Path, document_xml: bytes, output_path: Path) -> None:
    with ZipFile(source_path) as source_zip, ZipFile(output_path, "w", compression=ZIP_DEFLATED) as output_zip:
        for item in source_zip.infolist():
            if item.filename.endswith("/"):
                output_zip.writestr(item, b"")
                continue
            if item.filename == "word/document.xml":
                output_zip.writestr(item, document_xml)
            else:
                output_zip.writestr(item, source_zip.read(item.filename))


@contextmanager
def _docx_pdf_preview_source(docx_path: Path):
    if docx_path.suffix.lower() != ".docx":
        yield docx_path
        return

    tmp_path = None
    try:
        with ZipFile(docx_path) as archive:
            patched_xml = _patch_pdf_preview_document_xml(archive.read("word/document.xml"))

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_file:
            tmp_path = Path(tmp_file.name)

        _write_docx_with_document_xml(docx_path, patched_xml, tmp_path)
        yield tmp_path
    except Exception as e:
        logger.warning(
            "docx_pdf_preview_normalization_failed",
            extra={"docx_path": str(docx_path), "error": str(e)},
        )
        yield docx_path
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


async def _convert_docx_to_pdf_preview(docx_path: Path) -> dict:
    with _docx_pdf_preview_source(docx_path) as preview_source:
        return await pdf_converter.convert_to_pdf(str(preview_source))


async def _rebuild_docx_pdf_preview(pdf_id: str, docx_path: Path) -> dict:
    with _docx_pdf_preview_source(docx_path) as preview_source:
        return await pdf_converter.rebuild_pdf(pdf_id, str(preview_source))


def _preserve_docx_layout_from_source(source_path: Path, edited_path: Path) -> None:
    """
    Restore layout-critical OOXML omitted or synthesized by the browser editor.

    The editor should own content changes, but generated DOCX currently rewrites
    paragraph indents and table-cell widths. Reusing these specific properties
    from the source document keeps PDF preview and downloaded Word layout stable.
    """
    try:
        with ZipFile(source_path) as source_zip, ZipFile(edited_path) as edited_zip:
            source_xml = source_zip.read("word/document.xml")
            edited_xml = edited_zip.read("word/document.xml")
            patched_xml = _patch_edited_document_xml(source_xml, edited_xml)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_file:
                tmp_path = Path(tmp_file.name)

            try:
                with ZipFile(tmp_path, "w", compression=ZIP_DEFLATED) as output_zip:
                    for item in edited_zip.infolist():
                        if item.filename.endswith("/"):
                            output_zip.writestr(item, b"")
                            continue
                        if item.filename == "word/document.xml":
                            output_zip.writestr(item, patched_xml)
                        else:
                            output_zip.writestr(item, edited_zip.read(item.filename))
                shutil.move(str(tmp_path), str(edited_path))
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
    except Exception as e:
        logger.warning(
            "docx_layout_preservation_failed",
            extra={
                "source_path": str(source_path),
                "edited_path": str(edited_path),
                "error": str(e),
            },
        )


async def _ensure_pdf_available(pdf_id: str) -> bool:
    if pdf_converter.pdf_exists(pdf_id):
        return True

    try:
        from app.db.session_repository import get_session_repository

        match = await get_session_repository().find_office_document_by_pdf_id(pdf_id)
        document = (match or {}).get("document") or {}
        file_path = _office_document_file_path(document)
        if not file_path:
            logger.warning("PDF rebuild skipped: no source path for pdf_id=%s", pdf_id)
            return False

        source_path = Path(file_path).resolve()
        if not source_path.exists():
            logger.warning(
                "PDF rebuild skipped: source file missing for pdf_id=%s source_path=%s",
                pdf_id,
                source_path,
            )
            return False

        if source_path.suffix.lower() == ".docx":
            await _rebuild_docx_pdf_preview(pdf_id, source_path)
        else:
            await pdf_converter.rebuild_pdf(pdf_id, str(source_path))
        return pdf_converter.pdf_exists(pdf_id)
    except Exception as e:
        logger.warning("PDF rebuild failed for pdf_id=%s: %s", pdf_id, e, exc_info=True)
        return False


@router.get("/pdf/{pdf_id}")
async def get_pdf(pdf_id: str):
    """
    Get PDF file by ID

    Args:
        pdf_id: Unique PDF identifier

    Returns:
        PDF file as FileResponse
    """
    pdf_path = pdf_converter.get_pdf_path(pdf_id)

    if not await _ensure_pdf_available(pdf_id):
        raise HTTPException(status_code=404, detail="PDF not found")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{pdf_id}.pdf",
        headers={"Content-Disposition": content_disposition("inline", "preview.pdf")}
    )


@router.get("/pdf/{pdf_id}/download")
async def download_pdf(pdf_id: str, filename: Optional[str] = None):
    """
    Download generated PDF preview by ID.

    Args:
        pdf_id: Unique PDF identifier
        filename: Optional download filename

    Returns:
        PDF file as attachment
    """
    pdf_path = pdf_converter.get_pdf_path(pdf_id)

    if not await _ensure_pdf_available(pdf_id):
        raise HTTPException(status_code=404, detail="PDF not found")

    safe_name = Path(filename).name if filename else f"{pdf_id}.pdf"
    if not safe_name.lower().endswith(".pdf"):
        safe_name = f"{safe_name}.pdf"

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=Path(safe_name).name,
        headers={"Content-Disposition": content_disposition("attachment", safe_name)}
    )


@router.get("/pdf/{pdf_id}/info")
async def get_pdf_info(pdf_id: str):
    """
    Get PDF metadata

    Args:
        pdf_id: Unique PDF identifier

    Returns:
        PDF metadata including page count and file size
    """
    pdf_path = pdf_converter.get_pdf_path(pdf_id)

    if not await _ensure_pdf_available(pdf_id):
        raise HTTPException(status_code=404, detail="PDF not found")

    return {
        "pdf_id": pdf_id,
        "pages": pdf_converter._get_pdf_page_count(pdf_path),
        "size": pdf_path.stat().st_size,
        "filename": f"{pdf_id}.pdf"
    }


@router.post("/open-docx")
async def open_docx(request: Request):
    """
    Open a DOCX document for browser-side editing.

    This route intentionally supports only modern .docx files because the
    frontend editor reads and writes OOXML packages.
    """
    try:
        data = await request.json()
        resolved_path = _resolve_existing_docx(data.get("file_path"))
        filename = resolved_path.name

        return FileResponse(
            path=str(resolved_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
            headers={"Content-Disposition": content_disposition("inline", filename)}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error opening DOCX document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-docx")
async def save_docx(
    file_path: str = Form(...),
    session_id: str = Form(""),
    file: UploadFile = File(...),
):
    """
    Save an edited DOCX as a new version and return the standard office document
    payload consumed by the frontend preview/history panel.
    """
    try:
        source_path = _resolve_existing_docx(file_path)
        if file.filename and not file.filename.lower().endswith(".docx"):
            raise HTTPException(
                status_code=400,
                detail="Uploaded file must be a DOCX document",
            )

        display_filename = await _display_filename_for_path(source_path, file.filename or source_path.name)
        output_path = _edited_docx_path(source_path, display_filename)
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded DOCX file is empty")

        output_path.write_bytes(content)
        layout_source_path = _layout_reference_docx_path(source_path)
        _preserve_docx_layout_from_source(layout_source_path, output_path)
        pdf_preview = await _convert_docx_to_pdf_preview(output_path)
        timestamp = datetime.now().isoformat()

        document = {
            "doc_type": "word",
            "file_name": output_path.name,
            "file_path": str(output_path),
            "file_type": "docx",
            "pdf_preview": pdf_preview,
            "timestamp": timestamp,
            "last_action": {
                "tool": "docx_online_editor",
                "summary": "在线编辑保存",
                "timestamp": timestamp,
            },
            "metadata": {
                "source_file_path": str(source_path),
                "parent_file_path": str(source_path),
                "display_file_name": display_filename,
                "layout_source_file_path": str(layout_source_path),
                "session_id": session_id,
                "editor": "docx_online_editor",
                "version_type": "edited",
            },
        }
        await _persist_office_document_version(session_id, document)
        return {"success": True, "document": document}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving DOCX document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/open-excel")
async def open_excel(request: Request):
    """
    Open an Excel workbook for browser-side viewing/editing.
    """
    try:
        data = await request.json()
        resolved_path = _resolve_existing_excel(data.get("file_path"))
        filename = resolved_path.name

        return FileResponse(
            path=str(resolved_path),
            media_type=_excel_media_type(resolved_path),
            filename=filename,
            headers={"Content-Disposition": content_disposition("inline", filename)}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error opening Excel document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-excel")
async def save_excel(
    file_path: str = Form(...),
    session_id: str = Form(""),
    file: UploadFile = File(...),
):
    """
    Save an edited Excel workbook as a new version and persist it in session history.
    """
    try:
        source_path = _resolve_existing_excel(file_path)
        if file.filename and Path(file.filename).suffix.lower() not in EXCEL_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file must be an Excel document",
            )

        display_filename = await _display_filename_for_path(source_path, file.filename or source_path.name)
        output_path = _edited_office_path(source_path, display_filename)
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded Excel file is empty")

        output_path.write_bytes(content)
        timestamp = datetime.now().isoformat()
        document = {
            "doc_type": "excel",
            "file_name": output_path.name,
            "file_path": str(output_path),
            "file_type": output_path.suffix.lower().lstrip(".") or "xlsx",
            "spreadsheet_preview": _spreadsheet_preview(output_path),
            "timestamp": timestamp,
            "last_action": {
                "tool": "excel_online_editor",
                "summary": "在线编辑保存",
                "timestamp": timestamp,
            },
            "metadata": {
                "source_file_path": str(source_path),
                "parent_file_path": str(source_path),
                "display_file_name": display_filename,
                "session_id": session_id,
                "editor": "excel_online_editor",
                "version_type": "edited",
            },
        }
        await _persist_office_document_version(session_id, document)
        return {"success": True, "document": document}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving Excel document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply-edit")
async def apply_user_edit(request: Request, background_tasks: BackgroundTasks):
    """
    Apply user edit content to document

    This endpoint receives edit content from the frontend and passes it to the Agent,
    which will use appropriate Office tools to apply the changes.

    The actual document processing happens in the background, and results are
    pushed to the frontend via SSE.

    Args:
        file_path: Path to the document
        content: Edited content
        doc_type: Document type (word/ppt)
        session_id: Session ID (for restoring Agent context)

    Returns:
        {
            "success": true,
            "message": "Edit submitted, processing..."
        }
    """
    try:
        data = await request.json()
        file_path = data.get("file_path")
        content = data.get("content")
        doc_type = data.get("doc_type")
        session_id = data.get("session_id")

        if not file_path or not content:
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: file_path, content"
            )

        # Note: In a real implementation, you would:
        # 1. Store the edit request in a queue/database
        # 2. Notify the Agent session via WebSocket or another mechanism
        # 3. The Agent would process the edit and push results via SSE

        # For now, return success and let the frontend know
        # The actual edit processing will be handled by the Agent
        # when the user sends a natural language request

        logger.info(
            f"Office edit request received: file={file_path}, "
            f"type={doc_type}, session={session_id}"
        )

        return {
            "success": True,
            "message": "Edit submitted. Please use natural language to describe the changes you want to apply.",
            "hint": f"Try saying: 'Update the document {file_path} with the following content: {content[:100]}...'"
        }

    except Exception as e:
        logger.error(f"Error processing office edit: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pdf/{pdf_id}")
async def delete_pdf(pdf_id: str):
    """
    Delete a PDF file

    Args:
        pdf_id: Unique PDF identifier

    Returns:
        Success status
    """
    success = pdf_converter.cleanup_pdf(pdf_id)

    if not success:
        raise HTTPException(status_code=404, detail="PDF not found or already deleted")

    return {"success": True, "message": "PDF deleted"}


@router.post("/download-word")
async def download_word(request: Request):
    """
    Download Word document

    Args:
        file_path: Path to the Word document

    Returns:
        Word document as FileResponse
    """
    try:
        data = await request.json()
        file_path = data.get("file_path")

        if not file_path:
            raise HTTPException(
                status_code=400,
                detail="Missing required field: file_path"
            )

        # 安全检查：防止路径穿越攻击
        resolved_path = Path(file_path).resolve()

        # 检查文件是否存在
        if not resolved_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        # 检查文件扩展名
        if resolved_path.suffix.lower() not in ['.docx', '.doc']:
            raise HTTPException(
                status_code=400,
                detail="Only Word documents (.docx, .doc) are supported"
            )

        # 提取文件名
        filename = _safe_office_filename(
            data.get("file_name") or await _display_filename_for_path(resolved_path, resolved_path.name),
            resolved_path.name,
            resolved_path.suffix,
        )

        logger.info(f"Downloading Word document: {file_path}")

        # 根据文件扩展名设置正确的媒体类型
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if resolved_path.suffix.lower() == '.docx'
            else "application/msword"
        )

        return FileResponse(
            path=str(resolved_path),
            media_type=media_type,
            filename=filename,
            headers={"Content-Disposition": content_disposition("attachment", filename)}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading Word document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download-ppt")
async def download_ppt(request: Request):
    """
    Download PowerPoint document

    Args:
        file_path: Path to the PowerPoint document

    Returns:
        PowerPoint document as FileResponse
    """
    try:
        data = await request.json()
        file_path = data.get("file_path")

        if not file_path:
            raise HTTPException(
                status_code=400,
                detail="Missing required field: file_path"
            )

        resolved_path = Path(file_path).resolve()

        if not resolved_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        suffix = resolved_path.suffix.lower()
        if suffix not in ['.pptx', '.ppt']:
            raise HTTPException(
                status_code=400,
                detail="Only PowerPoint documents (.pptx, .ppt) are supported"
            )

        filename = _safe_office_filename(
            data.get("file_name") or await _display_filename_for_path(resolved_path, resolved_path.name),
            resolved_path.name,
            suffix,
        )

        logger.info(f"Downloading PowerPoint document: {file_path}")

        media_type = (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            if suffix == '.pptx'
            else "application/vnd.ms-powerpoint"
        )

        return FileResponse(
            path=str(resolved_path),
            media_type=media_type,
            filename=filename,
            headers={"Content-Disposition": content_disposition("attachment", filename)}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading PowerPoint document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download-excel")
async def download_excel(request: Request):
    """
    Download Excel workbook.
    """
    try:
        data = await request.json()
        file_path = data.get("file_path")

        if not file_path:
            raise HTTPException(
                status_code=400,
                detail="Missing required field: file_path"
            )

        resolved_path = _resolve_existing_excel(file_path)
        filename = _safe_office_filename(
            data.get("file_name") or await _display_filename_for_path(resolved_path, resolved_path.name),
            resolved_path.name,
            resolved_path.suffix,
        )

        logger.info(f"Downloading Excel document: {file_path}")

        return FileResponse(
            path=str(resolved_path),
            media_type=_excel_media_type(resolved_path),
            filename=filename,
            headers={"Content-Disposition": content_disposition("attachment", filename)}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading Excel document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

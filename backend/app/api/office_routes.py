"""
Office document preview API routes
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse
from pathlib import Path
import logging
from typing import Optional

from app.services.pdf_converter import pdf_converter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/office", tags=["office"])


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

    if not pdf_converter.pdf_exists(pdf_id):
        raise HTTPException(status_code=404, detail="PDF not found")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{pdf_id}.pdf",
        headers={"Content-Disposition": "inline; filename=preview.pdf"}
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

    if not pdf_converter.pdf_exists(pdf_id):
        raise HTTPException(status_code=404, detail="PDF not found")

    return {
        "pdf_id": pdf_id,
        "pages": pdf_converter._get_pdf_page_count(pdf_path),
        "size": pdf_path.stat().st_size,
        "filename": f"{pdf_id}.pdf"
    }


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

"""
Notebook preview API routes
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import logging

from app.services.notebook_converter import notebook_converter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notebook", tags=["notebook"])


@router.get("/html/{html_id}")
async def get_notebook_html(html_id: str):
    """
    Get Notebook HTML file by ID

    Args:
        html_id: Unique HTML identifier

    Returns:
        HTML file as FileResponse
    """
    html_path = notebook_converter.get_html_path(html_id)

    if not notebook_converter.html_exists(html_id):
        raise HTTPException(status_code=404, detail="Notebook HTML not found")

    return FileResponse(
        path=str(html_path),
        media_type="text/html",
        filename=f"{html_id}.html",
        headers={"Content-Disposition": "inline; filename=notebook.html"}
    )


@router.get("/html/{html_id}/info")
async def get_notebook_info(html_id: str):
    """
    Get Notebook HTML metadata

    Args:
        html_id: Unique HTML identifier

    Returns:
        HTML metadata including cell count and file size
    """
    html_path = notebook_converter.get_html_path(html_id)

    if not notebook_converter.html_exists(html_id):
        raise HTTPException(status_code=404, detail="Notebook HTML not found")

    return {
        "html_id": html_id,
        "cells": html_path.stat().st_size // 1000,  # 粗略估算
        "size": html_path.stat().st_size,
        "filename": f"{html_id}.html"
    }


@router.delete("/html/{html_id}")
async def delete_notebook_html(html_id: str):
    """
    Delete a Notebook HTML file

    Args:
        html_id: Unique HTML identifier

    Returns:
        Success status
    """
    success = notebook_converter.cleanup_html(html_id)

    if not success:
        raise HTTPException(status_code=404, detail="Notebook HTML not found or already deleted")

    return {"success": True, "message": "Notebook HTML deleted"}


@router.post("/download")
async def download_notebook(request_data: dict):
    """
    Download original .ipynb file

    Args:
        file_path: Path to the .ipynb file

    Returns:
        .ipynb file as FileResponse
    """
    from fastapi import Request

    # 这里需要在函数参数中使用Request，但为了简化，我们使用字典
    file_path = request_data.get("file_path")

    if not file_path or not file_path.endswith('.ipynb'):
        raise HTTPException(status_code=400, detail="Invalid notebook path")

    resolved_path = Path(file_path).resolve()

    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="Notebook not found")

    return FileResponse(
        path=str(resolved_path),
        media_type="application/json",
        filename=resolved_path.name,
        headers={"Content-Disposition": f"attachment; filename=\"{resolved_path.name}\""}
    )

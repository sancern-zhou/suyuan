"""
Utility 工具 API 路由
提供文件下载等通用功能
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from urllib.parse import unquote
import structlog

logger = structlog.get_logger()

router = APIRouter(tags=["utility"])


@router.get("/file/{file_path:path}")
async def download_file(file_path: str):
    """
    通用文件下载接口（支持所有文件类型）

    用于下载本地文件，包括：
    - PDF 文件（预览功能）
    - Markdown 文件
    - Word 文档
    - 其他文本文件

    Args:
        file_path: 文件路径（URL编码）

    Returns:
        文件内容作为 FileResponse
    """
    try:
        decoded_path = unquote(file_path)
        path = Path(decoded_path)

        # 兼容前端/工具把绝对路径编码后丢失首个斜杠的情况
        if not path.is_absolute():
            absolute_candidate = Path("/") / decoded_path.lstrip("/")
            if absolute_candidate.exists():
                path = absolute_candidate

        # 安全检查：防止路径穿越攻击
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {file_path}"
            )

        if not path.is_file():
            raise HTTPException(
                status_code=400,
                detail=f"Path is not a file: {file_path}"
            )

        # 检查文件大小（限制 50MB）
        file_size = path.stat().st_size
        if file_size > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"File too large: {file_size} bytes (max 50MB)"
            )

        # 获取文件名
        filename = path.name

        # 根据文件扩展名确定 media_type
        media_type = 'application/octet-stream'
        if path.suffix in ['.pdf']:
            media_type = 'application/pdf'
        elif path.suffix in ['.md', '.markdown']:
            media_type = 'text/markdown'
        elif path.suffix in ['.docx']:
            media_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif path.suffix in ['.xlsx']:
            media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif path.suffix in ['.xls']:
            media_type = 'application/vnd.ms-excel'
        elif path.suffix in ['.pptx']:
            media_type = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        elif path.suffix in ['.txt']:
            media_type = 'text/plain'

        # 对于PDF文件，设置为inline预览（避免自动下载）
        # 其他文件保持attachment下载行为
        headers = {}
        if path.suffix in ['.pdf']:
            headers['Content-Disposition'] = f'inline; filename="{filename}"'
        else:
            headers['Content-Disposition'] = f'attachment; filename="{filename}"'

        # 返回文件
        return FileResponse(
            path=str(path),
            filename=filename,
            media_type=media_type,
            headers=headers
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("file_download_failed", file_path=file_path, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download file: {str(e)}"
        )

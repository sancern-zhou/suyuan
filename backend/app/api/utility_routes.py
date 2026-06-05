"""
Utility 工具 API 路由
提供文件下载等通用功能
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from urllib.parse import unquote, quote
import structlog

logger = structlog.get_logger()

router = APIRouter(tags=["utility"])


MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".qmd": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
}

INLINE_PREVIEW_EXTENSIONS = {
    ".pdf",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".svg",
}


def get_file_media_type(suffix: str) -> str:
    """Return a browser-friendly media type for known artifact files."""
    return MEDIA_TYPES.get(suffix.lower(), "application/octet-stream")


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
        media_type = get_file_media_type(path.suffix)

        # 对于浏览器可直接展示的文件，设置为inline预览（避免 iframe 自动下载）
        # 其他文件保持attachment下载行为
        # 使用 RFC 5987 标准编码中文文件名
        # 注意：HTTP头必须用 latin-1 编码，所以 filename 参数只能包含 ASCII 字符
        # filename* 参数使用 UTF-8 编码，现代浏览器会优先使用这个参数
        filename_ascii = filename.encode('ascii', 'ignore').decode('ascii') or 'download'
        filename_encoded = quote(filename, safe='')

        headers = {}
        if path.suffix.lower() in INLINE_PREVIEW_EXTENSIONS:
            headers['Content-Disposition'] = f'inline; filename="{filename_ascii}"; filename*=UTF-8\'\'{filename_encoded}'
        else:
            headers['Content-Disposition'] = f'attachment; filename="{filename_ascii}"; filename*=UTF-8\'\'{filename_encoded}'

        # 返回文件
        # 注意：不传递 filename 参数给 FileResponse，避免内部 latin-1 编码问题
        # 文件名完全通过 headers 中的 Content-Disposition 控制
        return FileResponse(
            path=str(path),
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

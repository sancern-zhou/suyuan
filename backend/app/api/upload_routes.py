"""
文件上传API - 对话文件和图片上传

提供以下接口：
- POST /api/upload/chat - 上传文件用于对话
- GET /api/upload/{file_id} - 获取上传文件
- DELETE /api/upload/{file_id} - 删除上传文件
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from fastapi.responses import FileResponse, Response
from typing import Optional, List
import os
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.database import get_db
from app.knowledge_base.models import UploadedFile

logger = structlog.get_logger()

router = APIRouter()

# 获取API基础URL（用于返回完整URL给LLM）
def get_api_base_url(request: Request) -> str:
    """从请求中获取API基础URL"""
    # 优先使用环境变量配置
    env_base_url = os.getenv("API_BASE_URL")
    if env_base_url:
        return env_base_url.rstrip("/")

    # 否则从请求头构建
    host = request.headers.get("host", "localhost:8000")
    scheme = request.url.scheme
    return f"{scheme}://{host}"

# 配置
# 使用项目根目录的绝对路径（确保工具可以访问）
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # 从 backend/app/api/upload_routes.py 回到项目根目录
UPLOAD_STORAGE_DIR = os.getenv("UPLOAD_STORAGE_DIR", str(_PROJECT_ROOT / "backend_data_registry" / "uploads"))
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024  # 50MB

# 支持的文件类型
IMAGE_TYPES = {
    "image/png", "image/jpeg", "image/jpg", "image/gif",
    "image/bmp", "image/webp"
}
DOCUMENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/json",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
}


def get_file_category(mime_type: str, filename: str = None) -> str:
    """获取文件分类（image 或 document）

    优先使用 MIME 类型，如果 MIME 类型未知则使用文件扩展名
    """
    if mime_type in IMAGE_TYPES:
        return "image"
    elif mime_type in DOCUMENT_TYPES:
        return "document"

    # MIME 类型未知时，尝试通过文件扩展名判断
    if filename:
        ext = Path(filename).suffix.lower()
        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
        if ext in image_extensions:
            return "image"
        # 其他允许的扩展名都视为文档
        return "document"

    return "unknown"


def validate_file_type(filename: str, content_type: str) -> tuple[bool, str]:
    """验证文件类型

    优先使用文件扩展名判断，因为很多文件的MIME类型在不同系统上不一致
    例如：.md文件可能被识别为 text/markdown、text/plain 或 application/octet-stream

    Returns:
        (is_valid, error_message)
    """
    # 检查文件扩展名（主要验证方式）
    ext = Path(filename).suffix.lower()
    allowed_extensions = {
        # 图片
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
        # 文档
        ".pdf", ".txt", ".md", ".markdown", ".json", ".csv",
        # Office
        ".docx", ".xlsx", ".pptx"
    }

    if ext not in allowed_extensions:
        return False, f"不支持的文件扩展名: {ext}"

    # MIME 类型仅作为辅助检查，如果是 application/octet-stream 则忽略
    # 因为很多合法文件会被系统识别为此类型
    if content_type and content_type != "application/octet-stream":
        file_category = get_file_category(content_type)
        # 如果 MIME 类型明确指出是未知类型（且不是 octet-stream），则拒绝
        if file_category == "unknown":
            # 但扩展名是允许的，所以仍然接受
            pass

    return True, ""


def get_max_size(content_type: str, filename: str = None) -> int:
    """根据文件类型获取最大允许大小"""
    if get_file_category(content_type, filename) == "image":
        return MAX_IMAGE_SIZE
    return MAX_DOCUMENT_SIZE


@router.post("/chat")
async def upload_chat_file(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """上传文件用于对话

    支持的文件类型：
    - 图片: PNG, JPG, JPEG, GIF, BMP, WEBP (最大 5MB)
    - 文档: PDF, TXT, MD, JSON, CSV, DOCX, XLSX, PPTX (最大 50MB)

    Args:
        file: 上传的文件
        session_id: 可选的会话ID，用于关联文件与特定对话

    Returns:
        {
            "file_id": "uuid",
            "filename": "原始文件名",
            "file_type": "image|document",
            "mime_type": "image/png",
            "file_size": 12345,
            "url": "/api/upload/{file_id}",
            "upload_time": "2024-03-10T12:00:00"
        }
    """
    # 添加调试日志
    logger.info("upload_chat_file_called",
                filename=file.filename,
                content_type=file.content_type,
                session_id=session_id)

    # 验证文件类型
    is_valid, error_msg = validate_file_type(file.filename or "", file.content_type or "")
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # 检查文件大小
    max_size = get_max_size(file.content_type or "", file.filename or "")
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > max_size:
        max_mb = max_size // 1024 // 1024
        raise HTTPException(
            status_code=400,
            detail=f"文件过大。最大允许 {max_mb}MB"
        )

    # 生成文件ID（用于数据库记录）
    file_id = str(uuid.uuid4())

    # 确保存储目录存在
    os.makedirs(UPLOAD_STORAGE_DIR, exist_ok=True)

    # 清理文件名：移除特殊字符，保留中文、字母、数字、点、下划线、连字符
    import re
    original_filename = file.filename or "unnamed"
    # 提取文件扩展名
    file_ext = Path(original_filename).suffix
    # 清理基础文件名（移除路径分隔符等危险字符）
    safe_filename_base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', original_filename)
    if not safe_filename_base:
        safe_filename_base = "unnamed"
    # 使用 file_id + 扩展名保存，避免文件名冲突
    safe_filename = f"{file_id}{file_ext}" if file_ext else file_id
    file_path = os.path.join(UPLOAD_STORAGE_DIR, safe_filename)

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        logger.error("file_save_failed", file_id=file_id, filename=original_filename, error=str(e))
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 保存文件元信息到数据库
    file_category = get_file_category(file.content_type or "", file.filename or "")

    # 文件的绝对路径（用于工具访问）
    file_path_abs = os.path.abspath(file_path)

    uploaded_file = UploadedFile(
        id=file_id,
        filename=file.filename or "unnamed",
        file_path=file_path,
        file_type=file_category,
        mime_type=file.content_type or "application/octet-stream",
        file_size=file_size,
        session_id=session_id
    )

    try:
        db.add(uploaded_file)
        await db.commit()
        await db.refresh(uploaded_file)
    except Exception as e:
        logger.error("database_save_failed", file_id=file_id, error=str(e))
        # 如果数据库保存失败，删除已保存的文件
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"数据库保存失败: {e}")

    logger.info(
        "file_uploaded",
        file_id=file_id,
        filename=file.filename,
        file_type=file_category,
        file_size=file_size
    )

    # 根据文件类型返回不同格式的URL
    # 图片：返回完整HTTP URL（用于前端显示和analyze_image工具）
    # 文档：返回本地文件的绝对路径（工具直接使用，无需解析）
    if file_category == "image":
        # 图片返回完整HTTP URL
        api_base = get_api_base_url(request) if request else "http://localhost:8000"
        file_url = f"{api_base}/api/upload/{file_id}"
    else:
        # 文档返回绝对路径（简单直接，LLM无需理解相对路径概念）
        file_url = file_path_abs

    return {
        "file_id": file_id,
        "filename": file.filename or "unnamed",
        "file_type": file_category,
        "mime_type": file.content_type or "application/octet-stream",
        "file_size": file_size,
        "url": file_url,
        "upload_time": uploaded_file.created_at.isoformat()
    }


@router.get("/{file_id}")
async def get_uploaded_file(file_id: str, db: AsyncSession = Depends(get_db)):
    """获取上传的文件

    对于图片文件，直接返回图片数据
    对于文档文件，返回文件下载

    Args:
        file_id: 文件ID

    Returns:
        文件内容或 FileResponse
    """
    # 查询文件信息
    result = await db.execute(
        select(UploadedFile).where(UploadedFile.id == file_id)
    )
    uploaded_file = result.scalar_one_or_none()

    if uploaded_file is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 检查文件是否存在
    if not os.path.exists(uploaded_file.file_path):
        raise HTTPException(status_code=404, detail="文件已丢失")

    # 如果是图片，直接返回图片数据
    if uploaded_file.file_type == "image":
        return FileResponse(
            uploaded_file.file_path,
            media_type=uploaded_file.mime_type,
            headers={"Content-Disposition": f"inline; filename=\"{uploaded_file.filename}\""}
        )

    # 如果是文档，作为下载返回
    return FileResponse(
        uploaded_file.file_path,
        media_type=uploaded_file.mime_type,
        headers={"Content-Disposition": f"attachment; filename=\"{uploaded_file.filename}\""}
    )


@router.get("/{file_id}/info")
async def get_file_info(file_id: str, db: AsyncSession = Depends(get_db)):
    """获取文件元信息

    Args:
        file_id: 文件ID

    Returns:
        {
            "file_id": "xxx",
            "filename": "原始文件名",
            "file_type": "image|document",
            "mime_type": "image/png",
            "file_size": 12345,
            "url": "/api/upload/{file_id}",
            "exists": true,
            "upload_time": "2024-03-10T12:00:00"
        }
    """
    result = await db.execute(
        select(UploadedFile).where(UploadedFile.id == file_id)
    )
    uploaded_file = result.scalar_one_or_none()

    if uploaded_file is None:
        return {
            "file_id": file_id,
            "exists": False,
            "url": f"/api/upload/{file_id}"
        }

    file_exists = os.path.exists(uploaded_file.file_path)

    return {
        "file_id": file_id,
        "filename": uploaded_file.filename,
        "file_type": uploaded_file.file_type,
        "mime_type": uploaded_file.mime_type,
        "file_size": uploaded_file.file_size,
        "url": f"/api/upload/{file_id}",
        "exists": file_exists,
        "upload_time": uploaded_file.created_at.isoformat()
    }


@router.delete("/{file_id}")
async def delete_uploaded_file(file_id: str, db: AsyncSession = Depends(get_db)):
    """删除上传的文件

    Args:
        file_id: 文件ID

    Returns:
        {"success": true, "message": "File deleted"}
    """
    # 查询文件信息
    result = await db.execute(
        select(UploadedFile).where(UploadedFile.id == file_id)
    )
    uploaded_file = result.scalar_one_or_none()

    if uploaded_file is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 删除物理文件
    file_path = uploaded_file.file_path
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logger.warning("file_delete_failed", file_id=file_id, error=str(e))

    # 删除数据库记录
    await db.execute(
        delete(UploadedFile).where(UploadedFile.id == file_id)
    )
    await db.commit()

    logger.info("file_deleted", file_id=file_id)

    return {
        "success": True,
        "message": "文件已删除"
    }


@router.get("/")
async def list_uploaded_files(
    session_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """列出上传的文件

    Args:
        session_id: 可选的会话ID筛选
        limit: 返回数量限制
        offset: 偏移量

    Returns:
        {
            "files": [...],
            "total": 10
        }
    """
    query = select(UploadedFile)

    if session_id:
        query = query.where(UploadedFile.session_id == session_id)

    # 获取总数
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0

    # 获取文件列表
    query = query.order_by(UploadedFile.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    files = result.scalars().all()

    return {
        "files": [
            {
                "file_id": f.id,
                "filename": f.filename,
                "file_type": f.file_type,
                "mime_type": f.mime_type,
                "file_size": f.file_size,
                "url": f"/api/upload/{f.id}",
                "upload_time": f.created_at.isoformat()
            }
            for f in files
        ],
        "total": total
    }

"""
文件上传API - 对话文件和图片上传

提供以下接口：
- POST /api/upload/chat - 上传文件用于对话
- GET /api/upload/{file_id} - 获取上传文件
- DELETE /api/upload/{file_id} - 删除上传文件
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, Response
from typing import Optional, List
import asyncio
import os
import re
import subprocess
import tempfile
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
from defusedxml import ElementTree
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.database import get_db
from app.knowledge_base.models import UploadedFile
from app.utils.path_config import get_uploads_dir
from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import (
    SessionResourceService,
    stable_group_id,
)
from app.tools.resource_declarations import derivative_file, primary_file
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.service import ConversationCatalogService

logger = structlog.get_logger()

router = APIRouter()


def _content_disposition(disposition: str, filename: str) -> str:
    """Build an ASCII-safe Content-Disposition header for Unicode filenames."""
    safe_name = Path(filename or "download").name or "download"
    ascii_fallback = "".join(
        ch if 32 <= ord(ch) < 127 and ch not in {'"', "\\", ";"} else "_"
        for ch in safe_name
    ).strip("._ ")
    if not ascii_fallback:
        ascii_fallback = "download"
    encoded_name = quote(safe_name, safe="")
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_name}"

def _uploaded_file_url(file_id: str) -> str:
    """Return the canonical gateway-relative URL for an uploaded resource."""
    return f"/api/upload/{file_id}"


def _attachment_renderer(mime_type: str, filename: str) -> str:
    extension = Path(filename or "").suffix.lower()
    if mime_type.startswith("image/"):
        return "image"
    if mime_type == "application/pdf" or extension == ".pdf":
        return "pdf"
    if mime_type == "text/html" or extension in {".html", ".htm"}:
        return "html"
    if mime_type in {"text/markdown", "text/plain"} or extension in {".md", ".markdown", ".qmd", ".txt"}:
        return "markdown"
    if mime_type in {
        "text/csv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    } or extension in {".csv", ".xls", ".xlsx", ".xlsm"}:
        return "spreadsheet"
    return "file"


OFFICE_PDF_PREVIEW_EXTENSIONS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}


def _office_pdf_preview(file_path: str) -> Path | None:
    """Render Office uploads to an isolated PDF preview."""
    source = Path(file_path).resolve()
    if source.suffix.lower() not in OFFICE_PDF_PREVIEW_EXTENSIONS:
        return None
    preview = source.with_suffix(".preview.pdf")
    try:
        with tempfile.TemporaryDirectory(prefix="suyuan-office-preview-") as temp_dir:
            profile_dir = Path(temp_dir) / "profile"
            output_dir = Path(temp_dir) / "output"
            output_dir.mkdir()
            subprocess.run(
                [
                    "soffice",
                    "--headless",
                    f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(output_dir),
                    str(source),
                ],
                check=True,
                capture_output=True,
                timeout=90,
            )
            converted = output_dir / f"{source.stem}.pdf"
            if not converted.is_file() or converted.stat().st_size == 0:
                raise RuntimeError("LibreOffice did not produce a PDF preview")
            converted.replace(preview)
            return preview
    except Exception as exc:
        logger.warning(
            "office_attachment_preview_failed",
            file=str(source),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None


def _remove_office_pdf_preview(file_path: str) -> None:
    preview = Path(file_path).resolve().with_suffix(".preview.pdf")
    if preview.is_file():
        preview.unlink()

# 配置
# 统一使用 backend/backend_data_registry/uploads，避免附件路径诱导 Agent 写到仓库根目录。
UPLOAD_STORAGE_DIR = os.getenv("UPLOAD_STORAGE_DIR", str(get_uploads_dir()))
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024  # 50MB

# 支持的文件类型
IMAGE_TYPES = {
    "image/png", "image/jpeg", "image/jpg", "image/gif",
    "image/bmp", "image/webp", "image/svg+xml"
}
DOCUMENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/html",
    "application/json",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
    "application/msword",  # .doc
    "application/vnd.ms-excel",  # .xls
    "application/vnd.ms-powerpoint",  # .ppt
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
        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
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
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
        # 文档
        ".pdf", ".txt", ".md", ".markdown", ".html", ".htm", ".json", ".csv",
        # Office（新旧格式都支持）
        ".docx", ".xlsx", ".pptx",
        ".doc", ".xls", ".ppt"
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


def _xml_local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1].lower()


def _contains_external_css_reference(value: str) -> bool:
    compact = re.sub(r"\s+", "", value).lower()
    if "@import" in compact:
        return True
    return any(not target.startswith("#") for target in re.findall(r"url\(['\"]?([^)'\"]+)", compact))


def validate_svg_content(content: bytes) -> None:
    """Reject active SVG content and references that may access server-side resources."""
    try:
        root = ElementTree.fromstring(content)
    except Exception as exc:
        raise ValueError("SVG 文件不是有效的安全 XML") from exc

    if _xml_local_name(root.tag) != "svg":
        raise ValueError("SVG 文件缺少 svg 根元素")

    blocked_elements = {"script", "foreignobject", "iframe", "object", "embed"}
    for element in root.iter():
        element_name = _xml_local_name(element.tag)
        if element_name in blocked_elements:
            raise ValueError(f"SVG 包含不允许的元素: {element_name}")
        if element_name == "style" and _contains_external_css_reference(element.text or ""):
            raise ValueError("SVG 样式包含外部资源引用")

        for raw_name, raw_value in element.attrib.items():
            name = _xml_local_name(raw_name)
            value = str(raw_value).strip()
            if name.startswith("on"):
                raise ValueError("SVG 包含不允许的事件处理器")
            if name == "href" and value and not value.startswith("#"):
                raise ValueError("SVG 包含外部资源引用")
            if name == "style" and _contains_external_css_reference(value):
                raise ValueError("SVG 样式包含外部资源引用")


def _svg_render_size(content: bytes, max_dimension: int = 4096) -> tuple[int, int] | None:
    root = ElementTree.fromstring(content)

    def length(value: str | None) -> float | None:
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(px)?\s*", value or "")
        return float(match.group(1)) if match else None

    width = length(root.attrib.get("width"))
    height = length(root.attrib.get("height"))
    if not width or not height:
        view_box = re.split(r"[\s,]+", root.attrib.get("viewBox", "").strip())
        if len(view_box) == 4:
            try:
                width = width or abs(float(view_box[2]))
                height = height or abs(float(view_box[3]))
            except ValueError:
                pass
    if not width or not height:
        return None

    scale = min(1.0, max_dimension / width, max_dimension / height)
    if scale == 1.0:
        return None
    return max(1, round(width * scale)), max(1, round(height * scale))


def convert_svg_to_png(source_path: str, output_path: str) -> None:
    content = Path(source_path).read_bytes()
    validate_svg_content(content)
    render_size = _svg_render_size(content)
    size_args = (
        ["--keep-aspect-ratio", "--width", str(render_size[0]), "--height", str(render_size[1])]
        if render_size else []
    )
    try:
        subprocess.run(
            [
                "rsvg-convert",
                "--format", "png",
                *size_args,
                "--output", output_path,
                source_path,
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("SVG 转换组件未安装") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("SVG 转换超时") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"SVG 转换失败: {detail or '无法渲染该文件'}") from exc

    if not Path(output_path).is_file() or Path(output_path).stat().st_size == 0:
        raise ValueError("SVG 转换失败: 未生成有效图片")


@router.post("/chat")
async def upload_chat_file(
    file: UploadFile = File(...),
    session_id: str = Form(..., min_length=1),
    mode: str = Form("assistant"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """上传文件用于对话

    支持的文件类型：
    - 图片: PNG, JPG, JPEG, GIF, BMP, WEBP, SVG (最大 5MB；SVG 会安全转换为 PNG)
    - 文档: PDF, TXT, MD, HTML, HTM, JSON, CSV (最大 50MB)
    - Office: DOC, DOCX, XLS, XLSX, PPT, PPTX (最大 50MB)

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
    if user.auth_source == "app":
        # Android App sessions are social-source conversations and are marked
        # read-only only from the Web surface. App ownership is still checked.
        await catalog.require_read(session_id, user)
    else:
        await catalog.claim_web_draft(session_id=session_id, user=user, mode=mode)

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
    original_filename = file.filename or "unnamed"
    # 提取文件扩展名
    file_ext = Path(original_filename).suffix.lower()
    # 清理基础文件名（移除路径分隔符等危险字符）
    safe_filename_base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', original_filename)
    if not safe_filename_base:
        safe_filename_base = "unnamed"
    # 使用 file_id + 扩展名保存，避免文件名冲突
    is_svg = file_ext == ".svg" or (file.content_type or "").lower() == "image/svg+xml"
    stored_ext = ".png" if is_svg else file_ext
    stored_filename = f"{Path(original_filename).stem}.png" if is_svg else original_filename
    stored_mime_type = "image/png" if is_svg else (file.content_type or "application/octet-stream")
    safe_filename = f"{file_id}{stored_ext}" if stored_ext else file_id
    file_path = os.path.join(UPLOAD_STORAGE_DIR, safe_filename)
    source_file_path = os.path.join(UPLOAD_STORAGE_DIR, f"{file_id}.svg.upload") if is_svg else file_path

    try:
        with open(source_file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        if is_svg:
            convert_svg_to_png(source_file_path, file_path)
            os.remove(source_file_path)
    except ValueError as e:
        for path in {source_file_path, file_path}:
            if os.path.exists(path):
                os.remove(path)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("file_save_failed", file_id=file_id, filename=original_filename, error=str(e))
        for path in {source_file_path, file_path}:
            if os.path.exists(path):
                os.remove(path)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 保存文件元信息到数据库
    file_category = get_file_category(stored_mime_type, stored_filename)

    uploaded_file = UploadedFile(
        id=file_id,
        filename=stored_filename,
        file_path=file_path,
        file_type=file_category,
        mime_type=stored_mime_type,
        file_size=os.path.getsize(file_path),
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

    resource_ref = None
    preview_ref = None
    if session_id:
        try:
            group_key = f"upload:{file_id}"
            attachment_renderer = _attachment_renderer(stored_mime_type, stored_filename)
            previewable = attachment_renderer != "file"
            declarations = [
                ResourceDeclaration.model_validate(
                    primary_file(
                        file_path,
                        group_key=group_key,
                        tool_name="upload_chat",
                        role="attachment",
                        renderer=attachment_renderer,
                        capabilities=("preview", "download", "edit")
                        if (
                            attachment_renderer == "spreadsheet"
                            and Path(stored_filename).suffix.lower() in {".xls", ".xlsx"}
                        )
                        else (("preview", "download") if previewable else ("download",)),
                        label=stored_filename,
                        metadata={
                            "file_id": file_id,
                            "source": "user_upload",
                            **(
                                {
                                    "original_filename": original_filename,
                                    "original_mime_type": "image/svg+xml",
                                }
                                if is_svg
                                else {}
                            ),
                        },
                    )
                )
            ]
            office_preview = await asyncio.to_thread(_office_pdf_preview, file_path)
            if office_preview is not None:
                declarations.append(
                    ResourceDeclaration.model_validate(
                        derivative_file(
                            office_preview,
                            group_key=group_key,
                            parent_key=declarations[0].resource_key,
                            tool_name="upload_chat",
                            relation="preview",
                            role="attachment",
                            renderer="pdf",
                            capabilities=("preview",),
                            label=f"{Path(stored_filename).stem}.pdf",
                            metadata={"source": "office_preview"},
                        )
                    )
                )
            resource_batch = await SessionResourceService.database().publish_group(
                session_id,
                f"upload:{file_id}",
                group_key,
                declarations,
            )
            resource_ref = next(
                (item for item in resource_batch.resources if item.relation == "primary"),
                None,
            )
            preview_ref = next(
                (item for item in resource_batch.resources if item.relation == "preview"),
                None,
            )
            if resource_ref is None:
                raise RuntimeError("uploaded resource missing from resource store result")
        except Exception as exc:
            logger.error(
                "session_resource_registration_failed",
                file_id=file_id,
                session_id=session_id,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            await db.execute(delete(UploadedFile).where(UploadedFile.id == file_id))
            await db.commit()
            if os.path.exists(file_path):
                os.remove(file_path)
            _remove_office_pdf_preview(file_path)
            raise HTTPException(status_code=503, detail="resource_store_unavailable") from exc

    logger.info(
        "file_uploaded",
        file_id=file_id,
        filename=stored_filename,
        file_type=file_category,
        file_size=uploaded_file.file_size
    )

    # 对外协议只暴露稳定的网关相对资源地址。本地路径由 Agent 通过 file_id
    # 在服务端解析，避免把部署主机或文件系统细节泄漏到消息与前端状态中。
    file_url = _uploaded_file_url(file_id)

    return {
        "file_id": file_id,
        "filename": stored_filename,
        "file_type": file_category,
        "mime_type": stored_mime_type,
        "file_size": uploaded_file.file_size,
        "url": file_url,
        "download_url": file_url,
        "preview_url": (
            f"/api/social/app/sessions/{session_id}/resources/{preview_ref.resource_id}/content"
            if preview_ref is not None and preview_ref.resource_id and session_id
            else file_url
        ),
        "preview_mime_type": "application/pdf" if preview_ref is not None else None,
        "upload_time": uploaded_file.created_at.isoformat(),
        "resource_ref": (
            {
                "ref_id": resource_ref.resource_id,
                "resource_id": resource_ref.resource_id,
                "resource_key": resource_ref.resource_key,
                "group_id": resource_ref.group_id,
                "relation": resource_ref.relation,
                "kind": resource_ref.kind,
                "role": resource_ref.role,
                "label": resource_ref.label,
                "renderer": resource_ref.renderer,
                "capabilities": resource_ref.capabilities,
                "status": resource_ref.status,
                "created_at": resource_ref.created_at.isoformat(),
            }
            if resource_ref else None
        ),
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
            headers={"Content-Disposition": _content_disposition("inline", uploaded_file.filename)}
        )

    # 如果是文档，作为下载返回
    return FileResponse(
        uploaded_file.file_path,
        media_type=uploaded_file.mime_type,
        headers={"Content-Disposition": _content_disposition("attachment", uploaded_file.filename)}
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
async def delete_uploaded_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(require_current_user),
):
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
    try:
        _remove_office_pdf_preview(file_path)
    except Exception as e:
        logger.warning("office_preview_delete_failed", file_id=file_id, error=str(e))

    # 删除数据库记录
    await db.execute(
        delete(UploadedFile).where(UploadedFile.id == file_id)
    )
    await db.commit()

    if uploaded_file.session_id:
        try:
            resources = SessionResourceService.database()
            page = await resources.list_resources(
                uploaded_file.session_id,
                group_id=stable_group_id(
                    uploaded_file.session_id, f"upload:{file_id}"
                ),
                status=None,
            )
            for resource in page.resources:
                await resources.delete_resource(
                    uploaded_file.session_id, resource.resource_id
                )
        except Exception as exc:
            logger.error(
                "deleted_upload_resource_update_failed",
                file_id=file_id,
                session_id=uploaded_file.session_id,
                error=str(exc),
            )

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

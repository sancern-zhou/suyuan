"""
报告生成API路由
场景2：模板化报告生成
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from typing import Optional, Dict
import structlog
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.report_generation import TemplateReportRequest, QuickGenerateRequest
from app.utils.docx_markdown import convert_docx_to_markdown, sanitize_template_time_references
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.service import ConversationCatalogService
from app.db.database import get_db
from app.db.models.report_template import ReportTemplate
from sqlalchemy import select

logger = structlog.get_logger()

router = APIRouter(prefix="/report", tags=["report-generation"])

async def _stream_template_report_agent(
    template_content: str,
    target_time_range: Dict[str, str],
    raw_request: Request,
    user: CurrentUser,
    catalog: ConversationCatalogService,
) -> Response:
    """Use the Agent's session lifecycle and forward its terminal event once."""
    template_content = sanitize_template_time_references(template_content)
    display = target_time_range.get(
        "display", f"{target_time_range.get('start', '')}至{target_time_range.get('end', '')}"
    )
    user_query = f"""请根据以下模板内容，生成{display}的空气质量DOCX报告。

【模板内容】
{template_content}

【要求】
1. 分析模板结构，保留用户要求的报告章节安排。
2. 查询目标时段的真实数据，说明数据来源和缺失情况。
3. 按当前报告模式的工具及资源交付规范生成可下载的DOCX报告。
4. 将报告登记为当前会话资源，并在最终答复中提供下载入口。

请开始执行。"""

    from app.api.agent import AgentAnalyzeRequest, analyze_stream

    return await analyze_stream(
        AgentAnalyzeRequest(query=user_query, mode="report", skill_ids=[], context_refs=[]),
        raw_request=raw_request, user=user, catalog=catalog,
    )


@router.post("/generate-from-template-agent")
async def generate_from_template_agent(
    request: TemplateReportRequest,
    raw_request: Request,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """
    基于 Agent（模板报告专家）的临时报告生成（方案B Agent化，JSON 输入）。

    Request:
        {
            "template_content": "历史报告 Markdown 内容",
            "target_time_range": {"start": "...", "end": "...", "display": "..."}
        }
    """
    return await _stream_template_report_agent(
        template_content=request.template_content,
        target_time_range=request.target_time_range,
        raw_request=raw_request, user=user, catalog=catalog,
    )


@router.post("/generate-from-template-file")
async def generate_from_template_file(
    raw_request: Request,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    file: UploadFile = File(...),
    start: str = Form(...),
    end: str = Form(...),
    display: Optional[str] = Form(None),
):
    """
    基于上传的模板文件生成临时报告（Agent 化）。

    - 支持 .docx / .md / .txt：
        - .docx: 使用 convert_docx_to_markdown 转为带格式的 Markdown
        - .md / .txt: 按 UTF-8 解码为文本
    - 不支持其他格式，直接返回 400。
    """
    filename_lower = (file.filename or "").lower()
    raw_bytes = await file.read()

    if filename_lower.endswith(".docx"):
        template_content = convert_docx_to_markdown(raw_bytes)
    elif filename_lower.endswith(".md") or filename_lower.endswith(".txt"):
        try:
            template_content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # 回退到默认编码，避免因编码问题直接失败
            template_content = raw_bytes.decode(errors="ignore")
    else:
        raise HTTPException(
            status_code=400,
            detail="仅支持 .md/.txt/.docx 模板文件"
        )

    target_time_range: Dict[str, str] = {
        "start": start,
        "end": end
    }
    if display:
        target_time_range["display"] = display

    return await _stream_template_report_agent(
        template_content=template_content,
        target_time_range=target_time_range,
        raw_request=raw_request, user=user, catalog=catalog,
    )


@router.post("/templates/{template_id}/generate")
async def generate_from_saved_template(
    template_id: UUID,
    request: QuickGenerateRequest,
    raw_request: Request,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
    db: AsyncSession = Depends(get_db),
):
    """Generate from a saved template through the same current Agent path."""
    template = await db.get(ReportTemplate, template_id)
    if template is None or not template.is_active:
        raise HTTPException(status_code=404, detail="模板不存在或已停用")
    return await _stream_template_report_agent(
        template.content, request.time_range, raw_request, user, catalog
    )


@router.post("/templates")
async def create_template(
    name: str = Form(...),
    source_report: str = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    创建报告模板（方案C）

    Args:
        name: 模板名称
        source_report: 源报告内容
        description: 模板描述
        db: 数据库会话

    Returns:
        创建的模板信息
    """
    try:
        # 检查模板名称是否已存在
        result = await db.execute(
            select(ReportTemplate).where(ReportTemplate.name == name)
        )
        existing = result.scalar_one_or_none()

        if existing:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Template name already exists",
                    "message": "模板名称已存在"
                }
            )

        # 创建新模板
        template = ReportTemplate(
            name=name,
            description=description,
            content=source_report,
            template_type="structured",
            is_active=True
        )

        db.add(template)
        await db.commit()
        await db.refresh(template)

        logger.info(f"Template created: {template.id} - {template.name}")

        return {
            "id": str(template.id),
            "name": template.name,
            "description": template.description,
            "status": "success",
            "message": "模板创建成功"
        }

    except Exception as e:
        logger.error(f"Template creation failed: {str(e)}")
        await db.rollback()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "message": "模板创建失败"
            }
        )

@router.get("/templates")
async def list_templates(
    db: AsyncSession = Depends(get_db)
):
    """
    获取模板列表

    Args:
        db: 数据库会话

    Returns:
        模板列表
    """
    try:
        result = await db.execute(
            select(ReportTemplate).where(ReportTemplate.is_active == True).order_by(ReportTemplate.created_at.desc())
        )
        templates = result.scalars().all()

        return [
            {
                "id": str(template.id),
                "name": template.name,
                "description": template.description,
                "created_at": template.created_at.isoformat() if template.created_at else None,
                "usage_count": template.usage_count,
                "template_type": template.template_type
            }
            for template in templates
        ]

    except Exception as e:
        logger.error(f"Failed to list templates: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "templates": []
            }
        )


@router.post("/upload-template")
async def upload_template(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    上传模板文件

    Args:
        file: 模板文件（.md, .txt）
        name: 模板名称（可选，从文件名提取）
        description: 模板描述
        db: 数据库会话

    Returns:
        上传结果
    """
    try:
        # 读取文件内容，支持 .md/.txt/.docx，其中 docx 将转换为 Markdown
        filename_lower = (file.filename or "").lower()
        raw_bytes = await file.read()

        if filename_lower.endswith(".docx"):
            content = convert_docx_to_markdown(raw_bytes)
        elif filename_lower.endswith(".md") or filename_lower.endswith(".txt"):
            content = raw_bytes.decode("utf-8")
        else:
            raise HTTPException(
                status_code=400,
                detail="仅支持 .md/.txt/.docx 模板文件"
            )

        # 提取模板名称
        template_name = name or file.filename.replace(".md", "").replace(".txt", "")

        # 检查模板名称是否已存在
        result = await db.execute(
            select(ReportTemplate).where(ReportTemplate.name == template_name)
        )
        existing = result.scalar_one_or_none()

        if existing:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Template name already exists",
                    "message": "模板名称已存在"
                }
            )

        # 保存模板到数据库
        template = ReportTemplate(
            name=template_name,
            description=description,
            content=content,
            template_type="structured",
            is_active=True
        )

        db.add(template)
        await db.commit()
        await db.refresh(template)

        logger.info(f"Template uploaded: {template.id} - {template.name}")

        return {
            "success": True,
            "template_id": str(template.id),
            "name": template.name,
            "description": template.description,
            "content_length": len(content),
            "message": "模板上传成功"
        }

    except Exception as e:
        logger.error(f"Template upload failed: {str(e)}")
        await db.rollback()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "message": "模板上传失败"
            }
        )

@router.get("/health")
async def health_check():
    """
    健康检查

    Returns:
        服务状态
    """
    return {
        "status": "healthy",
        "service": "report-generation",
        "version": "1.0.0",
        "timestamp": 1640995200
    }

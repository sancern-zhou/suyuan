"""
报告生成API路由
场景2：模板化报告生成
"""
from fastapi import APIRouter, Depends, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional, Dict, Any
import json
import logging
import uuid
from fastapi import HTTPException
from fastapi import HTTPException
from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.report_generation import (
    TemplateReportRequest, CreateTemplateRequest, QuickGenerateRequest,
    ReportOptions
)
from app.services.template_report_engine import TemplateReportEngine
from app.services.tool_executor import ToolExecutor
from app.services.report_formatter import ReportFormatter
from app.routers.utils_docx import convert_docx_to_markdown, sanitize_template_time_references
from app.agent.experts.template_report_executor import TemplateReportExecutor
from app.agent.core.expert_plan_generator import ExpertTask
from app.agent.context.data_context_manager import DataContextManager
from app.agent.context.execution_context import ExecutionContext
from app.db.database import get_db
from app.db.models.report_template import ReportTemplate, ReportGenerationHistory
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["report-generation"])

# 全局服务实例
_react_agent = None
_tool_executor = None
_template_engine = None

def get_react_agent():
    """
    获取用于报告生成的 ReAct Agent 实例。

    【关键设计】
    - 这里复用 `app.routers.agent` 中的 `multi_expert_agent_instance`，
      确保模板报告流水线与主多专家系统/后续 ReAct 对话共享同一个
      `ReActAgent` 实例和会话记忆（HybridMemoryManager）。
    """
    global _react_agent
    if _react_agent is None:
        # 延迟导入，避免循环依赖在模块加载阶段就触发
        from app.routers.agent import multi_expert_agent_instance

        _react_agent = multi_expert_agent_instance
        # 注意：这里的 logger 是标准 logging.Logger，不支持 structlog 式的关键字参数。
        # 为避免 TypeError，仅记录一条简单的信息。
        logger.info("React Agent initialized for report generation (reuse multi_expert_agent_instance)")
    return _react_agent

def get_tool_executor() -> ToolExecutor:
    """获取工具执行器实例"""
    global _tool_executor, _react_agent
    if _tool_executor is None:
        react_agent = get_react_agent()
        _tool_executor = ToolExecutor(react_agent=react_agent)
        logger.info("ToolExecutor initialized with React Agent")
    return _tool_executor

def get_template_engine() -> TemplateReportEngine:
    """获取模板报告引擎实例"""
    global _template_engine
    if _template_engine is None:
        tool_executor = get_tool_executor()
        _template_engine = TemplateReportEngine(tool_executor)
        logger.info("TemplateReportEngine initialized")
    return _template_engine


def _stream_template_report_agent(
    template_content: str,
    target_time_range: Dict[str, str],
) -> StreamingResponse:
    """
    公共封装：基于模板内容 + 时间范围，走模板报告专家（Agent）生成流程。

    - generate-from-template-agent（JSON 版）与
      generate-from-template-file（文件上传版）都复用此逻辑。
    """

    executor = TemplateReportExecutor()

    async def event_generator():
        """
        统一的模板报告流水线入口：
        - 使用与主多专家系统共享的 ReActAgent 实例创建/复用会话；
        - 复用该会话下的 HybridMemoryManager + DataContextManager；
        - 将模板报告生成结果写入同一会话记忆，便于后续 ReAct 连续对话使用。
        """
        react_agent = get_react_agent()

        # 通过 ReActAgent 创建/复用会话，获取统一的 HybridMemoryManager
        # 注意：这是 ReActAgent 的内部方法，这里有意复用以实现真正共享记忆。
        session_id, memory_manager, created_new = await react_agent._get_or_create_session(  # type: ignore[attr-defined]
            session_id=None,
            reset_session=False
        )

        data_manager = DataContextManager(memory_manager)

        # 将上下文注入执行器，使其内部并发工具调用复用同一 DataContextManager / Memory
        executor._memory_manager = memory_manager
        executor._data_manager = data_manager

        try:
            # 起始事件：将真实的 ReAct 会话 ID 暴露给前端，便于后续连续对话复用
            yield format_sse_event({
                "type": "start",
                "data": {
                    "session_id": session_id,
                    "created_new": created_new
                }
            })

            # 为模板报告专家构造任务，上下文中仅放入模板和时间范围
            task = ExpertTask(
                task_id=f"template_report_{uuid.uuid4().hex[:6]}",
                expert_type="template_report",
                task_description="临时报告生成",
                context={
                    "template_content": template_content,
                    "target_time_range": target_time_range,
                    "session_id": session_id
                }
            )

            result = await executor.execute(task)

            # 将生成的整篇报告作为一次“助手回复”写入会话对话历史，
            # 方便后续 ReAct 在同一 session 中引用报告内容进行修改/追问。
            try:
                memory_manager.session.add_assistant_message(result.analysis.section_content)
            except Exception as log_err:  # 不影响主流程
                logger.warning(
                    "template_report_add_assistant_message_failed",
                    error=str(log_err)
                )

            # 完成事件：除了原有字段，还回传统一的 session_id，便于前端保存
            yield format_sse_event({
                "type": "complete",
                "data": {
                    "session_id": session_id,
                    "report_content": result.analysis.section_content,
                    "data_ids": result.data_ids,
                    "status": result.status
                }
            })

        except Exception as e:
            logger.error("template_report_agent_failed", error=str(e), exc_info=True)
            yield format_sse_event({
                "type": "fatal_error",
                "data": {"error": str(e)}
            })
        finally:
            # 更新会话最近使用时间，保持与 ReActAgent 的会话生命周期一致
            try:
                await react_agent._mark_session_used(session_id)  # type: ignore[attr-defined]
            except Exception as mark_err:
                logger.warning(
                    "template_report_mark_session_used_failed",
                    error=str(mark_err),
                    session_id=session_id
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/generate-from-template-agent")
async def generate_from_template_agent(
    request: TemplateReportRequest
):
    """
    基于 Agent（模板报告专家）的临时报告生成（方案B Agent化，JSON 输入）。

    Request:
        {
            "template_content": "历史报告 Markdown 内容",
            "target_time_range": {"start": "...", "end": "...", "display": "..."}
        }
    """
    return _stream_template_report_agent(
        template_content=request.template_content,
        target_time_range=request.target_time_range
    )


@router.post("/generate-from-template-file")
async def generate_from_template_file(
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

    # 时间标准化处理：将模板中的具体时间替换为占位符，避免LLM被历史时间误导
    template_content = sanitize_template_time_references(template_content)

    target_time_range: Dict[str, str] = {
        "start": start,
        "end": end
    }
    if display:
        target_time_range["display"] = display

    return _stream_template_report_agent(
        template_content=template_content,
        target_time_range=target_time_range
    )

@router.post("/generate-from-template")
async def generate_from_template(
    request: TemplateReportRequest
):
    """
    基于模板生成报告（流式返回）

    Request:
        {
            "template_content": "历史报告Markdown内容...",
            "target_time_range": {
                "start": "2025-01-01",
                "end": "2025-07-31"
            },
            "options": {
                "include_analysis": true,
                "include_charts": false
            }
        }

    Response: SSE流
        event: phase_started
        data: {"phase": "parsing", "description": "解析报告结构"}

        event: structure_parsed
        data: {"sections_count": 5, "tables_count": 2, "rankings_count": 3}

        event: phase_started
        data: {"phase": "data_fetching", "description": "获取数据"}

        event: data_fetched
        data: {"record_count": 100, "requirements_count": 10}

        event: report_completed
        data: {"report_content": "# 生成的报告\n..."}
    """
    engine = get_template_engine()

    async def event_generator():
        try:
            # 时间标准化处理：将模板中的具体时间替换为占位符
            sanitized_template = sanitize_template_time_references(request.template_content)
            
            # 生成报告
            async for event in engine.generate_from_template(
                template_content=sanitized_template,
                target_time_range=request.target_time_range,
                options=ReportOptions(**(request.options or {}))
            ):
                # 格式化事件为SSE格式
                yield format_sse_event(event)
        except Exception as e:
            logger.error(f"Report generation error: {str(e)}")
            error_event = {
                "type": "error",
                "data": {"error": str(e)}
            }
            yield format_sse_event(error_event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
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

@router.post("/templates/{template_id}/generate")
async def generate_from_saved_template(
    template_id: str,
    request: QuickGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    从已保存模板快速生成

    Args:
        template_id: 模板ID
        request: 快速生成请求
        db: 数据库会话

    Returns:
        SSE流式响应
    """
    engine = get_template_engine()

    async def event_generator():
        try:
            async for event in engine.generate_quick(
                template_id=template_id,
                time_range=request.time_range,
                db_session=db
            ):
                yield format_sse_event(event)
        except Exception as e:
            logger.error(f"Quick generation error: {str(e)}")
            error_event = {
                "type": "error",
                "data": {"error": str(e)}
            }
            yield format_sse_event(error_event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
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

def format_sse_event(event) -> str:
    """
    格式化事件为SSE格式

    Args:
        event: 事件对象

    Returns:
        str: SSE格式的事件
    """
    # 转换为字典
    event_dict = event.dict() if hasattr(event, 'dict') else event

    # 提取类型和数据
    event_type = event_dict.get("type", "unknown")
    event_data = event_dict.get("data", {})

    # 序列化为JSON
    data_json = json.dumps(event_data, ensure_ascii=False)

    # 返回SSE格式
    return f"event: {event_type}\ndata: {data_json}\n\n"

"""
报告导出路由

支持PDF/Word/HTML三种格式导出
前端截图方案：图表截图由前端完成并传递base64
"""

from fastapi import APIRouter, Response, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api/export", tags=["export"])


class ChartUserState(BaseModel):
    """图表用户交互状态"""
    legendSelected: Optional[Dict[str, bool]] = None
    dataZoom: Optional[List[Dict[str, Any]]] = None
    grid3D: Optional[Dict[str, Any]] = None
    chartType: Optional[str] = None
    
    class Config:
        extra = "allow"


class ChartExportData(BaseModel):
    """单个图表导出数据"""
    id: Optional[str] = None
    type: Optional[str] = "chart"  # 改为可选，默认chart
    title: Optional[str] = None
    data: Optional[Union[Dict[str, Any], List[Any]]] = None  # 支持字典或数组
    meta: Optional[Dict[str, Any]] = None
    user_state: Optional[ChartUserState] = None
    preview_image: Optional[str] = None  # 前端截图的base64
    order: Optional[int] = None
    
    class Config:
        extra = "allow"  # 允许额外字段，避免验证失败


class ReportExportRequest(BaseModel):
    """报告导出请求"""
    format: str = Field(default="pdf", description="导出格式: pdf/docx/html")
    report_content: Optional[Dict[str, Any]] = Field(
        default=None,
        description="报告专家生成的内容"
    )
    charts: List[ChartExportData] = Field(
        default_factory=list,
        description="选中的图表列表（含用户状态和前端截图）"
    )
    
    class Config:
        extra = "allow"


@router.post("/report")
async def export_report(request: ReportExportRequest):
    """
    导出综合分析报告
    
    支持格式：
    - pdf: PDF文档（推荐）
    - docx: Word文档
    - html: HTML网页
    """
    logger.info(
        "export_report_request",
        format=request.format,
        chart_count=len(request.charts),
        has_report_content=request.report_content is not None,
        chart_types=[c.type for c in request.charts] if request.charts else [],
        chart_ids=[c.id for c in request.charts] if request.charts else [],
        chart_titles=[c.title for c in request.charts] if request.charts else []
    )
    
    try:
        from app.services.report_exporter import ReportExporter
        
        exporter = ReportExporter()
        actual_format = request.format
        fallback_used = False
        
        try:
            result = await exporter.generate(
                format=request.format,
                report_content=request.report_content,
                charts=[c.dict() for c in request.charts]
            )
        except ImportError as pdf_error:
            # PDF导出失败，降级为HTML
            if request.format == "pdf":
                logger.warning("pdf_fallback_to_html", error=str(pdf_error))
                result = await exporter.generate(
                    format="html",
                    report_content=request.report_content,
                    charts=[c.dict() for c in request.charts]
                )
                actual_format = "html"
                fallback_used = True
            else:
                raise
        
        mime_types = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "html": "text/html; charset=utf-8"
        }
        extensions = {"pdf": "pdf", "docx": "docx", "html": "html"}
        
        mime_type = mime_types.get(actual_format, "application/octet-stream")
        extension = extensions.get(actual_format, "bin")
        filename = f"pollution_tracing_report.{extension}"
        
        logger.info(
            "export_report_success",
            format=actual_format,
            original_format=request.format,
            fallback_used=fallback_used,
            result_size=len(result) if result else 0
        )
        
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition, X-Export-Fallback"
        }
        if fallback_used:
            headers["X-Export-Fallback"] = "html"
        
        return Response(
            content=result,
            media_type=mime_type,
            headers=headers
        )
        
    except ImportError as e:
        logger.error("export_dependency_missing", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"导出功能依赖缺失: {str(e)}。请安装: pip install weasyprint python-docx markdown jinja2"
        )
    except Exception as e:
        logger.error("export_report_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.get("/status")
async def export_status():
    """检查导出服务状态"""
    status = {
        "available": True,
        "formats": ["html"],
        "dependencies": {}
    }
    
    # 检查weasyprint
    try:
        import weasyprint
        status["formats"].append("pdf")
        status["dependencies"]["weasyprint"] = True
    except ImportError:
        status["dependencies"]["weasyprint"] = False
    
    # 检查python-docx
    try:
        import docx
        status["formats"].append("docx")
        status["dependencies"]["python-docx"] = True
    except ImportError:
        status["dependencies"]["python-docx"] = False
    
    # 检查markdown
    try:
        import markdown
        status["dependencies"]["markdown"] = True
    except ImportError:
        status["dependencies"]["markdown"] = False
    
    return status

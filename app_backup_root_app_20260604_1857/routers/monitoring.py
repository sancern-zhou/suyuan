"""
LLM 监控 API 路由

提供查看 LLM 调用统计的 API 端点
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import structlog

from app.monitoring import (
    get_statistics,
    print_report,
    export_to_csv,
    export_to_json,
    get_monitor
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


class StatisticsResponse(BaseModel):
    """统计信息响应"""
    total_calls: int
    successful_calls: int
    failed_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost: float
    average_ttft: float
    average_output_rate: float
    success_rate: float
    by_model: Dict[str, Dict[str, Any]]


@router.get("/stats", response_model=StatisticsResponse)
async def get_llm_stats():
    """
    获取 LLM 调用统计信息
    
    Returns:
        统计信息（JSON 格式）
    """
    try:
        stats = get_statistics()
        return StatisticsResponse(**stats)
    except Exception as e:
        logger.error("get_llm_stats_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.get("/report")
async def get_llm_report():
    """
    获取 LLM 调用报告（文本格式）
    
    Returns:
        文本格式的统计报告
    """
    try:
        from io import StringIO
        import sys
        
        # 重定向 stdout 到 StringIO
        old_stdout = sys.stdout
        sys.stdout = buffer = StringIO()
        
        try:
            print_report()
        finally:
            sys.stdout = old_stdout
        
        report_text = buffer.getvalue()
        
        return {
            "report": report_text,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error("get_llm_report_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成报告失败: {str(e)}")


@router.post("/export/csv")
async def export_stats_csv(output_dir: Optional[str] = None):
    """
    导出统计信息为 CSV
    
    Args:
        output_dir: 输出目录（可选，默认为当前目录）
    
    Returns:
        导出文件路径
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(output_dir) / f"llm_stats_{timestamp}.csv" if output_dir else f"llm_stats_{timestamp}.csv"
        
        export_to_csv(str(output_path))
        
        logger.info("stats_exported_to_csv", filepath=str(output_path))
        
        return {
            "success": True,
            "filepath": str(output_path),
            "message": "CSV 导出成功"
        }
    except Exception as e:
        logger.error("export_csv_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"导出 CSV 失败: {str(e)}")


@router.post("/export/json")
async def export_stats_json(output_dir: Optional[str] = None):
    """
    导出统计信息为 JSON
    
    Args:
        output_dir: 输出目录（可选，默认为当前目录）
    
    Returns:
        导出文件路径
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(output_dir) / f"llm_stats_{timestamp}.json" if output_dir else f"llm_stats_{timestamp}.json"
        
        export_to_json(str(output_path))
        
        logger.info("stats_exported_to_json", filepath=str(output_path))
        
        return {
            "success": True,
            "filepath": str(output_path),
            "message": "JSON 导出成功"
        }
    except Exception as e:
        logger.error("export_json_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"导出 JSON 失败: {str(e)}")


@router.delete("/reset")
async def reset_stats():
    """
    重置统计信息（清空所有记录）
    
    ⚠️ 警告：此操作不可逆
    """
    try:
        monitor = get_monitor()
        monitor.records.clear()
        
        logger.info("stats_reset")
        
        return {
            "success": True,
            "message": "统计信息已重置"
        }
    except Exception as e:
        logger.error("reset_stats_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"重置统计信息失败: {str(e)}")


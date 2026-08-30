"""
LLM 监控 API 路由

提供查看 LLM 调用统计的 API 端点
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime
from pathlib import Path
import structlog

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.monitoring import (
    get_statistics,
    print_report,
    export_to_csv,
    export_to_json,
    get_monitor
)
from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


def _require_admin(user: CurrentUser) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin_required")


def _export_dir() -> Path:
    export_dir = get_data_registry() / "exports" / "monitoring"
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir


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
async def get_llm_stats(
    user: CurrentUser = Depends(require_current_user),
):
    """
    获取 LLM 调用统计信息（仅管理员）

    Returns:
        统计信息（JSON 格式）
    """
    _require_admin(user)
    try:
        stats = get_statistics()
        return StatisticsResponse(**stats)
    except Exception as e:
        logger.error("get_llm_stats_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.get("/report")
async def get_llm_report(
    user: CurrentUser = Depends(require_current_user),
):
    """
    获取 LLM 调用报告（文本格式，仅管理员）

    Returns:
        文本格式的统计报告
    """
    _require_admin(user)
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
async def export_stats_csv(
    user: CurrentUser = Depends(require_current_user),
):
    """
    导出统计信息为 CSV（仅管理员，输出目录固定在数据注册表内）

    Returns:
        导出文件路径
    """
    _require_admin(user)
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = _export_dir() / f"llm_stats_{timestamp}.csv"

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
async def export_stats_json(
    user: CurrentUser = Depends(require_current_user),
):
    """
    导出统计信息为 JSON（仅管理员，输出目录固定在数据注册表内）

    Returns:
        导出文件路径
    """
    _require_admin(user)
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = _export_dir() / f"llm_stats_{timestamp}.json"

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
async def reset_stats(
    user: CurrentUser = Depends(require_current_user),
):
    """
    重置统计信息（清空所有记录，仅管理员）

    ⚠️ 警告：此操作不可逆
    """
    _require_admin(user)
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


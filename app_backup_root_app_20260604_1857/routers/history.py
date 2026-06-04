"""
历史记录管理API路由
提供分析历史的查询、管理功能
"""
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Body
import structlog

from app.services.history_service import history_service, AnalysisHistoryRecord

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/list")
async def get_history_list(
    limit: int = Query(50, ge=1, le=200, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    scale: Optional[str] = Query(None, description="筛选维度：station 或 city"),
    city: Optional[str] = Query(None, description="筛选城市"),
    pollutant: Optional[str] = Query(None, description="筛选污染物"),
    user_id: Optional[str] = Query(None, description="筛选用户"),
    bookmarked_only: bool = Query(False, description="仅显示收藏")
):
    """
    获取历史记录列表（分页、筛选）

    返回示例：
    ```json
    {
      "records": [
        {
          "id": 1,
          "session_id": "uuid-xxxx",
          "query_text": "分析广州天河站2025-08-09的O3污染",
          "scale": "station",
          "location": "天河站",
          "city": "广州",
          "pollutant": "O3",
          "start_time": "2025-08-09T00:00:00",
          "end_time": "2025-08-09T23:59:59",
          "status": "completed",
          "duration_seconds": 45.2,
          "is_bookmarked": false,
          "created_at": "2025-10-23T10:30:00"
        }
      ],
      "total": 125,
      "limit": 50,
      "offset": 0
    }
    ```
    """
    try:
        result = await history_service.get_history_list(
            limit=limit,
            offset=offset,
            scale=scale,
            city=city,
            pollutant=pollutant,
            user_id=user_id,
            bookmarked_only=bookmarked_only
        )

        logger.info(
            "history_list_requested",
            total=result["total"],
            returned=len(result["records"]),
            filters={
                "scale": scale,
                "city": city,
                "pollutant": pollutant,
                "bookmarked_only": bookmarked_only
            }
        )

        return result

    except Exception as e:
        logger.error("get_history_list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch history list: {str(e)}")


@router.get("/{session_id}")
async def get_history_detail(session_id: str):
    """
    获取历史记录详情（用于恢复完整状态）

    返回完整的分析数据，包括：
    - 原始数据（气象、监测、组分、企业）
    - 分析结果（文本、KPI、可视化配置）
    - 对话历史

    用于前端恢复历史分析结果的完整展示。
    """
    try:
        record = await history_service.get_by_session_id(session_id)

        if not record:
            raise HTTPException(status_code=404, detail=f"History record not found: {session_id}")

        logger.info("history_detail_requested", session_id=session_id)

        # 🔧 修复：将 modules_data 提取为主数据结构，与实时分析响应格式一致
        # 如果 modules_data 存在且包含完整的分析模块，使用它作为主数据
        # 否则回退到传统的历史记录格式
        if record.get("modules_data") and isinstance(record["modules_data"], dict):
            # 使用 modules_data 作为主要响应数据（与实时分析一致）
            response_data = record["modules_data"]

            # 附加元数据到 query_info 中（如果存在）
            if "query_info" not in response_data or response_data["query_info"] is None:
                response_data["query_info"] = {}

            # 补充历史记录的元数据
            response_data["_history_metadata"] = {
                "session_id": record.get("session_id"),
                "created_at": record.get("created_at"),
                "is_bookmarked": record.get("is_bookmarked"),
                "notes": record.get("notes"),
                "tags": record.get("tags"),
                "duration_seconds": record.get("duration_seconds"),
                "from_history": True  # 标记为历史数据
            }

            logger.info(
                "history_transformed_to_analysis_format",
                session_id=session_id,
                has_visuals=any(
                    module.get("visuals")
                    for module in [
                        response_data.get("weather_analysis"),
                        response_data.get("regional_analysis"),
                        response_data.get("voc_analysis"),
                        response_data.get("particulate_analysis")
                    ]
                    if isinstance(module, dict)
                )
            )

            return {
                "success": True,
                "data": response_data
            }
        else:
            # 回退：返回完整的历史记录（兼容旧数据）
            logger.warning(
                "history_no_modules_data_fallback",
                session_id=session_id,
                hint="modules_data 不存在或为空，返回完整历史记录"
            )
            return {
                "success": True,
                "data": record,
                "_fallback": True
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_history_detail_failed", error=str(e), session_id=session_id)
        raise HTTPException(status_code=500, detail=f"Failed to fetch history detail: {str(e)}")


@router.delete("/{session_id}")
async def delete_history(session_id: str):
    """
    删除历史记录

    永久删除指定的分析记录。
    """
    try:
        deleted = await history_service.delete_by_session_id(session_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"History record not found: {session_id}")

        logger.info("history_deleted_via_api", session_id=session_id)

        return {
            "success": True,
            "message": "History record deleted successfully",
            "session_id": session_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_history_failed", error=str(e), session_id=session_id)
        raise HTTPException(status_code=500, detail=f"Failed to delete history: {str(e)}")


@router.post("/{session_id}/bookmark")
async def toggle_bookmark(session_id: str):
    """
    切换收藏状态

    点击收藏/取消收藏。
    """
    try:
        new_status = await history_service.toggle_bookmark(session_id)

        logger.info("bookmark_toggled_via_api", session_id=session_id, new_status=new_status)

        return {
            "success": True,
            "is_bookmarked": new_status,
            "message": "已收藏" if new_status else "已取消收藏"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("toggle_bookmark_failed", error=str(e), session_id=session_id)
        raise HTTPException(status_code=500, detail=f"Failed to toggle bookmark: {str(e)}")


@router.put("/{session_id}/notes")
async def update_notes(
    session_id: str,
    notes: str = Body(..., embed=True, description="备注内容")
):
    """
    更新备注

    为历史记录添加或修改备注。
    """
    try:
        updated = await history_service.update_notes(session_id, notes)

        if not updated:
            raise HTTPException(status_code=404, detail=f"History record not found: {session_id}")

        logger.info("notes_updated_via_api", session_id=session_id)

        return {
            "success": True,
            "message": "Notes updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_notes_failed", error=str(e), session_id=session_id)
        raise HTTPException(status_code=500, detail=f"Failed to update notes: {str(e)}")


@router.post("/save")
async def manual_save_history(
    session_id: str = Body(..., embed=True, description="会话ID"),
    force_save: bool = Body(False, embed=True, description="强制保存标志")
):
    """
    手动保存当前会话到历史记录

    用于前端手动触发保存操作，支持调试和测试。

    注意：
    - 如果记录已存在，返回"已存在"提示
    - 如果记录不存在，返回404错误（分析完成时应自动保存）
    - 不再支持从会话缓存中补救保存（老架构已移除）
    """
    try:
        logger.info("manual_save_requested", session_id=session_id, force_save=force_save)

        # 检查session_id是否有效
        if not session_id or session_id == "null":
            raise HTTPException(
                status_code=400,
                detail="无效的会话ID：session_id不能为空"
            )

        # 尝试获取现有记录
        existing_record = await history_service.get_by_session_id(session_id)

        if existing_record:
            logger.info(
                "manual_save_record_exists",
                session_id=session_id,
                created_at=existing_record.get("created_at")
            )
            return {
                "success": True,
                "message": "该会话已存在于历史记录中",
                "session_id": session_id,
                "record_id": existing_record.get("id"),
                "created_at": existing_record.get("created_at"),
                "already_exists": True
            }

        # 记录不存在
        logger.warning(
            "manual_save_record_not_found",
            session_id=session_id,
            hint="历史记录不存在。分析完成时应自动保存到历史记录。"
        )
        raise HTTPException(
            status_code=404,
            detail=f"未找到会话：{session_id}。该会话的历史记录不存在。正常情况下，分析完成时会自动保存到历史记录。请检查分析是否成功完成，或重新进行分析。"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("manual_save_failed", error=str(e), session_id=session_id, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"手动保存失败: {str(e)}"
        )


@router.get("/stats/summary")
async def get_stats_summary():
    """
    获取统计摘要

    返回历史记录的统计信息：
    - 总记录数
    - 站点分析数
    - 城市分析数
    - 各污染物分析次数
    """
    try:
        # 获取所有记录
        all_records = await history_service.get_history_list(limit=10000, offset=0)

        total = all_records["total"]
        records = all_records["records"]

        # 统计
        station_count = sum(1 for r in records if r["scale"] == "station")
        city_count = sum(1 for r in records if r["scale"] == "city")

        pollutant_stats = {}
        for r in records:
            if r["pollutant"]:
                pollutant_stats[r["pollutant"]] = pollutant_stats.get(r["pollutant"], 0) + 1

        return {
            "total": total,
            "station_count": station_count,
            "city_count": city_count,
            "pollutant_stats": pollutant_stats,
            "recent_analyses": records[:10]  # 最近10条
        }

    except Exception as e:
        logger.error("get_stats_summary_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get stats summary: {str(e)}")

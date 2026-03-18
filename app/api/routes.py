"""API routes - Basic configuration endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import structlog
import asyncio

from config.settings import settings
from app.services.lifecycle_manager import get_fetcher_scheduler

logger = structlog.get_logger()

router = APIRouter()


class ConfigResponse(BaseModel):
    """Response model for config endpoint."""

    amapPublicKey: Optional[str] = None
    features: dict = {}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "air-pollution-traceability-api",
        "version": "1.0.0",
    }


@router.options("/config")
async def config_options():
    """Handle OPTIONS preflight request for /config endpoint."""
    return {}


@router.get("/config")
async def get_config():
    """Get frontend configuration."""
    return ConfigResponse(
        amapPublicKey=settings.amap_public_key,
        features={
            "streaming": True,
            "realtime_progress": True,
        },
    )


# =============== Fetchers 管理 API ===============

@router.get("/system/status")
async def get_system_status():
    """
    获取系统状态信息

    包括：
    - Fetchers运行状态
    - LLM Tools注册情况
    - 数据库连接状态
    """
    try:
        from app.services.lifecycle_manager import get_fetcher_scheduler, get_tool_registry

        status = {
            "service": "air-pollution-traceability-api",
            "version": "1.0.0",
        }

        # 数据库状态
        import os
        if os.getenv("DATABASE_URL"):
            status["database"] = {
                "enabled": True,
                "url": os.getenv("DATABASE_URL").split("@")[1] if "@" in os.getenv("DATABASE_URL", "") else "configured"
            }
        else:
            status["database"] = {"enabled": False}

        # Fetchers状态
        try:
            scheduler = get_fetcher_scheduler()
            status["fetchers"] = scheduler.get_status()
        except Exception as e:
            status["fetchers"] = {"error": str(e)}

        # Tools状态
        try:
            registry = get_tool_registry()
            status["llm_tools"] = {
                "registered": registry.list_tools(),
                "count": len(registry.list_tools()),
                "statistics": registry.get_stats()
            }
        except Exception as e:
            status["llm_tools"] = {"error": str(e)}

        return status

    except Exception as e:
        logger.error("system_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")


@router.post("/fetchers/trigger/{fetcher_name}")
async def trigger_fetcher(fetcher_name: str):
    """
    手动触发指定Fetcher
    """
    try:
        scheduler = get_fetcher_scheduler()
        await scheduler.run_now(fetcher_name)
        return {
            "success": True,
            "message": f"Fetcher '{fetcher_name}' triggered successfully"
        }
    except Exception as e:
        logger.error("trigger_fetcher_failed", fetcher=fetcher_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to trigger fetcher: {str(e)}")


@router.post("/fetchers/pause/{fetcher_name}")
async def pause_fetcher(fetcher_name: str):
    """
    暂停指定Fetcher
    """
    try:
        scheduler = get_fetcher_scheduler()
        scheduler.pause(fetcher_name)
        return {
            "success": True,
            "message": f"Fetcher '{fetcher_name}' paused successfully"
        }
    except Exception as e:
        logger.error("pause_fetcher_failed", fetcher=fetcher_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to pause fetcher: {str(e)}")


@router.post("/fetchers/resume/{fetcher_name}")
async def resume_fetcher(fetcher_name: str):
    """
    恢复指定Fetcher
    """
    try:
        scheduler = get_fetcher_scheduler()
        scheduler.resume(fetcher_name)
        return {
            "success": True,
            "message": f"Fetcher '{fetcher_name}' resumed successfully"
        }
    except Exception as e:
        logger.error("resume_fetcher_failed", fetcher=fetcher_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to resume fetcher: {str(e)}")


# =============== ERA5 历史数据补采 API ===============

class ERA5HistoricalFetchRequest(BaseModel):
    """ERA5历史数据补采请求"""
    date: str  # 日期字符串 (YYYY-MM-DD)


@router.post("/fetchers/era5/historical")
async def fetch_era5_historical(request: ERA5HistoricalFetchRequest):
    """
    手动触发ERA5历史数据补采

    用于补采指定日期的ERA5气象数据（广东省全境825个网格点）
    """
    try:
        from app.fetchers.weather.era5_fetcher import ERA5Fetcher
        from datetime import datetime

        # 验证日期格式
        try:
            target_date = datetime.strptime(request.date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        # 不能选择未来日期
        if target_date.date() > datetime.now().date():
            raise HTTPException(status_code=400, detail="Cannot fetch data for future dates")

        # 创建 fetcher 实例并执行
        fetcher = ERA5Fetcher()
        result = await fetcher.fetch_and_store_for_date(request.date)

        if result.get("success"):
            return {
                "success": True,
                "message": f"ERA5 data fetched successfully for {request.date}",
                "data": result
            }
        else:
            return {
                "success": False,
                "message": f"ERA5 data fetch completed with errors for {request.date}",
                "data": result
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("era5_historical_fetch_failed", date=request.date, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch ERA5 historical data: {str(e)}")


# =============== 济宁市 ERA5 数据抓取 API ===============

class JiningERA5FetchRequest(BaseModel):
    """济宁市ERA5数据抓取请求"""
    date: str  # 日期字符串 (YYYY-MM-DD)
    station_id: Optional[str] = None  # 站点ID（可选，如 "11149A"）


@router.post("/fetchers/jining_era5/fetch")
async def fetch_jining_era5(request: JiningERA5FetchRequest):
    """
    手动触发济宁市ERA5数据抓取

    支持两种模式：
    1. 指定站点ID：仅抓取该站点的数据
    2. 不指定站点ID：抓取所有站点 + 市中心点的数据（共7个点）
    """
    try:
        from app.fetchers.weather.jining_era5_fetcher import JiningERA5Fetcher
        from datetime import datetime

        # 验证日期格式
        try:
            target_date = datetime.strptime(request.date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        # 不能选择未来日期
        if target_date.date() > datetime.now().date():
            raise HTTPException(status_code=400, detail="Cannot fetch data for future dates")

        # 创建 fetcher 实例
        fetcher = JiningERA5Fetcher()

        # 如果指定了站点ID，只抓取该站点
        if request.station_id:
            result = await fetcher.fetch_station_data(request.station_id, request.date)

            if result.get("success"):
                return {
                    "success": True,
                    "message": f"Jining station {request.station_id} ERA5 data fetched successfully for {request.date}",
                    "data": result
                }
            else:
                return {
                    "success": False,
                    "message": f"Jining station {request.station_id} ERA5 data fetch failed for {request.date}",
                    "data": result
                }
        else:
            # 抓取所有数据（站点 + 市中心）
            result = await fetcher.fetch_and_store_for_date(request.date)

            if result.get("success"):
                return {
                    "success": True,
                    "message": f"Jining ERA5 data fetched successfully for {request.date}",
                    "data": result
                }
            else:
                return {
                    "success": False,
                    "message": f"Jining ERA5 data fetch completed with errors for {request.date}",
                    "data": result
                }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("jining_era5_fetch_failed", date=request.date, station_id=request.station_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch Jining ERA5 data: {str(e)}")


@router.get("/fetchers/jining_era5/stations")
async def list_jining_stations():
    """
    获取济宁市监测站点列表和市中心点
    """
    try:
        from app.fetchers.weather.jining_era5_fetcher import JiningERA5Fetcher

        fetcher = JiningERA5Fetcher()

        stations = []
        for station_id, info in fetcher.stations.items():
            stations.append({
                "station_id": station_id,
                "name": info["name"],
                "lat": info["lat"],
                "lon": info["lon"]
            })

        # 添加市中心点
        city_center = {
            "station_id": "CITY_CENTER",
            "name": fetcher.city_center["name"],
            "lat": fetcher.city_center["lat"],
            "lon": fetcher.city_center["lon"]
        }

        return {
            "success": True,
            "station_count": len(stations),
            "city_center": city_center,
            "stations": stations
        }

    except Exception as e:
        logger.error("list_jining_stations_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list Jining stations: {str(e)}")

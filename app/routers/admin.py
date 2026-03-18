"""
Admin API endpoints for workflow visualization and configuration.
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from pydantic import BaseModel
from app.config.config_manager import config_manager
import structlog

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = structlog.get_logger()


class ConfigValueUpdate(BaseModel):
    """Configuration value update request."""
    value: Any


class WorkflowStep(BaseModel):
    """Workflow step definition."""
    id: str
    name: str
    description: str
    status: str = "pending"
    depends_on: List[str] = []


@router.get("/workflow")
async def get_workflow() -> Dict[str, Any]:
    """
    Get the complete analysis workflow structure.
    """
    workflow_steps = [
        {
            "id": "1_param_extraction",
            "name": "参数提取",
            "description": "使用LLM从用户查询中提取分析参数（地点、时间、污染物等）",
            "type": "llm",
            "prompt_key": "parameter_extraction",
            "depends_on": [],
            "outputs": ["location", "city", "pollutant", "start_time", "end_time"]
        },
        {
            "id": "2_station_info",
            "name": "站点信息查询",
            "description": "根据站点名称获取详细的地理信息和行政区划",
            "type": "api",
            "api_url": "STATION_API_BASE_URL/api/station-district/by-station-name",
            "depends_on": ["1_param_extraction"],
            "outputs": ["station_code", "lat", "lng", "city", "district"]
        },
        {
            "id": "3_nearby_stations",
            "name": "附近站点查询",
            "description": "查询周边站点用于区域对比分析",
            "type": "api",
            "api_url": "STATION_API_BASE_URL/api/nearest-stations/by-station-name",
            "depends_on": ["2_station_info"],
            "outputs": ["nearby_stations"]
        },
        {
            "id": "4_parallel_data",
            "name": "并行数据获取",
            "description": "同时获取多种监测数据（污染物浓度、气象数据等）",
            "type": "parallel",
            "depends_on": ["2_station_info"],
            "substeps": [
                {
                    "id": "4a_pollutant_data",
                    "name": "污染物浓度数据",
                    "api_url": "MONITORING_DATA_API_URL/api/uqp/query",
                    "description": "获取目标站点的小时污染物浓度数据"
                },
                {
                    "id": "4b_weather_data",
                    "name": "气象数据",
                    "api_url": "METEOROLOGICAL_API_URL",
                    "description": "获取风速、风向、温度、湿度等气象数据"
                },
                {
                    "id": "4c_nearby_pollutant",
                    "name": "周边站点数据",
                    "api_url": "MONITORING_DATA_API_URL/api/uqp/query",
                    "description": "获取周边站点的污染物数据用于对比"
                }
            ]
        },
        {
            "id": "5_upwind_analysis",
            "name": "上风向企业识别",
            "description": "基于风向数据筛选上风向企业，生成地图",
            "type": "api",
            "api_url": "UPWIND_ANALYSIS_API_URL/api/external/wind/upwind-and-map",
            "depends_on": ["4_parallel_data"],
            "outputs": ["enterprises", "map_url", "top_enterprises"]
        },
        {
            "id": "6_component_analysis",
            "name": "组分数据分析",
            "description": "根据污染物类型获取VOCs或颗粒物组分数据",
            "type": "conditional",
            "depends_on": ["4_parallel_data"],
            "conditions": {
                "O3": {
                    "id": "6a_vocs",
                    "name": "VOCs组分分析",
                    "api_url": "VOCS_DATA_API_URL/api/uqp/query",
                    "note": "Prompt is hardcoded in llm_service.py for performance"
                },
                "PM2.5|PM10": {
                    "id": "6b_particulate",
                    "name": "颗粒物组分分析",
                    "api_url": "PARTICULATE_DATA_API_URL/api/uqp/query",
                    "note": "Prompt is hardcoded in llm_service.py for performance"
                }
            }
        },
        {
            "id": "7_llm_source_analysis",
            "name": "LLM污染源分析",
            "description": "使用LLM基于组分数据和企业信息进行污染源解析（提示词已内联优化）",
            "type": "llm",
            "depends_on": ["5_upwind_analysis", "6_component_analysis"],
            "note": "Prompts are hardcoded in llm_service.py for better performance and maintainability"
        },
        {
            "id": "8_comprehensive_synthesis",
            "name": "综合分析总结",
            "description": "整合所有分析结果，生成综合溯源报告（提示词已内联优化）",
            "type": "llm",
            "depends_on": ["7_llm_source_analysis"],
            "outputs": ["comprehensive_report"],
            "note": "Prompt is hardcoded in llm_service.py for better performance and maintainability"
        },
        {
            "id": "9_visualization",
            "name": "可视化生成",
            "description": "生成ECharts图表配置和地图标注",
            "type": "processing",
            "depends_on": ["8_comprehensive_synthesis"],
            "outputs": ["charts", "maps"]
        }
    ]

    return {
        "workflow_name": "大气污染溯源分析工作流",
        "version": "1.0.0",
        "total_steps": len(workflow_steps),
        "steps": workflow_steps,
        "description": "从用户查询到生成完整溯源报告的端到端分析流程"
    }


@router.get("/config")
async def get_system_config() -> Dict[str, Any]:
    """
    Get current system configuration (API endpoints, LLM settings, etc.).
    """
    from config.settings import settings

    return {
        "server": {
            "host": settings.host,
            "port": settings.port,
            "environment": settings.environment,
            "debug": settings.debug
        },
        "llm": {
            "provider": settings.llm_provider,
            "model": getattr(settings, f"{settings.llm_provider}_model", "unknown")
        },
        "apis": {
            "station_api": settings.station_api_base_url,
            "monitoring_api": settings.monitoring_data_api_url,
            "vocs_api": settings.vocs_data_api_url,
            "particulate_api": settings.particulate_data_api_url,
            "meteorological_api": settings.meteorological_api_url,
            "upwind_api": settings.upwind_analysis_api_url
        },
        "analysis": {
            "search_range_km": settings.default_search_range_km,
            "max_enterprises": settings.default_max_enterprises,
            "top_n_enterprises": settings.default_top_n_enterprises
        },
        "retry": {
            "max_retries": settings.max_retries,
            "retry_interval_ms": settings.retry_interval_ms,
            "request_timeout_seconds": settings.request_timeout_seconds
        }
    }


@router.get("/config/all")
async def get_all_editable_config() -> Dict[str, Any]:
    """
    Get all editable configuration (from config_manager).
    """
    return config_manager.get_all_config()


@router.get("/config/section/{section_name}")
async def get_config_section(section_name: str) -> Dict[str, Any]:
    """
    Get a specific configuration section.
    """
    section = config_manager.get_section(section_name)
    if not section:
        raise HTTPException(status_code=404, detail=f"Section '{section_name}' not found")
    return section


@router.put("/config/{section_name}/{key}")
async def update_config_value(section_name: str, key: str, update: ConfigValueUpdate) -> Dict[str, Any]:
    """
    Update a specific configuration value.
    """
    success = config_manager.update_value(section_name, key, update.value)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Configuration '{section_name}.{key}' not found or invalid"
        )

    logger.info("config_updated", section=section_name, key=key, value=update.value)
    return {
        "success": True,
        "message": f"Configuration '{section_name}.{key}' updated successfully",
        "value": update.value
    }


@router.post("/config/reset")
async def reset_config() -> Dict[str, Any]:
    """
    Reset all configuration to default values.
    """
    success = config_manager.reset_to_defaults()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to reset configuration")

    logger.warning("config_reset_to_defaults")
    return {
        "success": True,
        "message": "All configuration reset to defaults"
    }


@router.post("/config/reload")
async def reload_config() -> Dict[str, Any]:
    """
    Force reload configuration from defaults (deletes old config file and recreates).
    Useful when DEFAULT_CONFIG structure has changed.
    """
    import os

    # Delete old config file
    if config_manager.config_file.exists():
        try:
            os.remove(config_manager.config_file)
            logger.info("old_config_file_deleted", file=str(config_manager.config_file))
        except Exception as e:
            logger.error("config_file_delete_failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to delete old config: {str(e)}")

    # Reload from defaults
    config_manager.config = config_manager._load_config()
    success = config_manager.save_config()

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save reloaded configuration")

    logger.warning("config_force_reloaded", sections=len(config_manager.config))
    return {
        "success": True,
        "message": "Configuration reloaded from defaults",
        "sections": len(config_manager.config),
        "config": config_manager.get_all_config()
    }


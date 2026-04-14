"""
全局调度器和生命周期管理

统一管理Fetchers和LLM Tools的生命周期
注意：工具注册已迁移到 app.tools.__init__.py 的 global_tool_registry
此处仅负责初始化和提供访问接口
"""
from app.fetchers.base.scheduler import FetcherScheduler
from app.fetchers.weather.era5_fetcher import ERA5Fetcher
from app.fetchers.weather.observed_fetcher import ObservedWeatherFetcher
from app.fetchers.weather.jining_era5_fetcher import JiningERA5Fetcher
from app.fetchers.satellite.nasa_firms_fetcher import NASAFirmsFetcher
from app.fetchers.dust.cams_dust_fetcher import CAMSDustFetcher
from app.fetchers.city_statistics import CityStatisticsFetcher, CityStatisticsOldStandardFetcher, ProvinceStatisticsFetcher, ProvinceStatisticsOldStandardFetcher  # 168城市和省级统计（新旧标准）
# 导入单一工具注册源
from app.tools import global_tool_registry

import structlog
import os

logger = structlog.get_logger()

# 全局实例
fetcher_scheduler = FetcherScheduler()
# 注意：不再创建独立的 tool_registry，统一使用 global_tool_registry


def initialize_fetchers():
    """
    初始化并启动数据获取后台

    注册所有Fetchers并启动调度器
    """
    try:
        # 注册Weather Fetchers
        fetcher_scheduler.register(ERA5Fetcher())
        fetcher_scheduler.register(ObservedWeatherFetcher())
        fetcher_scheduler.register(JiningERA5Fetcher())  # 济宁市 ERA5 Fetcher

        # 注册Satellite Fetchers
        fetcher_scheduler.register(NASAFirmsFetcher())

        # 注册Dust Fetchers
        fetcher_scheduler.register(CAMSDustFetcher())

        # 注册168城市统计Fetcher（新标准）
        fetcher_scheduler.register(CityStatisticsFetcher())

        # 注册168城市统计Fetcher（旧标准）
        fetcher_scheduler.register(CityStatisticsOldStandardFetcher())

        # 注册省级统计Fetcher（新标准）
        fetcher_scheduler.register(ProvinceStatisticsFetcher())

        # 注册省级统计Fetcher（旧标准）
        fetcher_scheduler.register(ProvinceStatisticsOldStandardFetcher())

        logger.info(
            "fetchers_registered",
            fetchers=fetcher_scheduler.list_fetchers()
        )

        # 启动调度器
        fetcher_scheduler.start()

        logger.info("fetcher_scheduler_started")

    except Exception as e:
        logger.error("fetchers_initialization_failed", error=str(e), exc_info=True)
        raise


def stop_fetchers():
    """
    停止数据获取后台
    """
    try:
        if fetcher_scheduler.is_running():
            fetcher_scheduler.stop()
            logger.info("fetcher_scheduler_stopped")
    except Exception as e:
        logger.error("fetchers_stop_failed", error=str(e))


def initialize_llm_tools():
    """
    初始化LLM工具

    注意：工具注册已迁移到 app.tools.__init__.py
    此处仅验证注册表状态和准备 Function Schemas
    """
    try:
        # 验证 global_tool_registry 状态
        tools = global_tool_registry.list_tools()
        if not tools:
            logger.warning(
                "global_tool_registry_empty",
                message="global_tool_registry 为空，工具可能未正确注册"
            )
        else:
            logger.info(
                "llm_tools_status",
                tools=tools,
                count=len(tools)
            )

        # 获取所有工具的Function Calling schemas
        schemas = global_tool_registry.get_function_schemas()
        logger.info(
            "function_schemas_prepared",
            count=len(schemas)
        )

        # 验证工具合规性
        for tool_name in tools:
            compliance = global_tool_registry.validate_tool_compliance(tool_name)
            if not compliance["valid"]:
                logger.error(
                    "tool_compliance_failed",
                    tool=tool_name,
                    errors=compliance["errors"]
                )

    except Exception as e:
        logger.error("tools_initialization_failed", error=str(e), exc_info=True)
        raise


def get_tool_registry():
    """
    获取全局工具注册表实例

    Returns:
        global_tool_registry: 单一工具注册源
    """
    return global_tool_registry


def get_fetcher_scheduler() -> FetcherScheduler:
    """
    获取全局Fetcher调度器实例

    Returns:
        FetcherScheduler: 全局调度器
    """
    return fetcher_scheduler

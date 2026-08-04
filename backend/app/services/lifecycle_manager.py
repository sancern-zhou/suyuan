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
from app.fetchers.weather.nmc_observed_fetcher import NMCObservedWeatherFetcher
from app.fetchers.weather.open_meteo_air_quality_forecast_fetcher import (
    OpenMeteoAirQualityForecastFetcher,
)
from app.fetchers.xuchang_daily_attainment_forecast import XuchangDailyAttainmentForecastFetcher
from app.fetchers.xuchang_annual_attainment_forecast import XuchangAnnualAttainmentForecastFetcher
from app.fetchers.satellite.nasa_firms_fetcher import NASAFirmsFetcher
from app.fetchers.satellite.gems_image_fetcher import GemsImageFetcher
from app.fetchers.satellite.gems_hcho_data_fetcher import GemsHchoDataFetcher
from app.fetchers.dust.cams_dust_fetcher import CAMSDustFetcher
from app.fetchers.air_quality_data_quality_monitor import AirQualityDataQualityFetcher  # 空气质量数据质量巡检
from app.fetchers.city_pollution_event_monitor import CityPollutionEventFetcher  # 城市污染过程告警
from app.fetchers.tenders import TenderInformationFetcher  # 招投标信息每日抓取
from app.fetchers.quick_trace import JiningQuickTraceFetcher  # 济宁市快速溯源报告每日生成
from app.fetchers.yuncheng_trial import YunchengTrialFetcher  # 运城市驻场试用场景小时数据盯守
from app.fetchers.consultation import ConsultationFileFetcher, MonthlyConsultationFileFetcher  # 会商文件批量更新、月度完整会商文件
from app.fetchers.consultation.annual_ytd import AnnualYtdConsultationFileFetcher  # 年度累计会商文件
from app.fetchers.consultation.monthly_supplement_fetchers import (
    MonthlyDistrictPollutantRankingFetcher,
    MonthlyMeteorologySupportFetcher,
    MonthlyPollutionEventsComponentsFetcher,
    MonthlyStationHighValuesFetcher,
)
# 导入单一工具注册源
from app.tools import global_tool_registry
from app.project_config.loader import load_project_context
from config.settings import settings

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
        raw_allowlist = os.getenv("FETCHER_ALLOWLIST", "").strip()
        allowlist = {
            name.strip() for name in raw_allowlist.split(",") if name.strip()
        }

        def register(fetcher):
            if allowlist and fetcher.name not in allowlist:
                logger.info(
                    "fetcher_skipped_by_allowlist",
                    fetcher=fetcher.name,
                )
                return
            fetcher_scheduler.register(fetcher)

        # 注册Weather Fetchers
        register(ERA5Fetcher())
        register(ObservedWeatherFetcher())
        register(JiningERA5Fetcher())  # 济宁市 ERA5 Fetcher
        register(NMCObservedWeatherFetcher())  # 许昌、运城NMC小时实况
        register(OpenMeteoAirQualityForecastFetcher())  # 运城、许昌未来72小时空气质量预报
        register(XuchangDailyAttainmentForecastFetcher())  # 许昌市日达标预测分析
        register(XuchangAnnualAttainmentForecastFetcher())  # 许昌市年度达标预测分析

        # 注册Satellite Fetchers
        register(NASAFirmsFetcher())
        enabled_modules = load_project_context(settings.project_id).enabled_modules
        if "xuchang-satellite" in enabled_modules:
            register(GemsImageFetcher())
            if os.getenv("GEMS_HCHO_DATA_FETCH_ENABLED", "false").lower() == "true":
                register(GemsHchoDataFetcher())

        # 注册Dust Fetchers
        register(CAMSDustFetcher())

        # 注册空气质量数据质量巡检Fetcher
        register(AirQualityDataQualityFetcher())

        # 注册城市污染过程告警Fetcher
        register(CityPollutionEventFetcher())

        # 注册招投标信息每日抓取Fetcher
        register(TenderInformationFetcher())

        # 注册济宁市快速溯源报告每日生成Fetcher
        register(JiningQuickTraceFetcher())

        # 注册运城市驻场试用场景小时数据盯守Fetcher
        register(YunchengTrialFetcher())

        # 注册会商文件批量更新Fetcher
        register(ConsultationFileFetcher())

        # 注册月度完整会商文件Fetcher（每月4号早上7点10分）
        register(MonthlyConsultationFileFetcher())

        # 注册年度累计会商文件Fetcher（每月4号早上7点20分）
        register(AnnualYtdConsultationFileFetcher())

        # 注册月度补充数据Fetcher（每月4号早上7点30-50分）
        register(MonthlyDistrictPollutantRankingFetcher())
        register(MonthlyStationHighValuesFetcher())
        register(MonthlyPollutionEventsComponentsFetcher())
        register(MonthlyMeteorologySupportFetcher())

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

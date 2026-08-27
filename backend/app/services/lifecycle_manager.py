"""
全局调度器和生命周期管理

统一管理Fetchers和LLM Tools的生命周期
注意：工具注册已迁移到 app.tools.__init__.py 的 global_tool_registry
此处仅负责初始化和提供访问接口
"""
import os

import structlog

from app.fetchers.air_quality_data_quality_monitor import (
    AirQualityDataQualityFetcher,  # 空气质量数据质量巡检
)
from app.fetchers.base.scheduler import FetcherScheduler
from app.fetchers.city_pollution_event_monitor import CityPollutionEventFetcher  # 城市污染过程告警
from app.fetchers.consultation import (  # 会商文件批量更新、月度完整会商文件
    ConsultationFileFetcher,
    MonthlyConsultationFileFetcher,
)
from app.fetchers.consultation.annual_ytd import (
    AnnualYtdConsultationFileFetcher,  # 年度累计会商文件
)
from app.fetchers.consultation.monthly_supplement_fetchers import (
    MonthlyDistrictPollutantRankingFetcher,
    MonthlyMeteorologySupportFetcher,
    MonthlyPollutionEventsComponentsFetcher,
    MonthlyStationHighValuesFetcher,
)
from app.fetchers.dust.cams_dust_fetcher import CAMSDustFetcher
from app.fetchers.fault_diagnosis import FaultDiagnosisFetcher
from app.fetchers.quick_trace import JiningQuickTraceFetcher  # 济宁市快速溯源报告每日生成
from app.fetchers.satellite.gems_hcho_data_fetcher import GemsHchoDataFetcher
from app.fetchers.satellite.gems_image_fetcher import GemsImageFetcher
from app.fetchers.satellite.nasa_firms_fetcher import NASAFirmsFetcher
from app.fetchers.tenders import TenderInformationFetcher  # 招投标信息每日抓取
from app.fetchers.weather.era5_fetcher import ERA5Fetcher
from app.fetchers.weather.jining_era5_fetcher import JiningERA5Fetcher
from app.fetchers.weather.nmc_observed_fetcher import NMCObservedWeatherFetcher
from app.fetchers.weather.nmc_weather_chart_fetcher import NMCWeatherChartFetcher
from app.fetchers.weather.observed_fetcher import ObservedWeatherFetcher
from app.fetchers.weather.open_meteo_air_quality_forecast_fetcher import (
    OpenMeteoAirQualityForecastFetcher,
)
from app.fetchers.yuncheng_trial import YunchengTrialFetcher  # 运城市驻场试用场景小时数据盯守
from app.fetchers.xuchang_annual_attainment_forecast import XuchangAnnualAttainmentForecastFetcher
from app.fetchers.xuchang_cnemc_station_hour import XuchangCnemcStationHourFetcher
from app.fetchers.xuchang_daily_attainment_forecast import XuchangDailyAttainmentForecastFetcher
from app.fetchers.xuchang_henan_month_year_accumulate import XuchangHenanMonthYearAccumulateFetcher
from app.fetchers.xuchang_station_deviation_alert import XuchangStationDeviationAlertFetcher
from app.fetchers.xuchang_station_daily_pollution import XuchangStationDailyPollutionFetcher
from app.fetchers.xuchang_transport_analysis import XuchangTransportAnalysisFetcher
from app.fetchers.xuchang_zhongda_station import (
    XuchangZhongdaCityFetcher,
    XuchangZhongdaStationFetcher,
)
from app.project_config.loader import load_project_context

# 导入单一工具注册源
from app.tools import global_tool_registry
from config.settings import settings

logger = structlog.get_logger()

# 全局实例
fetcher_scheduler = FetcherScheduler()
# 注意：不再创建独立的 tool_registry，统一使用 global_tool_registry


def initialize_fetchers() -> bool:
    """
    初始化并启动数据获取后台

    注册所有Fetchers并启动调度器
    """
    try:
        project_context = load_project_context(settings.project_id)
        if not project_context.manifest.backend.fetchers_enabled:
            logger.info(
                "fetchers_disabled_by_project",
                project=settings.project_id,
            )
            return False

        # An omitted list retains the legacy deployment behaviour.  A project
        # can instead declare an explicit (including empty) fetcher allowlist.
        fetchers = _configured_fetchers(project_context)
        for fetcher in fetchers:
            fetcher_scheduler.register(fetcher)

        logger.info(
            "fetchers_registered",
            fetchers=fetcher_scheduler.list_fetchers(),
            project=settings.project_id,
        )

        # 启动调度器
        fetcher_scheduler.start()

        logger.info("fetcher_scheduler_started")
        return True

    except Exception as e:
        logger.error("fetchers_initialization_failed", error=str(e), exc_info=True)
        raise


def _configured_fetchers(project_context):
    """Instantiate only fetchers declared by a project manifest."""
    enabled_modules = project_context.enabled_modules
    factories = {
        "era5": ERA5Fetcher,
        "observed_weather": ObservedWeatherFetcher,
        "jining_era5": JiningERA5Fetcher,
        "nmc_observed_weather": NMCObservedWeatherFetcher,
        "nmc_weather_chart": NMCWeatherChartFetcher,
        "open_meteo_air_quality_forecast": OpenMeteoAirQualityForecastFetcher,
        "nasa_firms": NASAFirmsFetcher,
        "cams_dust": CAMSDustFetcher,
        "air_quality_data_quality_monitor": AirQualityDataQualityFetcher,
        "city_pollution_event_monitor": CityPollutionEventFetcher,
        "tender_information": TenderInformationFetcher,
        "jining_quick_trace": JiningQuickTraceFetcher,
        "yuncheng_trial": YunchengTrialFetcher,
        "consultation": ConsultationFileFetcher,
        "monthly_consultation": MonthlyConsultationFileFetcher,
        "annual_ytd_consultation": AnnualYtdConsultationFileFetcher,
        "monthly_district_pollutant_ranking": MonthlyDistrictPollutantRankingFetcher,
        "monthly_station_high_values": MonthlyStationHighValuesFetcher,
        "monthly_pollution_events_components": MonthlyPollutionEventsComponentsFetcher,
        "monthly_meteorology_support": MonthlyMeteorologySupportFetcher,
        "fault_diagnosis": FaultDiagnosisFetcher,
        "xuchang_daily_attainment_forecast_fetcher": XuchangDailyAttainmentForecastFetcher,
        "xuchang_annual_attainment_forecast_fetcher": XuchangAnnualAttainmentForecastFetcher,
        "xuchang_cnemc_station_hour_fetcher": XuchangCnemcStationHourFetcher,
        "xuchang_henan_month_year_accumulate_fetcher": XuchangHenanMonthYearAccumulateFetcher,
        "xuchang_station_deviation_alert_fetcher": XuchangStationDeviationAlertFetcher,
        "xuchang_station_daily_pollution_fetcher": XuchangStationDailyPollutionFetcher,
        "xuchang_transport_analysis_fetcher": XuchangTransportAnalysisFetcher,
        "xuchang_zhongda_station_minute_fetcher": XuchangZhongdaStationFetcher,
        "xuchang_zhongda_station_hour_fetcher":
            lambda: XuchangZhongdaStationFetcher(data_kind="hour"),
        "xuchang_zhongda_station_day_fetcher":
            lambda: XuchangZhongdaStationFetcher(data_kind="day"),
        "xuchang_zhongda_city_hour_fetcher": XuchangZhongdaCityFetcher,
        "xuchang_zhongda_city_day_fetcher":
            lambda: XuchangZhongdaCityFetcher(data_kind="city_day"),
        "gems_xuchang_image_fetcher": GemsImageFetcher,
    }
    configured = project_context.manifest.backend.fetchers
    if configured is None:
        selected = list(factories)
        if "xuchang-satellite" in enabled_modules:
            selected.append("gems_image")
            if os.getenv("GEMS_HCHO_DATA_FETCH_ENABLED", "false").lower() == "true":
                selected.append("gems_hcho_data")
            factories["gems_image"] = GemsImageFetcher
            factories["gems_hcho_data"] = GemsHchoDataFetcher
    else:
        selected = configured

    unknown = [name for name in selected if name not in factories]
    if unknown:
        raise ValueError("unknown project fetchers: " + ", ".join(unknown))
    return [factories[name]() for name in selected]


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

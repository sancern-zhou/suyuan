"""
全局调度器和生命周期管理

统一管理Fetchers和LLM Tools的生命周期
注意：工具注册已迁移到 app.tools.__init__.py 的 global_tool_registry
此处仅负责初始化和提供访问接口
"""
import os

import structlog

from app.fetchers.base.scheduler import FetcherScheduler
from app.fetchers.consultation import (  # 会商文件批量更新、月度完整会商文件
    ConsultationFileFetcher,
    MonthlyConsultationFileFetcher,
)
from app.fetchers.consultation.annual_ytd import (
    AnnualYtdConsultationFileFetcher,  # 年度累计会商文件
)
from app.fetchers.satellite.gems_hcho_data_fetcher import GemsHchoDataFetcher
from app.fetchers.satellite.gems_image_fetcher import GemsImageFetcher
from app.fetchers.weather.nmc_observed_fetcher import NMCObservedWeatherFetcher
from app.fetchers.weather.observed_daily_fetcher import ObservedWeatherDailyFetcher
from app.fetchers.weather.observed_fetcher import ObservedWeatherFetcher
from app.fetchers.xuchang_annual_attainment_forecast import XuchangAnnualAttainmentForecastFetcher
from app.fetchers.xuchang_cnemc_station_hour import XuchangCnemcStationHourFetcher
from app.fetchers.xuchang_city_exceedance import XuchangCityExceedanceFetcher
from app.fetchers.xuchang_daily_attainment_forecast import XuchangDailyAttainmentForecastFetcher
from app.fetchers.xuchang_henan_month_year_accumulate import XuchangHenanMonthYearAccumulateFetcher
from app.fetchers.xuchang_nmc_hourly_forecast import XuchangNmcHourlyForecastFetcher
from app.fetchers.xuchang_station_daily_exceedance import XuchangStationDailyExceedanceFetcher
from app.fetchers.xuchang_station_daily_pollution import XuchangStationDailyPollutionFetcher
from app.fetchers.xuchang_station_deviation_alert import XuchangStationDeviationAlertFetcher
from app.fetchers.xuchang_transport_analysis import XuchangTransportAnalysisFetcher
from app.fetchers.xuchang_weather_com_daily_forecast import XuchangWeatherComDailyForecastFetcher
from app.fetchers.xuchang_weather_situation import (
    XuchangWeatherSituationEvidenceFetcher,
)
from app.fetchers.xuchang_town_five_minute import XuchangTownFiveMinuteFetcher
from app.fetchers.xuchang_zhongda_station import (
    XuchangZhongdaCityFetcher,
    XuchangZhongdaStationFetcher,
)
from app.project_config.loader import load_project_context
from app.fetchers.task_review_feedback import TaskReviewFeedbackFetcher

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
        "task_review_feedback": TaskReviewFeedbackFetcher,
        "observed_weather": ObservedWeatherFetcher,
        "nmc_observed_weather": NMCObservedWeatherFetcher,
        "observed_weather_daily": ObservedWeatherDailyFetcher,
        "consultation": ConsultationFileFetcher,
        "monthly_consultation": MonthlyConsultationFileFetcher,
        "annual_ytd_consultation": AnnualYtdConsultationFileFetcher,
        "xuchang_daily_attainment_forecast_fetcher": XuchangDailyAttainmentForecastFetcher,
        "xuchang_annual_attainment_forecast_fetcher": XuchangAnnualAttainmentForecastFetcher,
        "xuchang_cnemc_station_hour_fetcher": XuchangCnemcStationHourFetcher,
        "xuchang_city_exceedance_fetcher": XuchangCityExceedanceFetcher,
        "xuchang_henan_month_year_accumulate_fetcher": XuchangHenanMonthYearAccumulateFetcher,
        "xuchang_nmc_hourly_forecast_fetcher": XuchangNmcHourlyForecastFetcher,
        "xuchang_weather_com_daily_forecast_fetcher": XuchangWeatherComDailyForecastFetcher,
        "xuchang_weather_situation_evidence_fetcher": XuchangWeatherSituationEvidenceFetcher,
        "xuchang_station_deviation_alert_fetcher": XuchangStationDeviationAlertFetcher,
        "xuchang_station_daily_pollution_fetcher": XuchangStationDailyPollutionFetcher,
        "xuchang_station_daily_exceedance_fetcher": XuchangStationDailyExceedanceFetcher,
        "xuchang_transport_analysis_fetcher": XuchangTransportAnalysisFetcher,
        "xuchang_zhongda_station_minute_fetcher": XuchangZhongdaStationFetcher,
        "xuchang_zhongda_station_hour_fetcher":
            lambda: XuchangZhongdaStationFetcher(data_kind="hour"),
        "xuchang_zhongda_city_hour_fetcher": XuchangZhongdaCityFetcher,
        "xuchang_town_five_minute_fetcher": XuchangTownFiveMinuteFetcher,
        "gems_xuchang_image_fetcher": GemsImageFetcher,
    }
    # 广东工单同步已 data-ops 化（2026-10-24）：sync_table.py + dbt 计划任务负责
    # ODS/mart 刷新，不再经 worker fetcher；语义层见 projects/guangdong/data-ops。
    configured = project_context.manifest.backend.fetchers
    history_config = project_context.manifest.backend.weather_history
    if history_config is not None:
        from app.fetchers.weather.city_history_fetcher import CityHistoryFetcher
        factories["city_weather_history"] = lambda: CityHistoryFetcher(
            history_config, project_context.manifest.project
        )
    if configured is None:
        selected = list(factories)
        # xuchang 专属 fetcher 只在 xuchang 项目运行（其余项目缺 ZHONGDA 等凭据，
        # 只会产生周期性空转报错；2026-10-25 广东 worker 日志 109 条/夜均源于此）
        if "xuchang-air-quality" not in enabled_modules:
            selected = [name for name in selected
                        if not name.startswith("xuchang_")
                        and name != "gems_xuchang_image_fetcher"]
        # 广东部署：会商模板 xlsx 未随部署提供（M:\tmp\A会商文件\模板\ 为空），
        # 三个会商 fetcher 每晚必然失败；业务补放模板后移除本排除
        selected = [name for name in selected
                    if name not in ("consultation", "monthly_consultation", "annual_ytd_consultation")]
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

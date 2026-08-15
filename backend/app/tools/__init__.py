"""
LLM Tools

给LLM提供可调用的函数（Function Calling）

工具分类：
1. Query Tools - 查询工具（从数据库读取数据）
   - get_air_quality - 空气质量查询
   - get_weather_data - 气象数据查询
   - get_weather_forecast - 天气预报查询
   - get_current_weather - 实时天气查询
   - get_fire_hotspots - 火点数据查询
   - get_dust_data - 扬尘数据查询
   - get_component_data - 组分数据查询（VOCs/颗粒物，广东省超级站，已废弃）
   - get_vocs_data - VOCs组分数据查询（端口9092）
   - get_5min_data - 5分钟数据查询（站点污染物浓度和气象数据）

2. Analysis Tools - 分析工具（执行计算和分析）
   - analyze_upwind_enterprises - 上风向企业分析（广东省）
   - calculate_pm_pmf - PM2.5/PM10颗粒物PMF源解析（广东省超级站）
   - calculate_vocs_pmf - VOCs挥发性有机物PMF源解析（仅用于臭氧溯源）

3. Visualization Tools - 可视化工具（生成图表和地图配置）
   - execute_echarts_python - 生成前端交互式 ECharts 图表
   - create_report_chart - 生成正式报告静态图表
   - generate_map - 生成高德地图配置

4. Task Management Tools - 任务管理工具（housekeeping状态管理）
   - TaskCreate / TaskUpdate / TaskList / TaskGet - 增量管理当前会话任务清单

**工具选择决策：**
- 前端交互式图表 → execute_echarts_python
- QMD/Word/HTML 正式报告静态图表 → create_report_chart
"""

import structlog

from app.project_config.loader import load_project_context
from app.project_config.models import ProjectContext
from app.tools.base.registry import ToolRegistry
from config.settings import settings

logger = structlog.get_logger()

GIS_TOOL_NAMES = frozenset({
    "generate_map",
    "create_map_point_asset",
    "visual_interaction",
    "resolve_map_data_asset",
    "get_map_program_receipt",
    "wait_map_program_receipt",
    "spatial_analysis",
    "spatial_interpolation",
})


def is_project_tool_enabled(
    context: ProjectContext,
    owner: str,
    tool_name: str,
) -> bool:
    """Return whether a project explicitly enables a tool owned by a module."""
    return (
        owner in context.enabled_modules
        and tool_name in context.manifest.backend.tools
    )


def _register_gis_tools(registry: ToolRegistry) -> None:
    try:
        from app.tools.visualization.generate_map.tool import GenerateMapTool
        registry.register(GenerateMapTool(), priority=210)
        logger.info("tool_loaded", tool="generate_map")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="generate_map", error=str(e))

    try:
        from app.tools.gisctl.create_map_point_asset_tool import CreateMapPointAssetTool
        registry.register(CreateMapPointAssetTool(), priority=213)
        logger.info("tool_loaded", tool="create_map_point_asset")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="create_map_point_asset", error=str(e))

    try:
        from app.tools.gisctl.tool import GisctlTool
        registry.register(GisctlTool(), priority=214)
        logger.info("tool_loaded", tool="visual_interaction")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="visual_interaction", error=str(e))

    try:
        from app.tools.gisctl.asset_resolver_tool import ResolveMapDataAssetTool
        registry.register(ResolveMapDataAssetTool(), priority=215)
        logger.info("tool_loaded", tool="resolve_map_data_asset")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="resolve_map_data_asset", error=str(e))

    try:
        from app.tools.gisctl.map_program_receipt_tool import MapProgramReceiptTool, WaitMapProgramReceiptTool
        registry.register(MapProgramReceiptTool(), priority=216)
        logger.info("tool_loaded", tool="get_map_program_receipt")
        registry.register(WaitMapProgramReceiptTool(), priority=217)
        logger.info("tool_loaded", tool="wait_map_program_receipt")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_map_program_receipt", error=str(e))

    try:
        from app.tools.spatial.spatial_analysis.tool import SpatialAnalysisTool
        registry.register(SpatialAnalysisTool(), priority=218)
        logger.info("tool_loaded", tool="spatial_analysis")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="spatial_analysis", error=str(e))

    try:
        from app.tools.spatial.spatial_interpolation.tool import SpatialInterpolationTool
        registry.register(SpatialInterpolationTool(), priority=219)
        logger.info("tool_loaded", tool="spatial_interpolation")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="spatial_interpolation", error=str(e))


def create_global_tool_registry(context: ProjectContext | None = None) -> ToolRegistry:
    """
    创建并初始化全局工具注册表

    Returns:
        ToolRegistry: 已注册所有可用工具的注册表
    """
    registry = ToolRegistry(registry_name="global")
    context = context or load_project_context(settings.project_id)

    # ========================================
    # Query Tools（查询工具）
    # ========================================

    try:
        from app.tools.query.get_air_quality.tool import GetAirQualityTool
        registry.register(GetAirQualityTool(), priority=10)
        logger.info("tool_loaded", tool="get_air_quality")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_air_quality", error=str(e))

    try:
        from app.tools.query.get_weather_data.tool import GetWeatherDataTool
        registry.register(GetWeatherDataTool(), priority=20)
        logger.info("tool_loaded", tool="get_weather_data")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_weather_data", error=str(e))

    try:
        from app.tools.query.get_weather_forecast.tool import GetWeatherForecastTool
        registry.register(GetWeatherForecastTool(), priority=30)
        logger.info("tool_loaded", tool="get_weather_forecast")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_weather_forecast", error=str(e))

    try:
        from app.tools.query.get_current_weather.tool import GetCurrentWeatherTool
        registry.register(GetCurrentWeatherTool(), priority=15)
        logger.info("tool_loaded", tool="get_current_weather")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_current_weather", error=str(e))

    try:
        from app.tools.query.get_platform_weather_image.tool import GetPlatformWeatherImageTool
        registry.register(GetPlatformWeatherImageTool(), priority=17)
        logger.info("tool_loaded", tool="get_platform_weather_image")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_platform_weather_image", error=str(e))

    try:
        from app.tools.query.get_fire_hotspots.tool import GetFireHotspotsTool
        registry.register(GetFireHotspotsTool(), priority=40)
        logger.info("tool_loaded", tool="get_fire_hotspots")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_fire_hotspots", error=str(e))

    try:
        from app.tools.query.get_dust_data.tool import GetDustDataTool
        registry.register(GetDustDataTool(), priority=50)
        logger.info("tool_loaded", tool="get_dust_data")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_dust_data", error=str(e))


    # ========================================
    # VOCs and Particulate Data Tools (V2.0 - Split)
    # ========================================

    try:
        from app.tools.query.get_vocs_data import GetVOCsDataTool
        registry.register(GetVOCsDataTool(), priority=61)
        logger.info("tool_loaded", tool="get_vocs_data")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_vocs_data", error=str(e))

    # ========================================
    # PM2.5 Component Query Tools (Structured)
    # ========================================

    try:
        from app.tools.query.get_pm25_ionic.tool import GetPM25IonicTool
        registry.register(GetPM25IonicTool(), priority=63)
        logger.info("tool_loaded", tool="get_pm25_ionic")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_pm25_ionic", error=str(e))

    try:
        from app.tools.query.get_pm25_carbon.tool import GetPM25CarbonTool
        registry.register(GetPM25CarbonTool(), priority=64)
        logger.info("tool_loaded", tool="get_pm25_carbon")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_pm25_carbon", error=str(e))

    try:
        from app.tools.query.get_pm25_crustal.tool import GetPM25CrustalTool
        registry.register(GetPM25CrustalTool(), priority=65)
        logger.info("tool_loaded", tool="get_pm25_crustal")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_pm25_crustal", error=str(e))

    try:
        from app.tools.query.get_nearby_stations.tool import GetNearbyStationsTool
        registry.register(GetNearbyStationsTool(), priority=70)
        logger.info("tool_loaded", tool="get_nearby_stations")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_nearby_stations", error=str(e))

    try:
        from app.tools.query.get_universal_meteorology.tool import UniversalMeteorologyTool
        registry.register(UniversalMeteorologyTool(), priority=25)
        logger.info("tool_loaded", tool="get_universal_meteorology")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_universal_meteorology", error=str(e))

    try:
        from app.tools.query.get_observed_meteorology.tool import GetObservedMeteorologyTool
        registry.register(GetObservedMeteorologyTool(), priority=26)
        logger.info("tool_loaded", tool="get_observed_meteorology")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_observed_meteorology", error=str(e))

    try:
        from app.tools.query.get_jining_regular_stations.tool import GetJiningRegularStationsTool
        registry.register(GetJiningRegularStationsTool(), priority=31)
        logger.info("tool_loaded", tool="get_jining_regular_stations")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_jining_regular_stations", error=str(e))

    # 广东省 Suncere API 查询工具
    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereCityHourTool
        registry.register(QueryGDSuncereCityHourTool(), priority=32)
        logger.info("tool_loaded", tool="query_gd_suncere_city_hour")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_city_hour", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereStationHourTool
        registry.register(QueryGDSuncereStationHourTool(), priority=33)
        logger.info("tool_loaded", tool="query_gd_suncere_station_hour")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_station_hour", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereStationDayTool
        registry.register(QueryGDSuncereStationDayTool(), priority=34)
        logger.info("tool_loaded", tool="query_gd_suncere_station_day")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_station_day", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereRegionalComparisonTool
        registry.register(QueryGDSuncereRegionalComparisonTool(), priority=35)
        logger.info("tool_loaded", tool="query_gd_suncere_regional_comparison")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_regional_comparison", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereCityDayTool
        registry.register(QueryGDSuncereCityDayTool(), priority=36)
        logger.info("tool_loaded", tool="query_gd_suncere_city_day")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_city_day", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereDistrictDayTool
        registry.register(QueryGDSuncereDistrictDayTool(), priority=36)
        logger.info("tool_loaded", tool="query_gd_suncere_district_day")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_district_day", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereDistrictReportTool
        registry.register(QueryGDSuncereDistrictReportTool(), priority=37)
        logger.info("tool_loaded", tool="query_gd_suncere_district_report")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_district_report", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereReportCompareTool
        registry.register(QueryGDSuncereReportCompareTool(), priority=38)
        logger.info("tool_loaded", tool="query_gd_suncere_report_compare")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_report_compare", error=str(e))

    try:
        from app.tools.query.query_city_standard_report.tool import QueryCityStandardReportTool
        registry.register(QueryCityStandardReportTool(), priority=39)
        logger.info("tool_loaded", tool="query_city_standard_report")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_city_standard_report", error=str(e))

    try:
        from app.tools.query.query_city_standard_report.tool import QueryCityStandardYoyReportTool
        registry.register(QueryCityStandardYoyReportTool(), priority=39)
        logger.info("tool_loaded", tool="query_city_standard_yoy_report")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_city_standard_yoy_report", error=str(e))

    try:
        from app.tools.query.query_station_standard_report.tool import QueryStationStandardReportTool
        registry.register(QueryStationStandardReportTool(), priority=43)
        logger.info("tool_loaded", tool="query_station_standard_report")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_station_standard_report", error=str(e))

    try:
        from app.tools.query.query_station_standard_report.tool import QueryStationStandardYoyReportTool
        registry.register(QueryStationStandardYoyReportTool(), priority=44)
        logger.info("tool_loaded", tool="query_station_standard_yoy_report")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_station_standard_yoy_report", error=str(e))

    try:
        from app.tools.query.city_pollutant_rankings.tool import CityPollutantRankingsTool
        registry.register(CityPollutantRankingsTool(), priority=45)
        logger.info("tool_loaded", tool="analyze_city_pollutant_rankings")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="analyze_city_pollutant_rankings", error=str(e))

    # 全国省份/城市空气质量查询工具（GDQFWS参考项目）
    try:
        from app.tools.query.query_national_air_quality.tool_wrapper import QueryNationalProvinceAirQualityTool
        registry.register(QueryNationalProvinceAirQualityTool(), priority=46)
        logger.info("tool_loaded", tool="query_national_province_air_quality")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_national_province_air_quality", error=str(e))

    try:
        from app.tools.query.query_national_air_quality.tool_wrapper import QueryNationalCityAirQualityTool
        registry.register(QueryNationalCityAirQualityTool(), priority=47)
        logger.info("tool_loaded", tool="query_national_city_air_quality")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_national_city_air_quality", error=str(e))

    try:
        from app.tools.query.get_satellite_data.tool import GetSatelliteDataTool
        registry.register(GetSatelliteDataTool(), priority=43)
        logger.info("tool_loaded", tool="get_satellite_data")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_satellite_data", error=str(e))

    if is_project_tool_enabled(context, "satellite", "get_gems_image"):
        try:
            from app.tools.query.get_gems_image.tool import GetGemsImageTool
            registry.register(GetGemsImageTool(), priority=43)
            logger.info("tool_loaded", tool="get_gems_image")
        except ImportError as e:
            logger.warning("tool_import_failed", tool="get_gems_image", error=str(e))

    if is_project_tool_enabled(context, "satellite", "get_sentinel5p_image"):
        try:
            from app.tools.query.get_sentinel5p_image.tool import GetSentinel5PImageTool
            registry.register(GetSentinel5PImageTool(), priority=43)
            logger.info("tool_loaded", tool="get_sentinel5p_image")
        except ImportError as e:
            logger.warning("tool_import_failed", tool="get_sentinel5p_image", error=str(e))

    # 江西项目专属噪声数据查询工具
    jiangxi_noise_tools = [
        ("query_jiangxi_noise_city", "QueryJiangxiNoiseCityTool", 48),
        ("query_jiangxi_noise_station_minute", "QueryJiangxiNoiseStationMinuteTool", 49),
        ("query_jiangxi_noise_station_hour", "QueryJiangxiNoiseStationHourTool", 50),
        ("query_jiangxi_noise_station_day", "QueryJiangxiNoiseStationDayTool", 51),
        (
            "query_jiangxi_noise_station_statistics",
            "QueryJiangxiNoiseStationStatisticsTool",
            52,
        ),
        (
            "query_jiangxi_noise_city_compliance",
            "QueryJiangxiNoiseCityComplianceTool",
            53,
        ),
        (
            "query_jiangxi_noise_station_compliance",
            "QueryJiangxiNoiseStationComplianceTool",
            54,
        ),
    ]
    for tool_name, class_name, priority in jiangxi_noise_tools:
        if is_project_tool_enabled(context, "jiangxi-noise", tool_name):
            try:
                module = __import__(
                    "app.tools.query.query_jiangxi_noise.tool",
                    fromlist=[class_name],
                )
                registry.register(getattr(module, class_name)(), priority=priority)
                logger.info("tool_loaded", tool=tool_name)
            except ImportError as e:
                logger.warning("tool_import_failed", tool=tool_name, error=str(e))

    # XcAiDb SQL Server 城市历史数据查询工具
    try:
        from app.tools.query.query_xcai_city_history.tool import QueryXcAiCityHistoryTool
        registry.register(QueryXcAiCityHistoryTool(), priority=44)
        logger.info("tool_loaded", tool="query_xcai_city_history")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_xcai_city_history", error=str(e))

    # 通用SQL执行工具
    try:
        from app.tools.query.execute_sql_query.tool import ExecuteOpsSQLQueryTool, ExecuteSQLQueryTool, ExecuteTenderSQLQueryTool
        registry.register(ExecuteSQLQueryTool(), priority=47)
        logger.info("tool_loaded", tool="execute_sql_query")
        registry.register(ExecuteOpsSQLQueryTool(), priority=47)
        logger.info("tool_loaded", tool="execute_ops_sql_query")
        registry.register(ExecuteTenderSQLQueryTool(), priority=47)
        logger.info("tool_loaded", tool="execute_tender_sql_query")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="execute_sql_query", error=str(e))

    try:
        from app.tools.query.qianlima_realtime_tender.tool import QianlimaRealtimeTenderTool
        registry.register(QianlimaRealtimeTenderTool(), priority=46)
        logger.info("tool_loaded", tool="qianlima_realtime_tender")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="qianlima_realtime_tender", error=str(e))

    try:
        from app.tools.analysis.ops_work_order_audit.tool import (
            OpsAuditFetchDatasetTool,
            OpsAuditInspectTool,
            OpsAuditRunRulesTool,
        )
        registry.register(OpsAuditFetchDatasetTool(), priority=48)
        logger.info("tool_loaded", tool="ops_audit_fetch_dataset")
        registry.register(OpsAuditRunRulesTool(), priority=49)
        logger.info("tool_loaded", tool="ops_audit_run_rules")
        registry.register(OpsAuditInspectTool(), priority=50)
        logger.info("tool_loaded", tool="ops_audit_inspect")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="ops_audit_tools", error=str(e))

    if any(is_project_tool_enabled(context, "legacy", tool_name) for tool_name in {
        "jiangsu_fetch_station_data",
        "jiangsu_fetch_city_data",
        "jiangsu_fetch_district_data",
        "jiangsu_query_statistics",
    }):
        try:
            from app.tools.jiangsu.station_data import JiangsuStationDataTool
            from app.tools.jiangsu.query_tools import (
                JiangsuCityDataTool,
                JiangsuDistrictDataTool,
                JiangsuStatisticsTool,
            )
            for tool in (JiangsuStationDataTool(), JiangsuCityDataTool(), JiangsuDistrictDataTool(), JiangsuStatisticsTool()):
                registry.register(tool, priority=50)
                logger.info("tool_loaded", tool=tool.name)
        except ImportError as e:
            logger.warning("tool_import_failed", tool="jiangsu_data_tools", error=str(e))

    if is_project_tool_enabled(context, "legacy", "jiangsu_fetch_alarm_records"):
        try:
            from app.tools.jiangsu.alarm_records import JiangsuAlarmRecordsTool
            registry.register(JiangsuAlarmRecordsTool(), priority=51)
            logger.info("tool_loaded", tool="jiangsu_fetch_alarm_records")
        except ImportError as e:
            logger.warning("tool_import_failed", tool="jiangsu_fetch_alarm_records", error=str(e))

    if any(is_project_tool_enabled(context, "legacy", tool_name) for tool_name in {
        "jiangsu_fetch_attendance_records", "jiangsu_fetch_station_directory",
    }):
        try:
            from app.tools.jiangsu.operations_analysis import JiangsuAttendanceRecordsTool, JiangsuStationDirectoryTool
            for tool in (JiangsuAttendanceRecordsTool(), JiangsuStationDirectoryTool()):
                if is_project_tool_enabled(context, "legacy", tool.name):
                    registry.register(tool, priority=52)
                    logger.info("tool_loaded", tool=tool.name)
        except ImportError as e:
            logger.warning("tool_import_failed", tool="jiangsu_operations_analysis_tools", error=str(e))

    if any(is_project_tool_enabled(context, "legacy", tool_name) for tool_name in {
        "jiangsu_get_device_control_state",
        "jiangsu_prepare_device_control",
        "jiangsu_execute_device_control",
    }):
        try:
            from app.tools.jiangsu.device_control import (
                JiangsuDeviceControlExecuteTool,
                JiangsuDeviceControlPrepareTool,
                JiangsuDeviceControlStateTool,
            )
            for tool in (
                JiangsuDeviceControlStateTool(),
                JiangsuDeviceControlPrepareTool(),
                JiangsuDeviceControlExecuteTool(),
            ):
                if is_project_tool_enabled(context, "legacy", tool.name):
                    registry.register(tool, priority=53)
                    logger.info("tool_loaded", tool=tool.name)
        except ImportError as e:
            logger.warning("tool_import_failed", tool="jiangsu_device_control_tools", error=str(e))

    if any(is_project_tool_enabled(context, "legacy", tool_name) for tool_name in {
        "jiangsu_fetch_station_alarm_logs",
        "jiangsu_fetch_fault_work_orders",
        "jiangsu_fetch_auto_inspection",
        "jiangsu_fetch_network_inspection_summary",
        "jiangsu_fetch_station_environment_history",
        "jiangsu_fetch_qc_task_history",
        "jiangsu_fetch_qc_task_status",
        "jiangsu_fetch_qc_run_logs",
        "jiangsu_fetch_qc_monitoring_curve",
    }):
        try:
            from app.tools.jiangsu.fault_diagnosis import (
                JiangsuAutoInspectionTool,
                JiangsuFaultWorkOrdersTool,
                JiangsuNetworkInspectionSummaryTool,
                JiangsuStationEnvironmentHistoryTool,
                JiangsuQcMonitoringCurveTool,
                JiangsuQcRunLogTool,
                JiangsuQcTaskHistoryTool,
                JiangsuQcTaskStatusTool,
                JiangsuStationAlarmLogsTool,
            )
            for tool in (
                JiangsuStationAlarmLogsTool(), JiangsuFaultWorkOrdersTool(), JiangsuAutoInspectionTool(),
                JiangsuNetworkInspectionSummaryTool(), JiangsuStationEnvironmentHistoryTool(),
                JiangsuQcTaskHistoryTool(), JiangsuQcTaskStatusTool(), JiangsuQcRunLogTool(), JiangsuQcMonitoringCurveTool(),
            ):
                if is_project_tool_enabled(context, "legacy", tool.name):
                    registry.register(tool, priority=54)
                    logger.info("tool_loaded", tool=tool.name)
        except ImportError as e:
            logger.warning("tool_import_failed", tool="jiangsu_fault_diagnosis_tools", error=str(e))

    try:
        from app.tools.knowledge.knowledge_graph_query.tool import KnowledgeGraphQueryTool
        registry.register(KnowledgeGraphQueryTool(), priority=51)
        logger.info("tool_loaded", tool="knowledge_graph_query")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="knowledge_graph_query", error=str(e))

    try:
        from app.tools.knowledge.knowledge_graph_build.tool import KnowledgeGraphBuildTool
        registry.register(KnowledgeGraphBuildTool(), priority=52)
        logger.info("tool_loaded", tool="knowledge_graph_build")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="knowledge_graph_build", error=str(e))

    try:
        from app.tools.query.resolve_station_geo.tool import ResolveStationGeoTool
        registry.register(ResolveStationGeoTool(), priority=54)
        logger.info("tool_loaded", tool="resolve_station_geo")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="resolve_station_geo", error=str(e))

    # 5分钟数据查询工具
    try:
        from app.tools.query.get_5min_data.tool import Get5MinDataTool
        registry.register(Get5MinDataTool(), priority=48)
        logger.info("tool_loaded", tool="get_5min_data")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_5min_data", error=str(e))

    # ========================================
    # External Data Tools（外部数据工具）
    # ========================================

    try:
        from app.tools.external_data.gfs_downloader.tool import GFSDownloaderTool
        registry.register(GFSDownloaderTool(), priority=80)
        logger.info("tool_loaded", tool="download_gfs_data")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="download_gfs_data", error=str(e))

    try:
        from app.tools.external_data.gfs_processor.tool import GFSProcessorTool
        registry.register(GFSProcessorTool(), priority=85)
        logger.info("tool_loaded", tool="process_gfs_data")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="process_gfs_data", error=str(e))

    # ========================================
    # Analysis Tools（分析工具）
    # ========================================

    try:
        from app.tools.analysis.analyze_upwind_enterprises.tool import AnalyzeUpwindEnterprisesTool
        registry.register(AnalyzeUpwindEnterprisesTool(), priority=100)
        logger.info("tool_loaded", tool="analyze_upwind_enterprises")
    except (ImportError, KeyError) as e:
        logger.warning("tool_import_failed", tool="analyze_upwind_enterprises", error=str(e))

    try:
        # Import PM2.5/PM10颗粒物PMF工具
        from app.tools.analysis.calculate_pm_pmf.tool import CalculatePMFTool
        registry.register(CalculatePMFTool(), priority=110)
        logger.info("tool_loaded", tool="calculate_pm_pmf", version="v2_context")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="calculate_pm_pmf", error=str(e))

    try:
        # Import VOCs PMF工具（臭氧溯源专用）
        from app.tools.analysis.calculate_vocs_pmf.tool import CalculateVOCSPMFTool
        registry.register(CalculateVOCSPMFTool(), priority=111)
        logger.info("tool_loaded", tool="calculate_vocs_pmf", version="v2_context")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="calculate_vocs_pmf", error=str(e))

    # ========================================
    # OBM/EKMA Tools (基于RACM2完整化学机理)
    # ========================================

    try:
        from app.tools.analysis.meteorological_trajectory_analysis.tool import MeteorologicalTrajectoryAnalysisTool
        registry.register(MeteorologicalTrajectoryAnalysisTool(), priority=130)
        logger.info("tool_loaded", tool="meteorological_trajectory_analysis", version="noaa_api")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="meteorological_trajectory_analysis", error=str(e))

    try:
        from app.tools.analysis.trajectory_source_analysis.tool import TrajectorySourceAnalysisTool
        registry.register(TrajectorySourceAnalysisTool(), priority=135)
        logger.info("tool_loaded", tool="analyze_trajectory_sources", version="v1.0")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="analyze_trajectory_sources", error=str(e))

    # IAQI计算功能已整合到 aggregate_data 工具（使用新标准 HJ 633-2026）
    # 旧的 iaqi_calculator 工具已删除

    try:
        from app.tools.analysis.ml_predictor.tool import MLPredictorTool
        registry.register(MLPredictorTool(), priority=150)
        logger.info("tool_loaded", tool="predict_air_quality")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="predict_air_quality", error=str(e))

    # ========================================
    # PM2.5 Analysis Tools（PM2.5分析工具 - 基于参考项目）
    # ========================================
    # 新增的5个PM2.5分析工具，填补现有分析能力空白

    try:
        from app.tools.analysis.calculate_reconstruction.calculate_reconstruction import CalculateReconstructionTool
        registry.register(CalculateReconstructionTool(), priority=160)
        logger.info("tool_loaded", tool="calculate_reconstruction")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="calculate_reconstruction", error=str(e))

    try:
        from app.tools.analysis.calculate_carbon.calculate_carbon import CalculateCarbonTool
        registry.register(CalculateCarbonTool(), priority=161)
        logger.info("tool_loaded", tool="calculate_carbon")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="calculate_carbon", error=str(e))

    try:
        from app.tools.analysis.calculate_soluble.calculate_soluble import CalculateSolubleTool
        registry.register(CalculateSolubleTool(), priority=162)
        logger.info("tool_loaded", tool="calculate_soluble")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="calculate_soluble", error=str(e))

    try:
        from app.tools.analysis.calculate_crustal.calculate_crustal import CalculateCrustalTool
        registry.register(CalculateCrustalTool(), priority=163)
        logger.info("tool_loaded", tool="calculate_crustal")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="calculate_crustal", error=str(e))

    try:
        from app.tools.analysis.calculate_trace.calculate_trace import CalculateTraceTool
        registry.register(CalculateTraceTool(), priority=164)
        logger.info("tool_loaded", tool="calculate_trace")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="calculate_trace", error=str(e))

    # ========================================
    # Analysis Tools（数据分析工具）
    # ========================================

    try:
        from app.tools.analysis.aggregate_data.tool import AggregateDataTool
        registry.register(AggregateDataTool(), priority=75)
        logger.info("tool_loaded", tool="aggregate_data")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="aggregate_data", error=str(e))

    # ========================================
    # Visualization Tools（可视化工具）
    # ========================================

    if context.manifest.backend.gis_tools_enabled:
        _register_gis_tools(registry)
    else:
        logger.info("gis_tools_registration_skipped", project=context.manifest.project)

    # ===== create_diagram_artifact 已废弃，使用画板模式替代 =====
    # 画板模式通过 call_sub_agent(target_mode="board") 调用
    # 流程图、架构图、步骤图、决策树等由画板Agent生成draw.io图并返回图片文件

    try:
        from app.tools.visualization.create_drawio_board import CreateDrawioBoardTool
        registry.register(CreateDrawioBoardTool(), priority=212)
        logger.info("tool_loaded", tool="create_drawio_board")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="create_drawio_board", error=str(e))

    try:
        from app.tools.visualization.create_drawio_board import RenderDrawioBoardCandidateTool
        registry.register(RenderDrawioBoardCandidateTool(), priority=213)
        logger.info("tool_loaded", tool="render_drawio_board_candidate")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="render_drawio_board_candidate", error=str(e))

    try:
        from app.tools.visualization.create_drawio_board import AcceptDrawioBoardCandidateTool
        registry.register(AcceptDrawioBoardCandidateTool(), priority=214)
        logger.info("tool_loaded", tool="accept_drawio_board_candidate")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="accept_drawio_board_candidate", error=str(e))

    try:
        from app.tools.visualization.create_report_chart import CreateReportChartTool
        registry.register(CreateReportChartTool(), priority=213)
        logger.info("tool_loaded", tool="create_report_chart")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="create_report_chart", error=str(e))

    # ========================================
    # Utility Tools（实用工具）
    # ========================================

    try:
        from app.tools.utility.list_session_resources_tool import ListSessionResourcesTool
        registry.register(ListSessionResourcesTool(), priority=299)
        logger.info("tool_loaded", tool="list_session_resources")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="list_session_resources", error=str(e))

    try:
        from app.tools.utility.read_session_resource_tool import ReadSessionResourceTool
        registry.register(ReadSessionResourceTool(), priority=299)
        logger.info("tool_loaded", tool="read_session_resource")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="read_session_resource", error=str(e))

    try:
        from app.tools.utility.bash_tool import BashTool
        registry.register(BashTool(), priority=300)  # 修复: 500->300
        logger.info("tool_loaded", tool="bash")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="bash", error=str(e))

    try:
        from app.tools.utility.execute_python_tool import ExecuteEChartsPythonTool, ExecutePythonTool
        registry.register(ExecutePythonTool(), priority=301)  # 修复: 501->301
        logger.info("tool_loaded", tool="execute_python")
        registry.register(ExecuteEChartsPythonTool(), priority=301)
        logger.info("tool_loaded", tool="execute_echarts_python")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="execute_python", error=str(e))

    # ========================================
    # File & Image Tools（文件和图片工具）
    # ========================================

    try:
        from app.tools.utility.read_file_tool import ReadFileTool
        registry.register(ReadFileTool(), priority=302)  # 修复: 501->302
        logger.info("tool_loaded", tool="read_file")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="read_file", error=str(e))

    try:
        from app.tools.utility.analyze_image_tool import AnalyzeImageTool
        registry.register(AnalyzeImageTool(), priority=303)  # 修复: 502->303
        logger.info("tool_loaded", tool="analyze_image")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="analyze_image", error=str(e))

    try:
        from app.tools.utility.edit_file_tool_v2 import EditFileToolV2 as EditFileTool
        registry.register(EditFileTool(), priority=304)  # 修复: 503->304
        logger.info("tool_loaded", tool="edit_file", version="v2")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="edit_file", version="v2", error=str(e))

    try:
        from app.tools.utility.grep_tool import GrepTool
        registry.register(GrepTool(), priority=305)  # 修复: 504->305
        logger.info("tool_loaded", tool="grep")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="grep", error=str(e))

    try:
        from app.tools.utility.write_file_tool import WriteFileTool
        registry.register(WriteFileTool(), priority=306)  # 修复: 505->306
        logger.info("tool_loaded", tool="write_file")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="write_file", error=str(e))

    try:
        from app.tools.utility.publish_session_file_tool import PublishSessionFileTool
        registry.register(PublishSessionFileTool(), priority=306)
        logger.info("tool_loaded", tool="publish_session_file")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="publish_session_file", error=str(e))

    try:
        from app.tools.utility.glob_tool import GlobTool
        registry.register(GlobTool(), priority=307)  # 修复: 506->307
        logger.info("tool_loaded", tool="search_files")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="search_files", error=str(e))

    try:
        from app.tools.utility.list_directory_tool import ListDirectoryTool
        registry.register(ListDirectoryTool(), priority=308)  # 修复: 507->308
        logger.info("tool_loaded", tool="list_directory")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="list_directory", error=str(e))

    try:
        from app.tools.utility.vectorize_document_tool import VectorizeDocumentTool
        registry.register(VectorizeDocumentTool(), priority=309)  # 修复: 512->309
        logger.info("tool_loaded", tool="vectorize_document")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="vectorize_document", error=str(e))

    try:
        from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool
        registry.register(ListSkillsTool(), priority=310)  # 修复: 508->310
        logger.info("tool_loaded", tool="list_skills")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="list_skills", error=str(e))

    try:
        from app.tools.utility.skill_management.view_skill_tool import ViewSkillTool
        registry.register(ViewSkillTool(), priority=311)
        logger.info("tool_loaded", tool="view_skill")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="view_skill", error=str(e))

    try:
        from app.tools.utility.skill_management.create_skill_draft_tool import CreateSkillDraftTool
        registry.register(CreateSkillDraftTool(), priority=312)
        logger.info("tool_loaded", tool="create_skill_draft")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="create_skill_draft", error=str(e))

    try:
        from app.tools.utility.parse_pdf_tool import create_parse_pdf_tool
        registry.register(create_parse_pdf_tool(), priority=313)  # 修复: 509->313
        logger.info("tool_loaded", tool="parse_pdf")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="parse_pdf", error=str(e))

    # ========================================
    # Office Automation Tools
    # ========================================

    try:
        from app.tools.office.read_pptx_tool import ReadPptxTool
        registry.register(ReadPptxTool(), priority=345)  # 修复: 594->345
        logger.info("tool_loaded", tool="read_pptx")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="read_pptx", error=str(e))

    try:
        from app.tools.office.validate_pptx_tool import ValidatePptxTool
        registry.register(ValidatePptxTool(), priority=350)  # 修复: 592->350
        logger.info("tool_loaded", tool="validate_pptx")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="validate_pptx", error=str(e))

    try:
        from app.tools.office.ppt_master_tool import CreatePptxWithPptMasterTool
        registry.register(CreatePptxWithPptMasterTool(), priority=352)
        logger.info("tool_loaded", tool="create_pptx_with_ppt_master")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="create_pptx_with_ppt_master", error=str(e))

    try:
        from app.tools.office.editable_ppt.tool import ManageEditablePptTool
        registry.register(ManageEditablePptTool(), priority=353)
        logger.info("tool_loaded", tool="manage_editable_ppt")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="manage_editable_ppt", error=str(e))

    try:
        from app.tools.office.wecom_cli import WeComCliTool
        registry.register(WeComCliTool(), priority=354)
        logger.info("tool_loaded", tool="wecom_cli")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="wecom_cli", error=str(e))


    # ========================================
    # Scheduled Tasks Tools（定时任务工具）
    # ========================================

    try:
        from app.tools.scheduled_tasks import create_scheduled_task_tool
        registry.register(create_scheduled_task_tool, priority=360)  # 修复: 700->360
        logger.info("tool_loaded", tool="create_scheduled_task")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="create_scheduled_task", error=str(e))

    # ========================================
    # Social Mode Tools（社交模式工具 - 呼吸式Agent）
    # ========================================

    try:
        from app.tools.social.schedule_task.tool import ScheduleTaskTool
        registry.register(ScheduleTaskTool(), priority=361)  # 修复: 701->361
        logger.info("tool_loaded", tool="schedule_task")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="schedule_task", error=str(e))

    try:
        from app.tools.exam.exam_practice import ExamPracticeTool
        registry.register(ExamPracticeTool(), priority=361)
        logger.info("tool_loaded", tool="exam_practice")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="exam_practice", error=str(e))

    try:
        from app.tools.exam.exam_bank import GenerateExamBankTool
        registry.register(GenerateExamBankTool(), priority=362)
        logger.info("tool_loaded", tool="generate_exam_bank")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="generate_exam_bank", error=str(e))

    try:
        from app.tools.social.send_notification.tool import SendNotificationTool
        registry.register(SendNotificationTool(), priority=362)  # 修复: 702->362
        logger.info("tool_loaded", tool="send_notification")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="send_notification", error=str(e))

    try:
        from app.tools.social.broadcast.tool import BroadcastSocialUsersTool
        registry.register(BroadcastSocialUsersTool(), priority=363)
        logger.info("tool_loaded", tool="broadcast_social_users")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="broadcast_social_users", error=str(e))

    try:
        from app.tools.social.search_history.tool import SearchHistoryTool
        registry.register(SearchHistoryTool(), priority=364)  # 修复: 704->364
        logger.info("tool_loaded", tool="search_history")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="search_history", error=str(e))

    try:
        from app.tools.social.session_search.tool import SessionSearchTool
        registry.register(SessionSearchTool(), priority=365)
        logger.info("tool_loaded", tool="session_search")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="session_search", error=str(e))

    try:
        from app.tools.social.remember_fact.tool import RememberFactTool
        registry.register(RememberFactTool(), priority=371)  # 修复: 720->371
        logger.info("tool_loaded", tool="remember_fact")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="remember_fact", error=str(e))

    try:
        from app.tools.social.replace_memory.tool import ReplaceMemoryTool
        registry.register(ReplaceMemoryTool(), priority=372)  # 修复: 721->372
        logger.info("tool_loaded", tool="replace_memory")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="replace_memory", error=str(e))

    try:
        from app.tools.social.remove_memory.tool import RemoveMemoryTool
        registry.register(RemoveMemoryTool(), priority=373)  # 修复: 722->373
        logger.info("tool_loaded", tool="remove_memory")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="remove_memory", error=str(e))

    try:
        from app.tools.social.web_search.tool import WebSearchTool
        registry.register(WebSearchTool(), priority=375)  # 修复: 705->375
        logger.info("tool_loaded", tool="web_search")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="web_search", error=str(e))

    try:
        from app.tools.social.web_search.tool import WebFetchTool
        registry.register(WebFetchTool(), priority=376)  # 修复: 706->376
        logger.info("tool_loaded", tool="web_fetch")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="web_fetch", error=str(e))

    # ========================================
    # Social Mode Tools - Background Tasks（后台任务工具）
    # ========================================

    try:
        from app.tools.social.spawn.tool import SpawnTool
        registry.register(SpawnTool(), priority=377)  # 修复: 710->377
        logger.info("tool_loaded", tool="spawn")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="spawn", error=str(e))

    try:
        from app.tools.social.wait_task.tool import WaitTaskTool
        registry.register(WaitTaskTool(), priority=378)
        logger.info("tool_loaded", tool="wait_task")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="wait_task", error=str(e))

    try:
        from app.tools.social.cli_session.tool import CliSessionTool
        registry.register(CliSessionTool(), priority=379)
        logger.info("tool_loaded", tool="cli_session")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="cli_session", error=str(e))

    try:
        from app.tools.social.terminal_session.tool import TerminalSessionTool
        registry.register(TerminalSessionTool(), priority=380)
        logger.info("tool_loaded", tool="terminal_session")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="terminal_session", error=str(e))

    # ========================================
    # Task Management Tools（任务管理工具）
    # ========================================

    try:
        from app.tools.task_management.task_tools import (
            task_create_tool,
            task_get_tool,
            task_list_tool,
            task_update_tool,
        )
        registry.register(task_create_tool, priority=381)
        registry.register(task_update_tool, priority=382)
        registry.register(task_list_tool, priority=383)
        registry.register(task_get_tool, priority=384)
        logger.info("tool_loaded", tool="TaskCreate")
        logger.info("tool_loaded", tool="TaskUpdate")
        logger.info("tool_loaded", tool="TaskList")
        logger.info("tool_loaded", tool="TaskGet")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="task_management", error=str(e))

    # ========================================
    # Browser Tools（浏览器工具 - Office Assistant Pattern）
    # ========================================

    try:
        from app.tools.browser.tool import BrowserTool
        registry.register(BrowserTool(), priority=320)  # 修复: 550->320
        logger.info("tool_loaded", tool="browser")
    except (ImportError, ValueError) as e:
        # 捕获导入错误和 schema 验证错误
        logger.warning(
            "tool_registration_failed",
            tool="browser",
            error_type=type(e).__name__,
            error=str(e)
        )

    # ========================================
    # Agent Tools（Agent间调用工具）
    # ========================================

    try:
        from app.tools.agent_tools.call_sub_agent import CallSubAgentTool
        # 注意：CallSubAgentTool需要延迟初始化（在ReActLoop中注入依赖）
        # 这里创建一个占位符工具，真实的工具实例在executor中创建
        call_sub_agent_tool = CallSubAgentTool()
        registry.register(call_sub_agent_tool, priority=385)  # 修复: 900->385
        logger.info("tool_loaded", tool="call_sub_agent")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="call_sub_agent", error=str(e))

    # ========================================
    # Code Tools（编程模式工具）
    # ========================================

    try:
        from app.tools.code.validate_tool import ValidateToolTool
        registry.register(ValidateToolTool(), priority=386)  # 修复: 850->386
        logger.info("tool_loaded", tool="validate_tool")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="validate_tool", error=str(e))

    # ========================================
    # Workflow Tools（工作流工具 - 统一架构）
    # ========================================

    try:
        from app.tools.workflow.quick_trace_workflow import QuickTraceWorkflow
        registry.register(QuickTraceWorkflow(), priority=45)
        logger.info("tool_loaded", tool="quick_trace_workflow")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="quick_trace_workflow", error=str(e))

    try:
        from app.tools.workflow.deep_trace_workflow import DeepTraceWorkflow
        registry.register(DeepTraceWorkflow(), priority=47)
        logger.info("tool_loaded", tool="deep_trace_workflow")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="deep_trace_workflow", error=str(e))

    # ========================================
    # Report Tools（报告工具）
    # ========================================

    try:
        from app.tools.report.read_docx.tool import ReadDocxTool
        registry.register(ReadDocxTool(), priority=387)  # 修复: 459->387
        logger.info("tool_loaded", tool="read_docx")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="read_docx", error=str(e))

    try:
        from app.tools.report.report_package.tool import (
            CreateReportPackageTool,
            RenderReportPackageTool,
            ValidateReportPackageTool,
        )
        registry.register(CreateReportPackageTool(), priority=388)
        registry.register(RenderReportPackageTool(), priority=389)
        registry.register(ValidateReportPackageTool(), priority=390)
        logger.info("tool_loaded", tool="report_package_tools")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="report_package_tools", error=str(e))

    try:
        from app.tools.html_artifact import CreateHtmlArtifactTool
        registry.register(CreateHtmlArtifactTool(), priority=389)
        logger.info("tool_loaded", tool="create_html_artifact")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="create_html_artifact", error=str(e))

    try:
        from app.tools.workflow.knowledge_qa_workflow import KnowledgeQAWorkflow
        registry.register(KnowledgeQAWorkflow(), priority=48)
        logger.info("tool_loaded", tool="knowledge_qa_workflow")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="knowledge_qa_workflow", error=str(e))

    try:
        from app.tools.workflow.knowledge_document_reader import KnowledgeDocumentReader
        registry.register(KnowledgeDocumentReader(), priority=49)
        logger.info("tool_loaded", tool="knowledge_document_reader")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="knowledge_document_reader", error=str(e))

    logger.info(
        "global_tool_registry_created",
        total_tools=len(registry.list_tools()),
        tools=registry.list_tools()
    )

    return registry


# 创建全局注册表实例
global_tool_registry = create_global_tool_registry()


__all__ = [
    "global_tool_registry",
    "create_global_tool_registry"
]

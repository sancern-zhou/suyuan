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

2. Analysis Tools - 分析工具（执行计算和分析）
   - analyze_upwind_enterprises - 上风向企业分析（广东省）
   - calculate_pm_pmf - PM2.5/PM10颗粒物PMF源解析（广东省超级站）
   - calculate_vocs_pmf - VOCs挥发性有机物PMF源解析（仅用于臭氧溯源）

3. Visualization Tools - 可视化工具（生成图表和地图配置）
   **图表工具职责分工：**
   - smart_chart_generator (智能工具) - 固定格式数据专用
     * 适用：PMF/OBM分析结果、组分数据、已存储数据
     * 特征：从统一存储加载（data_id）、智能推荐图表类型
   - generate_chart (通用工具) - 动态数据专用
     * 适用：直接传入数据、自定义场景、预定义场景模板
     * 特征：直接传入数据（data）、模板库+LLM生成
   - generate_map - 生成高德地图配置

4. Task Management Tools - 任务管理工具（动态任务清单管理）
   - create_task - 创建新任务到任务清单
   - update_task - 更新任务状态（pending/in_progress/completed/failed）
   - list_tasks - 查看当前会话的所有任务
   - get_task - 获取特定任务的详细信息

**工具选择决策：**
- 有data_id → smart_chart_generator
- 无data_id → generate_chart
- PMF/OBM结果 → smart_chart_generator
- 原始数据 → generate_chart
"""

from app.tools.base.registry import ToolRegistry
import structlog

logger = structlog.get_logger()


def create_global_tool_registry() -> ToolRegistry:
    """
    创建并初始化全局工具注册表

    Returns:
        ToolRegistry: 已注册所有可用工具的注册表
    """
    registry = ToolRegistry(registry_name="global")

    # ========================================
    # Query Tools（查询工具）
    # ========================================

    try:
        from app.tools.system.read_data_registry.tool import ReadDataRegistryTool
        registry.register(ReadDataRegistryTool(), priority=5)
        logger.info("tool_loaded", tool="read_data_registry")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="read_data_registry", error=str(e))

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
        from app.tools.query.get_weather_situation_map.tool import GetWeatherSituationMapTool
        registry.register(GetWeatherSituationMapTool(), priority=16)
        logger.info("tool_loaded", tool="get_weather_situation_map")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_weather_situation_map", error=str(e))

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
        from app.tools.query.get_vocs_data.tool import GetVOCsDataTool
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
        from app.tools.knowledge.search_knowledge_base.tool import SearchKnowledgeBaseTool
        registry.register(SearchKnowledgeBaseTool(), priority=27)
        logger.info("tool_loaded", tool="search_knowledge_base")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="search_knowledge_base", error=str(e))

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
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereReportTool
        registry.register(QueryGDSuncereReportTool(), priority=37)
        logger.info("tool_loaded", tool="query_gd_suncere_report")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_report", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereReportCompareTool
        registry.register(QueryGDSuncereReportCompareTool(), priority=38)
        logger.info("tool_loaded", tool="query_gd_suncere_report_compare")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_report_compare", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryStandardComparisonTool
        registry.register(QueryStandardComparisonTool(), priority=39)
        logger.info("tool_loaded", tool="query_standard_comparison")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_standard_comparison", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereCityDayNewStandardTool
        registry.register(QueryGDSuncereCityDayNewStandardTool(), priority=40)
        logger.info("tool_loaded", tool="query_gd_suncere_city_day_new")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_city_day_new", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereCityDayOldStandardTool
        registry.register(QueryGDSuncereCityDayOldStandardTool(), priority=40)
        logger.info("tool_loaded", tool="query_gd_suncere_city_day_old_standard")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_city_day_old_standard", error=str(e))

    try:
        from app.tools.query.query_new_standard_report.tool import QueryNewStandardReportTool
        registry.register(QueryNewStandardReportTool(), priority=41)
        logger.info("tool_loaded", tool="query_new_standard_report")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_new_standard_report", error=str(e))

    try:
        from app.tools.query.compare_standard_reports.tool import CompareStandardReportsTool
        registry.register(CompareStandardReportsTool(), priority=42)
        logger.info("tool_loaded", tool="compare_standard_reports")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="compare_standard_reports", error=str(e))

    try:
        from app.tools.query.query_station_new_standard_report.tool import QueryStationNewStandardReportTool
        registry.register(QueryStationNewStandardReportTool(), priority=43)
        logger.info("tool_loaded", tool="query_station_new_standard_report")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_station_new_standard_report", error=str(e))

    try:
        from app.tools.query.compare_station_standard_reports.tool import CompareStationStandardReportsTool
        registry.register(CompareStationStandardReportsTool(), priority=44)
        logger.info("tool_loaded", tool="compare_station_standard_reports")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="compare_station_standard_reports", error=str(e))

    try:
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereOldStandardReportTool
        registry.register(QueryGDSuncereOldStandardReportTool(), priority=45)
        logger.info("tool_loaded", tool="query_old_standard_report")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_old_standard_report", error=str(e))

    try:
        from app.tools.query.get_satellite_data.tool import GetSatelliteDataTool
        registry.register(GetSatelliteDataTool(), priority=43)
        logger.info("tool_loaded", tool="get_satellite_data")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_satellite_data", error=str(e))

    # XcAiDb SQL Server 城市历史数据查询工具
    try:
        from app.tools.query.query_xcai_city_history.tool import QueryXcAiCityHistoryTool
        registry.register(QueryXcAiCityHistoryTool(), priority=44)
        logger.info("tool_loaded", tool="query_xcai_city_history")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_xcai_city_history", error=str(e))

    # 运维工单查询工具
    try:
        from app.tools.query.get_working_orders.tool import GetWorkingOrdersTool
        registry.register(GetWorkingOrdersTool(), priority=46)
        logger.info("tool_loaded", tool="get_working_orders")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_working_orders", error=str(e))

    # 通用SQL执行工具
    try:
        from app.tools.query.execute_sql_query.tool import ExecuteSQLQueryTool
        registry.register(ExecuteSQLQueryTool(), priority=47)
        logger.info("tool_loaded", tool="execute_sql_query")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="execute_sql_query", error=str(e))

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
    except ImportError as e:
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

    # IAQI计算功能已整合到 aggregate_data 工具（使用新标准 HJ 633-2024）
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

    try:
        from app.tools.visualization.generate_chart.tool import GenerateChartTool
        registry.register(GenerateChartTool(), priority=200)
        logger.info("tool_loaded", tool="generate_chart")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="generate_chart", error=str(e))

    try:
        from app.tools.visualization.generate_chart.revision_tool import GenerateChartRevisionTool
        registry.register(GenerateChartRevisionTool(), priority=201)
        logger.info("tool_loaded", tool="revise_chart")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="revise_chart", error=str(e))

    try:
        from app.tools.visualization.generate_map.tool import GenerateMapTool
        registry.register(GenerateMapTool(), priority=210)
        logger.info("tool_loaded", tool="generate_map")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="generate_map", error=str(e))

    try:
        from app.tools.analysis.smart_chart_generator.tool import SmartChartGenerator
        registry.register(SmartChartGenerator(), priority=220)
        logger.info("tool_loaded", tool="smart_chart_generator")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="smart_chart_generator", error=str(e))

    try:
        from app.tools.visualization.generate_aqi_calendar import GenerateAQICalendarTool
        registry.register(GenerateAQICalendarTool(), priority=221)
        logger.info("tool_loaded", tool="generate_aqi_calendar")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="generate_aqi_calendar", error=str(e))

    # ========================================
    # Utility Tools（实用工具）
    # ========================================

    try:
        from app.tools.utility.bash_tool import BashTool
        registry.register(BashTool(), priority=500)
        logger.info("tool_loaded", tool="bash")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="bash", error=str(e))

    try:
        from app.tools.utility.execute_python_tool import ExecutePythonTool
        registry.register(ExecutePythonTool(), priority=501)
        logger.info("tool_loaded", tool="execute_python")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="execute_python", error=str(e))

    # ========================================
    # File & Image Tools（文件和图片工具）
    # ========================================

    try:
        from app.tools.utility.read_file_tool import ReadFileTool
        registry.register(ReadFileTool(), priority=501)
        logger.info("tool_loaded", tool="read_file")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="read_file", error=str(e))

    try:
        from app.tools.utility.analyze_image_tool import AnalyzeImageTool
        registry.register(AnalyzeImageTool(), priority=502)
        logger.info("tool_loaded", tool="analyze_image")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="analyze_image", error=str(e))

    try:
        from app.tools.utility.edit_file_tool import EditFileTool
        registry.register(EditFileTool(), priority=503)
        logger.info("tool_loaded", tool="edit_file")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="edit_file", error=str(e))

    try:
        from app.tools.utility.grep_tool import GrepTool
        registry.register(GrepTool(), priority=504)
        logger.info("tool_loaded", tool="grep")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="grep", error=str(e))

    try:
        from app.tools.utility.write_file_tool import WriteFileTool
        registry.register(WriteFileTool(), priority=505)
        logger.info("tool_loaded", tool="write_file")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="write_file", error=str(e))

    try:
        from app.tools.utility.glob_tool import GlobTool
        registry.register(GlobTool(), priority=506)
        logger.info("tool_loaded", tool="search_files")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="search_files", error=str(e))

    try:
        from app.tools.utility.list_directory_tool import ListDirectoryTool
        registry.register(ListDirectoryTool(), priority=507)
        logger.info("tool_loaded", tool="list_directory")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="list_directory", error=str(e))

    try:
        from app.tools.utility.parse_pdf_tool import create_parse_pdf_tool
        registry.register(create_parse_pdf_tool(), priority=508)
        logger.info("tool_loaded", tool="parse_pdf")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="parse_pdf", error=str(e))

    # ========================================
    # Office Automation Tools（Cross-Platform - Phase 1-4）
    # ========================================

    # Phase 1: XML 解包/打包工具（跨平台）
    try:
        from app.tools.office.unpack_tool import UnpackOfficeTool
        registry.register(UnpackOfficeTool(), priority=598)
        logger.info("tool_loaded", tool="unpack_office")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="unpack_office", error=str(e))

    try:
        from app.tools.office.pack_tool import PackOfficeTool
        registry.register(PackOfficeTool(), priority=599)
        logger.info("tool_loaded", tool="pack_office")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="pack_office", error=str(e))

    # Phase 2: Word 高级编辑（跨平台）
    try:
        from app.tools.office.word_edit_tool import WordEditTool
        registry.register(WordEditTool(), priority=593)
        logger.info("tool_loaded", tool="word_edit")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="word_edit", error=str(e))

    try:
        from app.tools.office.accept_changes_tool import AcceptChangesTool
        registry.register(AcceptChangesTool(), priority=596)
        logger.info("tool_loaded", tool="accept_word_changes")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="accept_word_changes", error=str(e))

    try:
        from app.tools.office.find_replace_tool import FindReplaceTool
        registry.register(FindReplaceTool(), priority=597)
        logger.info("tool_loaded", tool="find_replace_word")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="find_replace_word", error=str(e))

    # Phase 3: Excel 公式重算（跨平台）
    try:
        from app.tools.office.excel_recalc_tool import ExcelRecalcTool
        registry.register(ExcelRecalcTool(), priority=595)
        logger.info("tool_loaded", tool="recalc_excel")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="recalc_excel", error=str(e))

    # Phase 4: PPT 幻灯片操作（跨平台）
    try:
        from app.tools.office.add_slide_tool import AddSlideTool
        registry.register(AddSlideTool(), priority=594)
        logger.info("tool_loaded", tool="add_ppt_slide")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="add_ppt_slide", error=str(e))


    # ========================================
    # Scheduled Tasks Tools（定时任务工具）
    # ========================================

    try:
        from app.tools.scheduled_tasks import create_scheduled_task_tool
        registry.register(create_scheduled_task_tool, priority=700)
        logger.info("tool_loaded", tool="create_scheduled_task")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="create_scheduled_task", error=str(e))

    # ========================================
    # Social Mode Tools（社交模式工具 - 呼吸式Agent）
    # ========================================

    try:
        from app.tools.social.schedule_task.tool import ScheduleTaskTool
        registry.register(ScheduleTaskTool(), priority=701)
        logger.info("tool_loaded", tool="schedule_task")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="schedule_task", error=str(e))

    try:
        from app.tools.social.send_notification.tool import SendNotificationTool
        registry.register(SendNotificationTool(), priority=702)
        logger.info("tool_loaded", tool="send_notification")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="send_notification", error=str(e))

    try:
        from app.tools.social.search_history.tool import SearchHistoryTool
        registry.register(SearchHistoryTool(), priority=704)
        logger.info("tool_loaded", tool="search_history")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="search_history", error=str(e))

    try:
        from app.tools.social.web_search.tool import WebSearchTool
        registry.register(WebSearchTool(), priority=705)
        logger.info("tool_loaded", tool="web_search")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="web_search", error=str(e))

    try:
        from app.tools.social.web_search.tool import WebFetchTool
        registry.register(WebFetchTool(), priority=706)
        logger.info("tool_loaded", tool="web_fetch")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="web_fetch", error=str(e))

    # ========================================
    # Social Mode Tools - Background Tasks（后台任务工具）
    # ========================================

    try:
        from app.tools.social.spawn.tool import SpawnTool
        registry.register(SpawnTool(), priority=710)
        logger.info("tool_loaded", tool="spawn")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="spawn", error=str(e))

    # ========================================
    # Task Management Tools（任务管理工具）
    # ========================================

    try:
        from app.tools.task_management.todo_write import todo_write_tool
        registry.register(todo_write_tool, priority=800)
        logger.info("tool_loaded", tool="TodoWrite")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="TodoWrite", error=str(e))

    # ========================================
    # Browser Tools（浏览器工具 - Office Assistant Pattern）
    # ========================================

    try:
        from app.tools.browser.tool import BrowserTool
        registry.register(BrowserTool(), priority=550)
        logger.info("tool_loaded", tool="browser")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="browser", error=str(e))

    # ========================================
    # Agent Tools（Agent间调用工具）
    # ========================================

    try:
        from app.tools.agent_tools.call_sub_agent import CallSubAgentTool
        # 注意：CallSubAgentTool需要延迟初始化（在ReActLoop中注入依赖）
        # 这里创建一个占位符工具，真实的工具实例在executor中创建
        call_sub_agent_tool = CallSubAgentTool()
        registry.register(call_sub_agent_tool, priority=900)
        logger.info("tool_loaded", tool="call_sub_agent")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="call_sub_agent", error=str(e))

    # ========================================
    # Code Tools（编程模式工具）
    # ========================================

    try:
        from app.tools.code.validate_tool import ValidateToolTool
        registry.register(ValidateToolTool(), priority=850)
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
        registry.register(ReadDocxTool(), priority=459)
        logger.info("tool_loaded", tool="read_docx")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="read_docx", error=str(e))

    try:
        from app.tools.workflow.knowledge_qa_workflow import KnowledgeQAWorkflow
        registry.register(KnowledgeQAWorkflow(), priority=48)
        logger.info("tool_loaded", tool="knowledge_qa_workflow")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="knowledge_qa_workflow", error=str(e))

    # ========================================
    # Planning Tools（规划工具）
    # ========================================

    try:
        from app.tools.planning.complex_query_planner.tool import ComplexQueryPlannerTool
        registry.register(ComplexQueryPlannerTool(), priority=55)
        logger.info("tool_loaded", tool="complex_query_planner")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="complex_query_planner", error=str(e))

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

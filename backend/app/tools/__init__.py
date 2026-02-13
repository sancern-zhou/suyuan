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
   - get_particulate_data - 颗粒物组分数据查询（端口9093）

2. Analysis Tools - 分析工具（执行计算和分析）
   - analyze_upwind_enterprises - 上风向企业分析（广东省）
   - calculate_pm_pmf - PM2.5/PM10颗粒物PMF源解析（广东省超级站）
   - calculate_vocs_pmf - VOCs挥发性有机物PMF源解析（仅用于臭氧溯源）
   - calculate_obm_full_chemistry - OBM/EKMA完整化学机理分析（RACM2, 102物种, 504反应）

3. Visualization Tools - 可视化工具（生成图表和地图配置）
   **图表工具职责分工：**
   - smart_chart_generator (智能工具) - 固定格式数据专用
     * 适用：PMF/OBM分析结果、组分数据、已存储数据
     * 特征：从统一存储加载（data_id）、智能推荐图表类型
   - generate_chart (通用工具) - 动态数据专用
     * 适用：直接传入数据、自定义场景、预定义场景模板
     * 特征：直接传入数据（data）、模板库+LLM生成
   - generate_map - 生成高德地图配置

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

    try:
        from app.tools.query.get_particulate_data.tool import GetParticulateDataTool
        registry.register(GetParticulateDataTool(), priority=62)
        logger.info("tool_loaded", tool="get_particulate_data")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_particulate_data", error=str(e))

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
        from app.tools.query.get_guangdong_regular_stations.tool import GetGuangdongRegularStationsTool
        registry.register(GetGuangdongRegularStationsTool(), priority=30)
        logger.info("tool_loaded", tool="get_guangdong_regular_stations")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_guangdong_regular_stations", error=str(e))

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
        from app.tools.query.query_gd_suncere.tool_wrapper import QueryGDSuncereRegionalComparisonTool
        registry.register(QueryGDSuncereRegionalComparisonTool(), priority=33)
        logger.info("tool_loaded", tool="query_gd_suncere_regional_comparison")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="query_gd_suncere_regional_comparison", error=str(e))

    try:
        from app.tools.query.get_satellite_data.tool import GetSatelliteDataTool
        registry.register(GetSatelliteDataTool(), priority=35)
        logger.info("tool_loaded", tool="get_satellite_data")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="get_satellite_data", error=str(e))

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
        from app.tools.analysis.pybox_integration.tool import CalculateOBMFullChemistryTool
        registry.register(CalculateOBMFullChemistryTool(), priority=126)
        logger.info("tool_loaded", tool="calculate_obm_full_chemistry", version="racm2")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="calculate_obm_full_chemistry", error=str(e))

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

    try:
        from app.tools.analysis.iaqi_calculator.tool import IAQICalculatorTool
        registry.register(IAQICalculatorTool(), priority=145)
        logger.info("tool_loaded", tool="calculate_iaqi")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="calculate_iaqi", error=str(e))

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

    # ========================================
    # Utility Tools（实用工具）
    # ========================================

    try:
        from app.tools.utility.bash_tool import BashTool
        registry.register(BashTool(), priority=500)
        logger.info("tool_loaded", tool="bash")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="bash", error=str(e))

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

    # ========================================
    # Office Automation Tools（Windows Only - Win32 COM）
    # ========================================

    try:
        from app.tools.office.word_tool import WordWin32LLMTool
        registry.register(WordWin32LLMTool(), priority=600)
        logger.info("tool_loaded", tool="word_processor")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="word_processor", error=str(e))

    try:
        from app.tools.office.excel_tool import ExcelWin32LLMTool
        registry.register(ExcelWin32LLMTool(), priority=601)
        logger.info("tool_loaded", tool="excel_processor")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="excel_processor", error=str(e))

    try:
        from app.tools.office.ppt_tool import PPTWin32LLMTool
        registry.register(PPTWin32LLMTool(), priority=602)
        logger.info("tool_loaded", tool="ppt_processor")
    except ImportError as e:
        logger.warning("tool_import_failed", tool="ppt_processor", error=str(e))

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

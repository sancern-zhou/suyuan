"""
通用SQL执行工具

支持Agent直接执行SQL查询语句访问SQL Server历史数据库。
复用SQLValidator进行安全验证。
"""

from typing import Dict, Any, Optional, TYPE_CHECKING, List
import pyodbc
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.sql_validator import SQLValidator

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext


logger = structlog.get_logger()


MONITORING_SQL_TABLES = [
    'era5_reanalysis_data',
    'observed_weather_data',
    'weather_stations',
    'weather_data_cache',
    'fire_hotspots',
    'dust_forecasts',
    'dust_events',
    'air_quality_forecast',
    'city_aqi_publish_history',
    'CityDayAQIPublishHistory',
    'CityAQIPublishHistory',
    'CurrentAirQuality',
    'OpenMeteoAirQualityForecast72h',
    'dbo.OpenMeteoAirQualityForecast72h',
    'dat_station_day',
    'dat_station_hour',
    'dat_weather_hour',
    'dat_zhongda_station_minute',
    'dat_zhongda_station_hour',
    'dat_zhongda_station_day',
    'dat_zhongda_city_hour',
    'dat_zhongda_city_day',
    'HenanCityAccumulateRanking',
    'WeatherForecast7Day',
    'city_168_statistics_new_standard',
    'city_168_statistics_old_standard',
    'province_statistics_new_standard',
    'province_statistics_old_standard',
    'noise_city_compliance_monthly',
    'noise_city_compliance_daily',
    'qc_history',
    'quality_control_records',
    'analysis_history',
    'BSD_STATION',
    'information_schema.columns',
    'information_schema.tables',
]


AIR_QUALITY_SCHEMA_GUIDE = (
    "\n\n【高频空气质量表字段契约】"
    "\n以下字段已经确认；查询这些表时直接生成SQL，不要先调用describe_table。"
    "仅当需要契约未列出的字段，或数据库返回字段错误时，才调用describe_table。"
    "\n- 地理参数规则：城市名称和行政区代码从当前项目上下文或用户长期记忆获取，"
    "本工具不内置特定项目的地理信息。SQL中的{city_name}和{city_code}仅表示模板变量，"
    "执行前必须替换为上下文中的实际值，不得把模板变量原样写入SQL。"
    "若上下文缺少名称与代码的映射，应补充地理上下文；describe_table只能查询字段，不能提供该映射。"
    "不同表的城市字段不同，禁止跨表套用字段名。"
    "\n【数据源优先级】站点小时/站点日/城市小时/城市日数据同时存在通用发布表"
    "（dat_station_hour、dat_station_day、CityAQIPublishHistory、CityDayAQIPublishHistory）"
    "和中大平台表（dat_zhongda_station_hour、dat_zhongda_station_day、dat_zhongda_city_hour、"
    "dat_zhongda_city_day）两个来源时，优先查询中大平台表（dat_zhongda_*）——中大源为审核后数据，"
    "准确性更高。仅当中大表不覆盖所需时间（如城市聚合滞后约1天）或字段缺失时，再用通用发布表补充。"
    "站点5分钟数据（dat_zhongda_station_minute）为中大独有，无此冲突。"
    "\n- CurrentAirQuality（城市当前实况及今明两天预报摘要）："
    "城市字段为CityID，按行政区代码筛选：CityID = '{city_code}'；"
    "没有cityname、Area、CityCode，不得把城市名称写入CityID。"
    "污染物字段：AQI, PM25, PM10, O3, SO2, NO2, CO；"
    "等级与首要污染物：AQILevel, MaxPollution；"
    "实况与更新时间：WeatherCondition, Temperature, WindPower, Humidity, RecordTime, UpdateTime；"
    "今日字段：TodayCondition, TodayMinAqi, TodayMaxAqi, TodayMaxPollution, TodayTemp；"
    "明日字段：TomorrowCondition, TomorrowMinAqi, TomorrowMaxAqi, TomorrowMaxPollution, TomorrowTemp。"
    "当前实况示例：SELECT TOP 1 CityID, AQI, PM25, PM10, O3, SO2, NO2, CO, "
    "AQILevel, MaxPollution, RecordTime, UpdateTime FROM dbo.CurrentAirQuality "
    "WHERE CityID = '{city_code}' ORDER BY UpdateTime DESC。"
    "\n- CityAQIPublishHistory（城市小时历史）："
    "城市字段为Area和CityCode，按城市全称或行政区代码筛选："
    "Area = N'{city_name}'或CityCode = {city_code}；"
    "没有cityname、CityID。时间字段为TimePoint；"
    "污染物字段为PM2_5, PM10, O3, NO2, SO2, CO, AQI；"
    "其他字段为PrimaryPollutant, Quality。注意PM2.5字段名是PM2_5，不是PM25。"
    "注意：与dat_zhongda_city_hour数据重复，优先使用中大表（审核后数据），本表仅作补充。"
    "\n- CityDayAQIPublishHistory（城市日历史）："
    "城市字段为Area和CityCode，按城市全称或行政区代码筛选："
    "Area = N'{city_name}'或CityCode = {city_code}；"
    "时间字段为TimePoint；日均字段为PM2_5_24h, PM10_24h, O3_8h_24h, "
    "NO2_24h, SO2_24h, CO_24h；其他字段为AQI, PrimaryPollutant, Quality。"
    "注意：与dat_zhongda_city_day数据重复，优先使用中大表（审核后数据），本表仅作补充。"
            "\n- dat_station_hour（站点小时）和dat_station_day（站点日）："
            "城市字段为city_area_code，按行政区代码筛选：city_area_code = '{city_code}'；"
            "站点字段为station_id, name, lon, lat；时间字段为data_time；"
            "污染物字段使用小写：aqi, aqi_level, pm25, pm10, o3, no2, so2, co, pollutant；"
            "dat_station_day另有O38h字段。没有cityname、CityID、Area、CityCode。"
            "注意：与dat_zhongda_station_hour/dat_zhongda_station_day数据重复，优先使用中大表（审核后数据），本表仅作补充。"
            "\n- dat_zhongda_station_minute（中大平台站点5分钟）和dat_zhongda_station_hour（中大平台站点小时）："
            "城市字段为area，按城市全称筛选：area = N'{city_name}'；"
            "站点字段为station_code（平台内部编码，数字+字母如'1003A'）和station_name；时间字段为time_point；"
            "没有city_area_code、cityname、CityID、CityCode、station_id。"
            "口径字段必须显式过滤：data_table_type（'Act'实况/'Std'标况）、parameter_type（'gp'常规污染物），"
            "当前仅采集'Act'+'gp'口径。"
            "污染物数值字段小写：aqi, api, so2, no_val, no2, nox, o3, co, pm10, pm25, o3_8h, pm1；"
            "NO浓度列名是no_val，不是no；单位co为mg/m3，其余为μg/m3。"
            "每个数值字段另有对应质量标记列（如pm25_mark、o3_mark），"
            "非空值（H/B/BB/W/HSp/LSp/PS/PZ/AS/CZ/CS/RM）表示该值带质量标记，慎用于统计。"
            "-99为平台无效值，统计前必须排除（如AND pm25 <> -99）；NULL表示缺失。"
            "分钟表每5分钟一条，小时表整点一条，小时口径为审核后(App)。"
            "示例：SELECT TOP 60 station_code, station_name, time_point, aqi, pm25, pm10, o3, so2, no2, co "
            "FROM dbo.dat_zhongda_station_minute WHERE area = N'{city_name}' "
            "AND data_table_type = 'Act' AND parameter_type = 'gp' AND time_point >= '2026-08-26 18:00' "
            "ORDER BY time_point DESC。"
            "\n- dat_zhongda_station_day（中大平台站点日均，审核后）："
            "城市/站点/口径字段与分钟表规则一致（area=N'{city_name}'、station_code、data_table_type、parameter_type），"
            "但时间为data_date（DATE类型），另有unique_code、standard='AQI'、data_source_type='App'、"
            "pollutant（首要污染物）、quality_type（类别）、quality_level（等级）；"
            "污染物单位已统一换算为μg/m3（CO为mg/m3），与分钟/小时表一致；-99仍为无效值需排除。"
            "\n- dat_zhongda_city_hour（中大平台城市小时）和dat_zhongda_city_day（中大平台城市日均）："
            "城市字段为area（按城市全称筛选area = N'{city_name}'），另有city_code、province字段；"
            "city_hour时间为time_point，city_day时间为data_date；"
            "两表均含data_type_plan（评价规划期，按数据时间互斥分区："
            "2026-01-01起为'155th'十五五，2021~2025为'145th'十四五，更早为'135th'；"
            "查询2026年数据必须加data_type_plan = '155th'，用错规划期会返回空）；"
            "city_day另有data_source_type='SubstitutionBack'（替代回算）和description。"
            "字段为小写污染物列：so2, no_val, no2, nox, o3, co, pm10, pm25, pm1，city_day另有o3_1h、o3_8h；"
            "评价字段city_hour为aqi/quality/pollutant，city_day为aqi/pollutant/quality_type/quality_level；"
            "两表均含第二组评价字段（aqi_2/quality_2/pollutant_2或pm10_2/pm25_2，city_day无quality_2）；"
            "city_day质量标记列为<污染物>_mark形式（如so2_mark、pm2_5_mark）；"
            "城市表数值为平台返回原值（当前无数据，单位未经核实，跨表统计前先抽样核对）。"
            "城市表无效占位值为-999（区别于站点表的-99），统计前必须排除（如AND aqi <> -999）。"
            "注意：城市表由平台聚合任务生成，可能为空，查询无结果不代表SQL错误。"
            "\n- HenanCityAccumulateRanking（河南省城市月/年累计空气质量排名）："
            "period_type区分monthly（月累计）/yearly（年累计），period为YYYY-MM或YYYY；"
            "城市字段为city，按全称筛选如city = N'郑州'；排名为city_rank（1最优）；"
            "is_pro_city=1为省辖市，0为市平均/县平均等汇总行；"
            "指标字段：zong（综合指数）, pm25, pm10, so2, no2, co, o3；"
            "同比字段：zong_change_rate（如N'5.6%'文本）, change_rate, ratio；"
            "天数字段：valid_days（有效天数）, pm_valid_days, o3_exceed_days, heavy_pollution_days；"
            "统计区间stat_start/stat_end；当期数据每日抓取整体更新，lastyear_json存去年同期行。"
            "示例：SELECT TOP 30 city, city_rank, zong, pm25, valid_days FROM dbo.HenanCityAccumulateRanking "
            "WHERE period_type = 'monthly' AND period = '2026-08' ORDER BY city_rank。"
    "\n- WeatherForecast7Day（7天空气质量预报）："
    "城市字段为cityname，按城市全称筛选：cityname = N'{city_name}'；时间字段为TimePoint；"
    "预报字段为DayTitle, MinAqi, MaxAqi, MaxPollution, WeatherCondition, "
    "Temperature, WindLevel, WindDirection, UpdateDate, UpdateTime。"
    "cityname仅用于此预报表，不得用于CurrentAirQuality或城市、站点历史表。"
)


OPS_SQL_TABLES = [
    # 系统管理
    'sys_user',
    'sys_department',
    'wfl_workflow',
    'wfl_task',
    # 运维工单与站点设备基础信息
    'working_orders',
    'working_order_details',
    'wo_commonfile_links',
    'WO_COMMONFILE',
    'base_station',
    'base_station_sup',
    'base_device',
    'base_user_station',
    'base_department_station',
    'base_contract_station',
    'BSD_STATION',
    # 周检表
    'RF_W_GASEOUSCHECK_CO',
    'RF_W_GASEOUSCHECK_NOX',
    'RF_W_GASEOUSCHECK_O3',
    'RF_W_GASEOUSCHECK_SO2',
    'RF_W_GrainCalibrationCheck_PM10',
    'RF_W_GrainCalibrationCheck_PM25',
    'RF_W_GrainCalibrationCheckAttach',
    'RF_W_INSPECTION',
    'RF_W_INSPECTIONSUMMARY',
    'RF_W_LONGOPTICALPATH',
    'RF_W_OTHERDEVICECHECK',
    'RF_W_PMCHECK',
    'RF_W_STANDARD_ALL',
    # 双周表
    'RF_TW_CleanCuttingHead',
    'RF_TW_PmFlowCalibrate',
    'RF_TW_PmFlowCheck',
    # 月检表
    'RF_M_GASEOUSCALICHECK',
    'RF_M_GASEOUSCALIDEVICECHECK',
    'RF_M_GASEOUSFLOWCHECK',
    'RF_M_MANUALCOMPARISON',
    'RF_M_MANUALCOMPARISONDETAIL',
    'RF_M_MEMBRANEWEIGHING',
    'RF_M_PMDEVICEMAINTAIN',
    'RF_M_STATIONDEVICEMAINTAIN',
    'RF_M_StationMaintainCheck',
    # 季检表
    'RF_Q_GASEOUSMULTIPOINT_CO',
    'RF_Q_GASEOUSMULTIPOINT_NO2',
    'RF_Q_GASEOUSMULTIPOINT_O3',
    'RF_Q_GASEOUSMULTIPOINT_SO2',
    'RF_Q_GASEOUSPRECISION_CO',
    'RF_Q_GASEOUSPRECISION_NO2',
    'RF_Q_GASEOUSPRECISION_O3',
    'RF_Q_GASEOUSPRECISION_SO2',
    'RF_Q_GaseousFlowCheck',
    'RF_Q_LONGOPTICALPATH_NO2',
    'RF_Q_LONGOPTICALPATH_O3',
    'RF_Q_LONGOPTICALPATH_SO2',
    'RF_Q_PM10RUNSTATUSCHECK',
    'RF_Q_PM25RUNSTATUSCHECK',
    'RF_Q_PMPRESSURE',
    'RF_Q_STATIONDEVICECLEAN',
    'RF_Q_StationMaintainCheck',
    # 其他现场表
    'RF_SEC_INSPECTION',
    'RF_SEC_INSTRUMENTRECORD',
    'RF_SEC_MONITORINGCHECK',
    'RF_PM1MonitorInspection',
    'RF_BCMonitorInspection',
    # 现场检查表
    'SEC_CHECKSCORE',
    'SEC_CHECKSCORE_SX',
    'SEC_CHECKSCORE_SXNEW',
    # 年度/应急维护表
    'RF_Y_DEVICECHANGE',
    'RF_Y_DEVICEREPAIR',
    'RF_Y_PreventiveMaintenance',
    # 超站表单
    'Sup_RF_MonthNepheloMeterCheck',
    'Sup_RF_NepheloMeterCalibration',
    # 海盐运维表单
    'RF_HY_EnvironmentHumidity',
    'RF_HY_GASEOUSCALIDEVICECHECK',
    'RF_HY_NOXCONVERSIONRATE',
    'RF_HY_O3VALUEPASS',
    'RF_HY_STATIONDEVICEMAINTAIN',
    'RF_HY_StationMaintainCheck',
    'RF_HY_VISIBILITYCALI',
    # 质控校准管理表
    'qa_appraisalcalibrationlog',
    'qa_appraisalcalibrationmanagem',
    'qa_calibrationpass',
    'qa_ozonecalibration',
    'qa_ozonetransfer',
    'qa_standardmateriallog',
    'qa_standardmaterialstorage',
]


TENDER_SQL_TABLES = [
    'tender_notices',
    'tender_notice_contents',
    'tender_candidates',
    'tender_fetch_runs',
]


class BaseSQLQueryTool(LLMTool):
    """
    通用SQL执行工具

    使用场景：
    - 直接执行SQL查询语句访问SQL Server历史数据库
    - 查看表结构信息
    - 支持复杂查询、JOIN、聚合等SQL操作

    安全机制：
    - 只允许SELECT查询
    - 禁止DROP/DELETE/UPDATE/INSERT等操作
    - 表名白名单验证
    - 最大返回1000条记录
    """

    # 默认返回记录数限制
    DEFAULT_LIMIT = 50

    def __init__(
        self,
        *,
        tool_name: str,
        tool_description: str,
        schema_description: str,
        allowed_tables: List[str],
        default_database: str = "XcAiDb",
        allow_information_schema_sql: bool = True,
    ):
        """初始化工具"""

        self.tool_name = tool_name
        self.default_database = default_database
        self.allow_information_schema_sql = allow_information_schema_sql
        self.sql_validator = SQLValidator(max_limit=1000, allowed_tables=allowed_tables)

        function_schema = {
            "name": tool_name,
            "description": schema_description,
            "parameters": {
                "type": "object",
                "properties": {
                    "describe_table": {
                        "type": "string",
                        "description": "查看表结构（与sql二选一），输入目标表名"
                    },
                    "sql": {
                        "type": "string",
                        "description": "SQL SELECT查询语句（与describe_table二选一）"
                    },
                    "database": {
                        "type": "string",
                        "description": f"数据库名称，默认{default_database}",
                        "enum": ["XcAiDb", "AirPollutionAnalysis"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回记录数限制（默认50，最大1000，仅用于sql查询）",
                        "default": 50
                    }
                }
            }
        }

        super().__init__(
            name=tool_name,
            description=tool_description,
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.3.0",
            requires_context=True  # 启用ExecutionContext以支持数据外部化
        )

    async def execute(self, context: Optional["ExecutionContext"] = None, describe_table: Optional[str] = None, sql: Optional[str] = None, database: Optional[str] = None, limit: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        """
        执行工具

        Args:
            context: 执行上下文（用于数据外部化）
            describe_table: 查看表结构（与sql二选一，不能为空）
            sql: SQL查询语句（与describe_table二选一）
            database: 数据库名称（可选，默认'XcAiDb'）
            limit: 返回记录数限制

        Returns:
            查询结果或表结构信息
        """

        # 参数验证：describe_table 和 sql 二选一
        if describe_table and sql:
            return {
                "success": False,
                "data": None,
                "summary": "describe_table 和 sql 参数不能同时使用，请只提供其中一个"
            }

        if not describe_table and not sql:
            return {
                "success": False,
                "data": None,
                "summary": "请提供 describe_table（查看表结构）或 sql（执行查询）参数，二者必选其一"
            }

        # describe_table 不能为空字符串
        if describe_table is not None and not describe_table.strip():
            return {
                "success": False,
                "data": None,
                "summary": "describe_table 参数不能为空，请输入有效的表名"
            }

        # 设置默认数据库
        if database is None:
            database = self.default_database

        # 验证数据库名称
        if database not in ["XcAiDb", "AirPollutionAnalysis"]:
            return {
                "success": False,
                "data": None,
                "summary": f"不支持的数据库名称 '{database}'。支持的数据库：XcAiDb、AirPollutionAnalysis"
            }

        # 判断是查看表结构还是执行SQL
        if describe_table:
            return self._describe_table(describe_table, database)
        else:
            return await self._execute_sql_query(sql, database, limit, context)

    def _describe_table(self, table_name: str, database: str) -> Dict[str, Any]:
        """
        查看表结构（动态从数据库获取）

        Args:
            table_name: 表名
            database: 数据库名称

        Returns:
            表结构信息 + 1条最新数据样例
        """
        # 验证表名是否在白名单中
        if table_name not in self.sql_validator.ALLOWED_TABLES:
            return {
                "success": False,
                "data": None,
                "summary": f"表 '{table_name}' 不在白名单中。可用表: {', '.join(self.sql_validator.ALLOWED_TABLES)}"
            }

        # 过滤掉系统视图
        if table_name.startswith('information_schema'):
            return {
                "success": False,
                "data": None,
                "summary": f"不能查询系统视图 '{table_name}' 的结构"
            }

        try:
            # 动态查询表结构（支持多种schema：dbo, guest, sys等）
            # 先尝试查询表所在的schema
            schema_sql = f"""
                SELECT TABLE_SCHEMA
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_NAME = '{table_name}'
            """
            schemas = self._execute_query(schema_sql, database)

            # 构建查询条件
            if schemas:
                # 如果找到表，使用找到的schema
                schema_list = [s['TABLE_SCHEMA'] for s in schemas]
                where_clause = " OR ".join([f"(TABLE_SCHEMA = '{s}' AND TABLE_NAME = '{table_name}')" for s in schema_list])
            else:
                # 如果没找到，尝试常见schema
                where_clause = f"(TABLE_SCHEMA = 'dbo' AND TABLE_NAME = '{table_name}') OR " \
                              f"(TABLE_SCHEMA = 'guest' AND TABLE_NAME = '{table_name}') OR " \
                              f"(TABLE_NAME = '{table_name}')"

            sql = f"""
                SELECT
                    COLUMN_NAME,
                    DATA_TYPE,
                    CHARACTER_MAXIMUM_LENGTH,
                    IS_NULLABLE,
                    COLUMN_DEFAULT,
                    TABLE_SCHEMA
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE {where_clause}
                ORDER BY TABLE_SCHEMA, ORDINAL_POSITION
            """

            columns = self._execute_query(sql, database)

            if not columns:
                # 如果还是找不到，列出数据库中所有表（用于调试）
                all_tables_sql = """
                    SELECT TABLE_SCHEMA, TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE = 'BASE TABLE'
                    ORDER BY TABLE_SCHEMA, TABLE_NAME
                """
                all_tables = self._execute_query(all_tables_sql, database)

                # 查找可能相似的表名
                similar_tables = [t['TABLE_NAME'] for t in all_tables
                                 if table_name.lower() in t['TABLE_NAME'].lower()]

                hint = ""
                if similar_tables:
                    hint = f"\n\n相似的表名: {', '.join(similar_tables[:5])}"
                else:
                    # 列出前10个表作为参考
                    sample_tables = [f"{t['TABLE_SCHEMA']}.{t['TABLE_NAME']}" for t in all_tables[:10]]
                    hint = f"\n\n数据库中的前10个表: {', '.join(sample_tables)}"

                return {
                    "success": False,
                    "data": None,
                    "summary": f"未找到表 '{table_name}' 的结构信息。{hint}"
                }

            # 获取schema信息（使用第一个schema）
            table_schema = columns[0].get('TABLE_SCHEMA', 'dbo')
            full_table_name = f"{table_schema}.{table_name}"

            # 获取1条最新数据样例（尝试通过日期字段排序）
            sample_sql = self._build_sample_sql(full_table_name, columns)
            sample_data = self._execute_query(sample_sql, database)

            # 格式化字段列表（包含schema信息）
            fields_text = "\n".join([
                f"  - {col['COLUMN_NAME']} ({col['DATA_TYPE']}{'(' + str(col['CHARACTER_MAXIMUM_LENGTH']) + ')' if col['CHARACTER_MAXIMUM_LENGTH'] else ''}, {'可空' if col['IS_NULLABLE'] == 'YES' else '非空'})"
                for col in columns
            ])

            # 格式化数据样例
            sample_text = ""
            if sample_data:
                sample_record = sample_data[0]
                sample_text = "\n最新数据样例:\n"
                for col in columns:
                    col_name = col['COLUMN_NAME']
                    value = sample_record.get(col_name, "NULL")
                    # 截断过长的字符串
                    if isinstance(value, str) and len(value) > 50:
                        value = value[:50] + "..."
                    sample_text += f"  {col_name}: {value}\n"
            else:
                sample_text = "\n数据样例: 表中暂无数据\n"

            result = {
                "success": True,
                "data": {
                    "table_name": table_name,
                    "full_table_name": full_table_name,
                    "table_schema": table_schema,
                    "database": database,
                    "columns": columns,
                    "sample_data": sample_data[0] if sample_data else None
                },
                "summary": f"""表名: {full_table_name} (数据库: {database})

字段列表:
{fields_text}

字段总数: {len(columns)}
{sample_text}提示：使用 {self.tool_name}(sql='SELECT TOP 200 * FROM {full_table_name}', database='{database}') 查看更多数据"""
            }

            logger.info(
                "table_schema_described",
                table_name=table_name,
                field_count=len(columns),
                has_sample=len(sample_data) > 0
            )

            return result

        except Exception as e:
            logger.error("describe_table_failed", table_name=table_name, error=str(e))
            return {
                "success": False,
                "data": None,
                "summary": f"查询表结构失败: {str(e)}"
            }

    async def _execute_sql_query(self, sql: str, database: str, limit: Optional[int], context: Optional["ExecutionContext"]) -> Dict[str, Any]:
        """
        执行SQL查询

        Args:
            sql: SQL查询语句
            database: 数据库名称
            limit: 返回记录数限制
            context: 执行上下文

        Returns:
            查询结果（data外部化）
        """

        # 设置默认限制
        if limit is None:
            limit = self.DEFAULT_LIMIT

        # 确保限制不超过最大值
        limit = min(limit, self.sql_validator.max_limit)

        logger.info(
            "sql_query_start",
            database=database,
            sql_preview=sql[:100] if len(sql) > 100 else sql,
            limit=limit,
            session_id=getattr(context, 'session_id', 'unknown') if context else 'unknown'
        )

        try:
            sql = self.sql_validator.normalize_sql(sql)

            # 运维模式不允许通过 information_schema 做表名发现式查询。
            # 查看单表字段请走 describe_table，表名必须来自工具说明中的白名单。
            if not self.allow_information_schema_sql:
                referenced_tables = self.sql_validator.extract_tables(sql)
                information_schema_tables = [
                    table for table in referenced_tables
                    if table.lower().startswith("information_schema.")
                ]
                if information_schema_tables:
                    return {
                        "success": False,
                        "data": [],
                        "summary": (
                            "运维模式不允许表名发现式查询，不能直接查询 "
                            f"{', '.join(information_schema_tables)}。"
                            "请只使用 execute_ops_sql_query 工具说明中列出的白名单表单；"
                            "如果字段不确定，请调用 "
                            "execute_ops_sql_query(describe_table='白名单表名', database='AirPollutionAnalysis') "
                            "查看该表字段和样例。"
                        ),
                    }

            # 1. SQL安全验证
            is_valid, error_msg = self.sql_validator.validate(sql)
            if not is_valid:
                logger.warning(
                    "sql_validation_failed",
                    error=error_msg,
                    sql_preview=sql[:100]
                )
                return {
                    "success": False,
                    "data": [],
                    "summary": f"SQL验证失败: {error_msg}。请使用 {self.tool_name}(describe_table='表名', database='{database}') 查看正确的表结构信息。"
                }

            # 2. 添加TOP子句（SQL Server使用TOP而非LIMIT）
            safe_sql = self._sanitize_limit_for_sqlserver(sql, limit)

            # 3. 执行查询
            results = self._execute_query(safe_sql, database)

            logger.info(
                "sql_query_success",
                database=database,
                result_count=len(results),
                sql_preview=sql[:100]
            )

            # 4. 数据外部化：超过24条记录时采样
            sample_data = results
            file_path = None

            if context and len(results) > 24:
                try:
                    # 动态提取列名作为元数据
                    if results:
                        columns = list(results[0].keys())
                    else:
                        columns = []

                    # 保存完整数据
                    file_path = context.save_data(
                        data=results,
                        schema="sql_query_result",  # 通用schema
                        metadata={
                            "database": database,
                            "sql": sql,
                            "row_count": len(results),
                            "columns": columns,
                            "limit": limit
                        }
                    )

                    # 智能采样：前12条 + 后12条（Head-Tail采样）
                    sample_count = 24
                    head_size = sample_count // 2
                    tail_size = sample_count - head_size
                    head = results[:head_size]
                    tail = results[-tail_size:]
                    sample_data = head + tail

                    logger.info(
                        "sql_query_data_externalized",
                        total_count=len(results),
                        sample_count=len(sample_data),
                        file_path=file_path
                    )

                    return {
                        "success": True,
                        "data": sample_data,  # 只返回样本数据
                        "file_path": file_path,    # 完整数据文件路径
                        "count": len(results),
                        "sample_count": len(sample_data),
                        "summary": f"查询到{len(results)}条记录（已外部化，返回样本{len(sample_data)}条）",
                        "metadata": {
                            "database": database,
                            "columns": columns,
                            "externalized": True,
                            "hint": "如果结果中包含英文代码值（如Fault、Check等），请转换为中文向用户展示"
                        }
                    }
                except Exception as save_error:
                    logger.warning("sql_query_save_failed", error=str(save_error))
                    # 外部化失败，降级到返回全部数据
                    file_path = None

            # 未外部化，返回全部数据
            return {
                "success": True,
                "data": results,
                "file_path": file_path,
                "count": len(results),
                "summary": f"查询到{len(results)}条记录",
                "metadata": {
                    "hint": "如果结果中包含英文代码值（如Fault、Check等），请转换为中文向用户展示"
                }
            }

        except pyodbc.ProgrammingError as e:
            # SQL语法错误或字段名错误
            error_msg = str(e)
            logger.error(
                "sql_syntax_error",
                error=error_msg,
                sql_preview=sql[:100]
            )

            # 提取表名
            table_name = self._extract_table_name(sql)
            hint = ""
            if table_name:
                hint = f" 请使用 {self.tool_name}(describe_table='{table_name}', database='{database}') 查看正确的字段名。"

            return {
                "success": False,
                "data": [],
                "summary": f"SQL执行失败: {error_msg}.{hint}"
            }

        except Exception as e:
            logger.error(
                "sql_query_failed",
                error=str(e),
                error_type=type(e).__name__,
                sql_preview=sql[:100]
            )
            return {
                "success": False,
                "data": [],
                "summary": f"查询失败: {str(e)}。请使用 {self.tool_name}(describe_table='表名', database='{database}') 查看正确的表结构信息。"
            }

    def _sanitize_limit_for_sqlserver(self, sql: str, limit: int) -> str:
        """
        为SQL Server添加TOP子句（SQL Server不支持LIMIT）

        Args:
            sql: SQL查询语句
            limit: 限制行数

        Returns:
            添加了TOP的SQL语句
        """
        import re

        # 检查是否已有TOP
        top_match = re.search(r'\bTOP\s+(\d+)', sql, re.IGNORECASE)
        if top_match:
            # 已有TOP，检查是否超过最大值
            top_value = int(top_match.group(1))
            if top_value > self.sql_validator.max_limit:
                # 替换为最大值
                sql = re.sub(
                    r'\bTOP\s+\d+',
                    f'TOP {self.sql_validator.max_limit}',
                    sql,
                    flags=re.IGNORECASE
                )
            return sql
        else:
            # 添加TOP子句
            # 匹配 SELECT 后面的内容，在 SELECT 和第一个字段之间插入 TOP
            select_match = re.search(r'\bSELECT\s+', sql, re.IGNORECASE)
            if select_match:
                select_end = select_match.end()
                # 检查是否已经有 DISTINCT 等关键字
                distinct_match = re.search(r'\bSELECT\s+(DISTINCT|ALL)\s+', sql, re.IGNORECASE)
                if distinct_match:
                    # 在 DISTINCT 之后插入 TOP
                    insert_pos = distinct_match.end()
                    return sql[:insert_pos] + f' TOP {limit} ' + sql[insert_pos:]
                else:
                    # 在 SELECT 之后直接插入 TOP
                    return sql[:select_end] + f'TOP {limit} ' + sql[select_end:]

            return sql

    def _build_sample_sql(self, table_name: str, columns: list) -> str:
        """
        构建获取最新数据样例的SQL（智能检测日期字段排序）

        Args:
            table_name: 表名
            columns: 字段信息列表

        Returns:
            SQL查询语句
        """
        # 检测常见的日期/时间字段名
        date_keywords = ['date', 'time', 'created', 'updated', 'modified', 'stat_date', 'create_time', 'update_time']
        date_column = None

        for col in columns:
            col_name_lower = col['COLUMN_NAME'].lower()
            # 检查是否是日期类型字段
            if col['DATA_TYPE'] in ('datetime', 'datetime2', 'date', 'timestamp'):
                # 优先匹配包含日期关键词的字段
                for keyword in date_keywords:
                    if keyword in col_name_lower:
                        date_column = col['COLUMN_NAME']
                        break
                # 如果还没找到，使用第一个日期类型字段
                if not date_column:
                    date_column = col['COLUMN_NAME']

        # 构建SQL
        if date_column:
            # 使用日期字段排序获取最新记录
            return f"SELECT TOP 1 * FROM {table_name} ORDER BY {date_column} DESC"
        else:
            # 没有日期字段，直接取1条
            return f"SELECT TOP 1 * FROM {table_name}"

    def _extract_table_name(self, sql: str) -> Optional[str]:
        """从SQL中提取表名"""
        import re
        sql_lower = sql.lower()

        # 尝试提取FROM后的表名
        from_match = re.search(r'\bfrom\s+(\w+)', sql_lower)
        if from_match:
            table = from_match.group(1)
            # 检查是否在白名单中（排除系统视图）
            if table in self.sql_validator.ALLOWED_TABLES and not table.startswith('information_schema'):
                return table

        return None

    def _get_connection_string(self, database: str) -> str:
        """获取数据库连接字符串"""
        try:
            from config.settings import Settings
            settings = Settings()

            # 替换数据库名称
            conn_str = settings.sqlserver_connection_string
            # 替换 DATABASE=部分
            import re
            conn_str = re.sub(r'DATABASE=\w+', f'DATABASE={database}', conn_str, flags=re.IGNORECASE)

            return conn_str
        except Exception as e:
            logger.error("获取数据库配置失败", error=str(e))
            raise

    def _execute_query(self, sql: str, database: str) -> list:
        """执行SQL查询"""
        connection_string = self._get_connection_string(database)

        conn = pyodbc.connect(connection_string, timeout=30)
        cursor = conn.cursor()

        try:
            cursor.execute(sql)

            # 转换为字典列表
            columns = [column[0] for column in cursor.description]
            results = []
            for row in cursor.fetchall():
                record = dict(zip(columns, row))

                # 转换datetime为字符串
                for key, value in record.items():
                    if hasattr(value, 'strftime'):
                        record[key] = value.strftime('%Y-%m-%d %H:%M:%S')

                results.append(record)

            return results

        finally:
            cursor.close()
            conn.close()


class ExecuteSQLQueryTool(BaseSQLQueryTool):
    """问数/监测数据专用SQL查询工具。"""

    def __init__(self):
        schema_description = (
            "监测数据SQL Server查询工具。支持二选一：describe_table查看表结构，或sql执行SELECT查询。"
            "高频表优先使用下方已确认的字段契约直接生成SQL；其他表字段不确定时再用describe_table动态查询。"
            "硬约束：只允许SELECT；禁止DROP/DELETE/INSERT/UPDATE；最大返回1000条。"
            "SQL Server语法：中文字符串必须加N前缀，如 N'广东'；分页/限制用TOP，不支持LIMIT。"
            "database默认为XcAiDb；质控/站点基础信息通常用AirPollutionAnalysis。"
            "\n\n常用表说明（按数据库分类）："
            "\n【XcAiDb数据库-空气质量】"
            "\n- WeatherForecast7Day：7天空气质量预报（全国319城，含MinAqi/MaxAqi/MaxPollution/WeatherCondition/Temperature/WindLevel/WindDirection/TimePoint）"
            "\n- OpenMeteoAirQualityForecast72h：Open-Meteo未来72小时空气质量预报明细"
            "\n- CityDayAQIPublishHistory：城市日空气质量历史数据（次选，优先中大表）"
            "\n- CityAQIPublishHistory：城市小时空气质量历史数据（次选，优先中大表）"
            "\n- CurrentAirQuality：当前空气质量"
            "\n- dat_station_hour/dat_station_day：站点小时/日数据（次选，优先中大表）"
            "\n- dat_zhongda_station_minute/dat_zhongda_station_hour：中大平台站点5分钟/小时数据（含质量标记列，-99为无效值）"
            "\n- dat_zhongda_station_day：中大平台站点日均（审核后）"
            "\n- dat_zhongda_city_hour/dat_zhongda_city_day：中大平台城市小时/日均（可能为空，需空结果容错）"
            "\n- HenanCityAccumulateRanking：河南省城市月/年累计空气质量排名（period_type区分月/年累计）"
            "\n【统计预计算表】"
            "\n- city_168_statistics_new_standard/city_168_statistics_old_standard：168城市空气质量统计；"
            "适用于168城市全国排名、排名变化、全国发布统计数据查询"
            "\n- province_statistics_new_standard/province_statistics_old_standard：省级空气质量统计"
            "\n- noise_city_compliance_monthly/noise_city_compliance_daily：噪声达标率统计"
            "\n【AirPollutionAnalysis数据库-质控与站点】"
            "\n- qc_history：自动质控历史数据"
            "\n- quality_control_records：质控例行检查记录"
            "\n- BSD_STATION：站点信息表（含站点ID/名称/代码/区域/经纬度/地址）"
            "\n- analysis_history：分析历史记录"
            + AIR_QUALITY_SCHEMA_GUIDE
            + "\n\n提示：使用describe_table可查看白名单表的完整字段结构。运维表单请使用execute_ops_sql_query。"
        )
        super().__init__(
            tool_name="execute_sql_query",
            tool_description="Execute monitoring SQL queries on SQL Server database or get table structure",
            schema_description=schema_description,
            allowed_tables=MONITORING_SQL_TABLES,
            default_database="XcAiDb",
        )


class ExecuteOpsSQLQueryTool(BaseSQLQueryTool):
    """运维模式专用SQL查询工具。"""

    def __init__(self):
        schema_description = (
            "运维表单SQL Server查询工具。支持二选一：describe_table查看表结构，或sql执行SELECT查询。"
            "用于运维模式查询工单、站点设备、周检、双周、月检、季检、现场巡检等运维表单。"
            "不确定字段/表结构时先用describe_table动态查询，不要依赖记忆中的字段名。"
            "只能查询下方列出的运维白名单表单；禁止通过information_schema.tables、information_schema.columns等元数据表做表名发现式查询。"
            "如果不知道中文业务表单对应哪个白名单表名，不要猜表名或模糊搜索系统表，应说明映射不明确。"
            "硬约束：只允许SELECT；禁止DROP/DELETE/INSERT/UPDATE；最大返回1000条。"
            "SQL Server语法：中文字符串必须加N前缀，如 N'完成'；分页/限制用TOP，不支持LIMIT。"
            "database默认为AirPollutionAnalysis。"
            "\n\n常用表说明："
            "\n【系统管理】"
            "\n- sys_user：用户信息（CREATEUSERID, CURRENTUSERID, PREVUSERID, NEXTUSERID）"
            "\n- sys_department：部门信息（DEPARTMENTID, FIELDDEPARTMENTID）"
            "\n- wfl_workflow：工作流程定义（WORKFLOWID）"
            "\n- wfl_task：任务节点定义（STARTTASKID）"
            "\n【工单与站点设备】"
            "\n- working_orders/working_order_details：运维工单及详情"
            "\n- wo_commonfile_links：工单/运维表单通用附件关联"
            "\n- WO_COMMONFILE：工单通用文件表"
            "\n- BSD_STATION/base_station/base_station_sup：站点基础信息"
            "\n- base_device：设备基础信息"
            "\n- base_user_station/base_department_station/base_contract_station：用户/部门/合同-站点关联"
            "\n【周检表】"
            "\n- RF_W_GASEOUSCHECK_CO：周检-CO检查"
            "\n- RF_W_GASEOUSCHECK_NOX：周检-NOX检查"
            "\n- RF_W_GASEOUSCHECK_O3：周检-O3检查"
            "\n- RF_W_GASEOUSCHECK_SO2：周检-SO2检查"
            "\n- RF_W_GrainCalibrationCheck_PM10：周检-PM10颗粒物监测仪校准检查"
            "\n- RF_W_GrainCalibrationCheck_PM25：周检-PM2.5颗粒物监测仪校准检查"
            "\n- RF_W_GrainCalibrationCheckAttach：颗粒物监测仪校准检查附件"
            "\n- RF_W_INSPECTION：周检-站点巡检记录"
            "\n- RF_W_INSPECTIONSUMMARY：周检-巡检汇总"
            "\n- RF_W_LONGOPTICALPATH：周检-长光程分析仪器运行状况检查"
            "\n- RF_W_OTHERDEVICECHECK：周检-其他设备"
            "\n- RF_W_PMCHECK：周检-PM2.5自动监测分析仪运行状况检查"
            "\n- RF_W_STANDARD_ALL：周检-流量检查的仪器设备和标准流量"
            "\n【双周表】"
            "\n- RF_TW_CleanCuttingHead：双周-切割头清洗"
            "\n- RF_TW_PmFlowCalibrate：双周-PM流量校准"
            "\n- RF_TW_PmFlowCheck：双周-PM流量检查"
            "\n【月检表】"
            "\n- RF_M_GASEOUSCALICHECK：月检-气态校准检查"
            "\n- RF_M_GASEOUSCALIDEVICECHECK：月检-气态校准设备检查"
            "\n- RF_M_GASEOUSFLOWCHECK：月检-气态流量检查"
            "\n- RF_M_MANUALCOMPARISON：月检-手工比对"
            "\n- RF_M_MANUALCOMPARISONDETAIL：月检-手工比对明细"
            "\n- RF_M_MEMBRANEWEIGHING：月检-滤膜称重"
            "\n- RF_M_PMDEVICEMAINTAIN：月检-PM设备维护"
            "\n- RF_M_STATIONDEVICEMAINTAIN：月检-站点设备维护"
            "\n- RF_M_StationMaintainCheck：月检-站点维护检查"
            "\n【季检表】"
            "\n- RF_Q_GASEOUSMULTIPOINT_CO/NO2/O3/SO2：季检-气态多点校准"
            "\n- RF_Q_GASEOUSPRECISION_CO/NO2/O3/SO2：季检-气态精密度"
            "\n- RF_Q_GaseousFlowCheck：季检-气态流量检查"
            "\n- RF_Q_LONGOPTICALPATH_NO2/O3/SO2：长光路校准"
            "\n- RF_Q_PM10RUNSTATUSCHECK：PM10运行状态检查"
            "\n- RF_Q_PM25RUNSTATUSCHECK：PM2.5运行状态检查"
            "\n- RF_Q_PMPRESSURE：PM压力/流量"
            "\n- RF_Q_STATIONDEVICECLEAN：季检-站点设备清洁"
            "\n- RF_Q_StationMaintainCheck：季检-站点维护检查"
            "\n【年度/应急维护表】"
            "\n- RF_Y_DEVICECHANGE：年度-备机更换记录"
            "\n- RF_Y_DEVICEREPAIR：年度-空气自动监测仪器设备检修"
            "\n- RF_Y_PreventiveMaintenance：年度-预防性维护"
            "\n【现场表】"
            "\n- RF_SEC_INSPECTION：现场巡检"
            "\n- RF_SEC_INSTRUMENTRECORD：仪器记录"
            "\n- RF_SEC_MONITORINGCHECK：监测检查"
            "\n- RF_PM1MonitorInspection：PM1监测巡检"
            "\n- RF_BCMonitorInspection：BC监测巡检"
            "\n- SEC_CHECKSCORE：运维情况现场质控检查评分"
            "\n- SEC_CHECKSCORE_SX：运维情况现场质控检查评分(山西)"
            "\n- SEC_CHECKSCORE_SXNEW：运维情况现场质控检查评分(山西新版)"
            "\n【超站表单】"
            "\n- Sup_RF_MonthNepheloMeterCheck：超站-浊度计巡检维护记录"
            "\n- Sup_RF_NepheloMeterCalibration：超站-浊度计零点跨度检查校准"
            "\n【海盐运维表单】"
            "\n- RF_HY_EnvironmentHumidity：海盐-环境湿度校准"
            "\n- RF_HY_GASEOUSCALIDEVICECHECK：海盐-气体校准设备检查"
            "\n- RF_HY_NOXCONVERSIONRATE：海盐-NOx转化率"
            "\n- RF_HY_O3VALUEPASS：臭氧（O3）校准仪（工作标准）量值传递记录表（每季度）"
            "\n- RF_HY_STATIONDEVICEMAINTAIN：海盐-站点设备维护"
            "\n- RF_HY_StationMaintainCheck：海盐-站点维护检查"
            "\n- RF_HY_VISIBILITYCALI：海盐-能见度校准"
            "\n【质控校准管理表】"
            "\n- qa_appraisalcalibrationlog：评价校准操作日志"
            "\n- qa_appraisalcalibrationmanagem：评价校准管理"
            "\n- qa_calibrationpass：校准通过记录"
            "\n- qa_ozonecalibration：臭氧校准记录"
            "\n- qa_ozonetransfer：臭氧传递记录"
            "\n- qa_standardmateriallog：标准物质日志"
            "\n- qa_standardmaterialstorage：标准物质库存/存储"
            "\n\n提示：使用describe_table可查看白名单表的完整字段结构。空气质量监测统计请使用execute_sql_query。"
        )
        super().__init__(
            tool_name="execute_ops_sql_query",
            tool_description="Execute operations SQL queries on SQL Server database or get table structure",
            schema_description=schema_description,
            allowed_tables=OPS_SQL_TABLES,
            default_database="AirPollutionAnalysis",
            allow_information_schema_sql=False,
        )


class ExecuteTenderSQLQueryTool(BaseSQLQueryTool):
    """助手模式招投标数据专用SQL查询工具。"""

    def __init__(self):
        schema_description = (
            "招投标数据SQL Server查询工具。支持二选一：describe_table查看表结构，或sql执行SELECT查询。"
            "用于助手模式查询已抓取、初筛、详情清洗并入库的招标公告和中标公告。"
            "只能查询下方列出的招投标白名单表；禁止查询其他业务库表。"
            "硬约束：只允许SELECT；禁止DROP/DELETE/INSERT/UPDATE；最大返回1000条。"
            "SQL Server语法：中文字符串必须加N前缀，如 N'生态环境局'；分页/限制用TOP，不支持LIMIT。"
            "database默认为XcAiDb。"
            "\n\n常用表说明："
            "\n- tender_notices：清洗后的目标公告主表，也是回答“某天有多少条招投标公告/有哪些公告”的最终事实表。包含title、notice_type、project_name、purchaser、winning_bidder、budget_amount、winning_amount、province、city、publish_date、project_category、summary、key_requirements_json、extraction_meta_json等字段。"
            "\n- tender_notice_contents：公告原文内容表，按url关联tender_notices，包含raw_content等大文本字段。"
            "\n- tender_candidates：列表页候选公告表，用于判断初筛和补录闭环状态。accepted候选表示已通过初筛；accepted候选LEFT JOIN tender_notices后n.url IS NULL的数量，才表示仍缺详情/仍未入库。"
            "\n- tender_fetch_runs：抓取执行日志表，可能保留初次失败、补录中断、重试成功等多轮历史记录。它只用于排障，不是最终业务状态；不要累加saved_notices，不要仅因旧run存在detail_fetch_failures就判断补录未完成。"
            "\n\n判断口径："
            "\n- 最终入库数量：只统计tender_notices，按publish_date去重后的事实表结果为准。"
            "\n- 补录是否完成：统计accepted候选中尚未在tender_notices出现的数量；为0表示已通过详情页抓取/复核闭环，即使历史run仍有失败日志。"
            "\n- run状态解读：tender_fetch_runs.status=partial_failed/failed/interrupted只说明该执行批次有错误或被中断，不代表该日期最终未完成；需要结合最终入库和accepted_missing_notice判断。"
            "\n\n常见查询："
            "\n- 某日最终入库公告：SELECT TOP 50 title, notice_type, purchaser, publish_date FROM tender_notices WHERE publish_date = '2026-07-01' ORDER BY id DESC"
            "\n- 某日最终闭环统计：SELECT COUNT(*) AS accepted, SUM(CASE WHEN n.url IS NOT NULL THEN 1 ELSE 0 END) AS accepted_with_notice, SUM(CASE WHEN n.url IS NULL THEN 1 ELSE 0 END) AS accepted_missing_notice FROM tender_candidates c LEFT JOIN tender_notices n ON n.url = c.url WHERE c.publish_date = '2026-07-01' AND c.filter_status = 'accepted'"
            "\n- 某日候选初筛统计：SELECT filter_status, decision_source, COUNT(*) AS cnt FROM tender_candidates WHERE publish_date = '2026-07-01' GROUP BY filter_status, decision_source"
            "\n- 最近执行日志排障：SELECT TOP 10 id, target_date, status, total_candidates, detail_fetch_failures, saved_notices, started_at, finished_at FROM tender_fetch_runs ORDER BY started_at DESC"
            "\n\n提示：使用describe_table可查看白名单表的完整字段结构。"
        )
        super().__init__(
            tool_name="execute_tender_sql_query",
            tool_description="Execute tender information SQL queries on SQL Server database or get table structure",
            schema_description=schema_description,
            allowed_tables=TENDER_SQL_TABLES,
            default_database="XcAiDb",
            allow_information_schema_sql=False,
        )

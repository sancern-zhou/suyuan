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
    'dat_station_day',
    'dat_station_hour',
    'dat_weather_hour',
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


OPS_SQL_TABLES = [
    # 运维工单与站点设备基础信息
    'working_orders',
    'working_order_details',
    'wo_commonfile_links',
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
    'RF_W_OTHERDEVICECHECK',
    # 双周表
    'RF_TW_CleanCuttingHead',
    'RF_TW_PmFlowCalibrate',
    'RF_TW_PmFlowCheck',
    # 月检表
    'RF_M_GASEOUSCALICHECK',
    'RF_M_GASEOUSCALIDEVICECHECK',
    'RF_M_GASEOUSFLOWCHECK',
    'RF_M_MANUALCOMPARISON',
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
    'RF_Q_PM25RUNSTATUSCHECK',
    'RF_Q_PMPRESSURE',
    'RF_Q_STATIONDEVICECLEAN',
    'RF_Q_StationMaintainCheck',
    # 其他现场表
    'RF_SEC_INSPECTION',
    'RF_SEC_INSTRUMENTRECORD',
    'RF_SEC_MONITORINGCHECK',
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
    - 最大返回200条记录
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
        self.sql_validator = SQLValidator(max_limit=200, allowed_tables=allowed_tables)

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
                        "description": "返回记录数限制（默认50，最大200，仅用于sql查询）",
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
            data_id = None

            if context and len(results) > 24:
                try:
                    # 动态提取列名作为元数据
                    if results:
                        columns = list(results[0].keys())
                    else:
                        columns = []

                    # 保存完整数据
                    data_id = context.save_data(
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
                        data_id=data_id
                    )

                    return {
                        "success": True,
                        "data": sample_data,  # 只返回样本数据
                        "data_id": data_id,    # 完整数据ID
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
                    data_id = None

            # 未外部化，返回全部数据
            return {
                "success": True,
                "data": results,
                "data_id": data_id,
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
            "不确定字段/表结构时先用describe_table动态查询，不要依赖记忆中的表清单。"
            "硬约束：只允许SELECT；禁止DROP/DELETE/INSERT/UPDATE；最大返回200条。"
            "SQL Server语法：中文字符串必须加N前缀，如 N'广东'；分页/限制用TOP，不支持LIMIT。"
            "database默认为XcAiDb；质控/站点基础信息通常用AirPollutionAnalysis。"
            "\n\n常用表说明（按数据库分类）："
            "\n【XcAiDb数据库-空气质量】"
            "\n- WeatherForecast7Day：7天空气质量预报（全国319城，含MinAqi/MaxAqi/MaxPollution/WeatherCondition/Temperature/WindLevel/WindDirection/TimePoint）"
            "\n- CityDayAQIPublishHistory：城市日空气质量历史数据（24小时均值）"
            "\n- CityAQIPublishHistory：城市小时空气质量历史数据"
            "\n- CurrentAirQuality：当前空气质量"
            "\n- dat_station_hour/dat_station_day：站点小时/日数据"
            "\n【统计预计算表】"
            "\n- city_168_statistics_new_standard/city_168_statistics_old_standard：168城市空气质量统计"
            "\n- province_statistics_new_standard/province_statistics_old_standard：省级空气质量统计"
            "\n- noise_city_compliance_monthly/noise_city_compliance_daily：噪声达标率统计"
            "\n【AirPollutionAnalysis数据库-质控与站点】"
            "\n- qc_history：自动质控历史数据"
            "\n- quality_control_records：质控例行检查记录"
            "\n- BSD_STATION：站点信息表（含站点ID/名称/代码/区域/经纬度/地址）"
            "\n- analysis_history：分析历史记录"
            "\n\n提示：使用describe_table可查看白名单表的完整字段结构。运维表单请使用execute_ops_sql_query。"
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
            "硬约束：只允许SELECT；禁止DROP/DELETE/INSERT/UPDATE；最大返回200条。"
            "SQL Server语法：中文字符串必须加N前缀，如 N'完成'；分页/限制用TOP，不支持LIMIT。"
            "database默认为AirPollutionAnalysis。"
            "\n\n常用表说明："
            "\n【工单与站点设备】"
            "\n- working_orders/working_order_details：运维工单及详情"
            "\n- wo_commonfile_links：工单/运维表单通用附件关联"
            "\n- BSD_STATION/base_station/base_station_sup：站点基础信息"
            "\n- base_device：设备基础信息"
            "\n- base_user_station/base_department_station/base_contract_station：用户/部门/合同-站点关联"
            "\n【周检表】"
            "\n- RF_W_GASEOUSCHECK_CO：周检-CO检查"
            "\n- RF_W_GASEOUSCHECK_NOX：周检-NOX检查"
            "\n- RF_W_GASEOUSCHECK_O3：周检-O3检查"
            "\n- RF_W_GASEOUSCHECK_SO2：周检-SO2检查"
            "\n- RF_W_OTHERDEVICECHECK：周检-其他设备"
            "\n【双周表】"
            "\n- RF_TW_CleanCuttingHead：双周-切割头清洗"
            "\n- RF_TW_PmFlowCalibrate：双周-PM流量校准"
            "\n- RF_TW_PmFlowCheck：双周-PM流量检查"
            "\n【月检表】"
            "\n- RF_M_GASEOUSCALICHECK：月检-气态校准检查"
            "\n- RF_M_GASEOUSCALIDEVICECHECK：月检-气态校准设备检查"
            "\n- RF_M_GASEOUSFLOWCHECK：月检-气态流量检查"
            "\n- RF_M_MANUALCOMPARISON：月检-手工比对"
            "\n- RF_M_PMDEVICEMAINTAIN：月检-PM设备维护"
            "\n- RF_M_STATIONDEVICEMAINTAIN：月检-站点设备维护"
            "\n- RF_M_StationMaintainCheck：月检-站点维护检查"
            "\n【季检表】"
            "\n- RF_Q_GASEOUSMULTIPOINT_CO/NO2/O3/SO2：季检-气态多点校准"
            "\n- RF_Q_GASEOUSPRECISION_CO/NO2/O3/SO2：季检-气态精密度"
            "\n- RF_Q_GaseousFlowCheck：季检-气态流量检查"
            "\n- RF_Q_LONGOPTICALPATH_NO2/O3/SO2：长光路校准"
            "\n- RF_Q_PM25RUNSTATUSCHECK：PM2.5运行状态检查"
            "\n- RF_Q_PMPRESSURE：PM压力/流量"
            "\n- RF_Q_STATIONDEVICECLEAN：季检-站点设备清洁"
            "\n- RF_Q_StationMaintainCheck：季检-站点维护检查"
            "\n【现场表】"
            "\n- RF_SEC_INSPECTION：现场巡检"
            "\n- RF_SEC_INSTRUMENTRECORD：仪器记录"
            "\n- RF_SEC_MONITORINGCHECK：监测检查"
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

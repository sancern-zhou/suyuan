"""
通用SQL执行工具

支持Agent直接执行SQL查询语句访问SQL Server历史数据库。
复用SQLValidator进行安全验证。
"""

from typing import Dict, Any, Optional
import pyodbc
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.sql_validator import SQLValidator


logger = structlog.get_logger()


class ExecuteSQLQueryTool(LLMTool):
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
    - 最大返回100条记录
    """

    # 默认返回记录数限制
    DEFAULT_LIMIT = 50

    def __init__(self):
        """初始化工具"""

        # 初始化SQL验证器，扩展表名白名单
        self.sql_validator = SQLValidator(max_limit=100)
        # 注意：qc_history 和 working_orders 已在 SQLValidator 类的白名单中，无需重复添加
        # 添加业务表到白名单
        self.sql_validator.ALLOWED_TABLES.extend([
            'city_168_statistics_new_standard',  # 168城市空气质量统计预计算表（新标准限值）
            'city_168_statistics_old_standard',  # 168城市空气质量统计预计算表（旧标准限值）
            'province_statistics_new_standard',  # 省级空气质量统计预计算表（新标准限值）
            'province_statistics_old_standard',  # 省级空气质量统计预计算表（旧标准限值）
            'noise_city_compliance_monthly',  # 城市噪声昼夜达标率月汇总表
            'noise_city_compliance_daily',  # 城市噪声昼夜达标率逐日明细表
        ])

        function_schema = {
            "name": "execute_sql_query",
            "description": """
通用SQL执行工具，直接执行SQL查询语句访问SQL Server历史数据库。

**两种使用方式（二选一）**：
1. 查看表结构：execute_sql_query(describe_table='表名')
   - 动态从数据库获取表结构信息
   - 返回字段名、数据类型、长度、是否可空等信息

2. 执行SQL查询：execute_sql_query(sql='SQL语句')
   - 执行SELECT查询获取数据
   - 支持复杂查询、JOIN、聚合等操作

**describe_table 参数说明**：
- 输入目标表名（如 'qc_history', 'working_orders'）
- 工具会动态查询数据库获取该表的结构信息
- 不需要提供 sql 参数

**sql 参数说明**：
- 输入完整的SQL查询语句
- 不需要提供 describe_table 参数

**database 参数说明**（可选）：
- 指定查询的数据库名称
- 'XcAiDb'（默认）：空气质量发布历史数据
- 'AirPollutionAnalysis'：污染分析数据（包含qc_history、quality_control_records等质控表）

**⚠️ SQL Server语法规则**
- ❌ WHERE province_name = '广东' → 必须使用N前缀：N'广东'
- ❌ SELECT ... LIMIT 10 → SQL Server使用TOP而非LIMIT

**可用数据表**：
【XcAiDb数据库（默认）】
168城市统计（城市名不带'市'后缀，省份名不带'省'后缀）：
- city_168_statistics_new_standard：168城市空气质量统计（新标准 HJ 633-2026，限值：PM10=60, PM2.5=30。包含预计算的排名字段：comprehensive_index_rank、comprehensive_index_rank_new_limit_old_algo。数据周期2024-01至今）

  **stat_type字段说明**：ytd_to_month(年初到某月累计，如stat_date='2026-03'表示1-3月累计)、month_current(当月累计，如stat_date='2026-04'表示4月当月)、year_to_date(年初至今，如stat_date='2026'表示1月至今)、month_complete(完整月，如stat_date='2026-03'表示3月完整月)

- city_168_statistics_old_standard：168城市空气质量统计（旧标准 HJ 633-2013，限值：PM10=70, PM2.5=35。包含预计算的排名字段：comprehensive_index_rank_new_algo、comprehensive_index_rank_old_algo。使用final_output修约规则：PM2.5/CO保留1位，其他取整。stat_type字段说明同上）

省级统计（省份名不带'省'后缀）：
- province_statistics_new_standard：省级空气质量统计（新标准 HJ 633-2026，限值：PM10=60, PM2.5=30。包含预计算的排名字段：comprehensive_index_rank、comprehensive_index_rank_new_limit_old_algo。数据周期2024-01至今）

  **stat_type字段说明**：ytd_to_month(年初到某月累计，如stat_date='2026-03'表示1-3月累计)、month_current(当月累计，如stat_date='2026-04'表示4月当月)、year_to_date(年初至今，如stat_date='2026'表示1月至今)、month_complete(完整月，如stat_date='2026-03'表示3月完整月)

- province_statistics_old_standard：省级空气质量统计（旧标准 HJ 633-2013，限值：PM10=70, PM2.5=35。包含预计算的排名字段：comprehensive_index_rank_new_algo、comprehensive_index_rank_old_algo。使用final_output修约规则：PM2.5/CO保留1位，其他取整。stat_type字段说明同上）

噪声达标率数据：
- noise_city_compliance_monthly：城市噪声昼夜达标率月汇总表。包含 province、city_name、period_month、station_total、day_compliance_rate、night_compliance_rate、night_status、is_province_total 等字段；当前已导入安徽省2025年11月16地市及全省汇总数据。night_status 按夜间评价达标率是否达到100%分为“达标/未达标/无有效数据”。
- noise_city_compliance_daily：城市噪声昼夜达标率逐日明细表。包含 city_name、data_date、night_compliant_station_days、night_valid_station_days、night_compliance_rate、night_status 以及1类/2类/3类/4a类站点有效天数字段；可用于展示各城市每日夜间达标和未达标情况。

原始数据表：
- CityDayAQIPublishHistory：城市日空气质量发布历史（24小时均值）
- CityAQIPublishHistory：城市小时空气质量发布历史
- CurrentAirQuality：当前空气质量

【AirPollutionAnalysis数据库】
- qc_history：自动质控历史数据表（13551条记录，包含站点代码、任务组、任务名称、结果、目标值、响应值等，支持StationName字段查询）
- quality_control_records：质控例行检查记录
- working_orders：运维工单
- analysis_history：分析历史记录
- BSD_STATION：站点信息表（包含站点ID、名称、代码、区域ID、经纬度、地址、状态等，支持按区域查询站点列表）

**安全限制**：
- 只允许SELECT查询
- 禁止DROP/DELETE/INSERT/UPDATE等操作
- 表名白名单验证
- 最大返回100条记录

**使用流程**：
1. 先查看表结构：execute_sql_query(describe_table='qc_history', database='AirPollutionAnalysis')
2. 根据表结构和数据样例编写SQL（注意中文字符串使用 N 前缀）
3. 执行查询：execute_sql_query(sql='SELECT ...', database='AirPollutionAnalysis')
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "describe_table": {
                        "type": "string",
                        "description": "查看表结构（与sql参数二选一）。输入目标表名，如 'qc_history' 或 'working_orders'。工具会动态从数据库获取该表的结构信息，包括字段名、数据类型、长度、是否可空等。"
                    },
                    "sql": {
                        "type": "string",
                        "description": "SQL查询语句（与describe_table参数二选一）。输入完整的SQL SELECT查询语句。"
                    },
                    "database": {
                        "type": "string",
                        "description": "数据库名称（可选）。默认为'XcAiDb'，查询质控数据时使用'AirPollutionAnalysis'。",
                        "enum": ["XcAiDb", "AirPollutionAnalysis"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回记录数限制（默认50，最大100，仅用于sql查询）",
                        "default": 50
                    }
                }
            }
        }

        super().__init__(
            name="execute_sql_query",
            description="Execute SQL queries on SQL Server database or get table structure",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.2.0",
            requires_context=False
        )

    async def execute(self, describe_table: Optional[str] = None, sql: Optional[str] = None, database: Optional[str] = None, limit: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        """
        执行工具

        Args:
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
            database = "XcAiDb"

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
            return await self._execute_sql_query(sql, database, limit)

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
                all_tables = self._execute_query(all_tables_sql)

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
{sample_text}提示：使用 execute_sql_query(sql='SELECT TOP 100 * FROM {full_table_name}', database='{database}') 查看更多数据"""
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

    async def _execute_sql_query(self, sql: str, database: str, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        执行SQL查询

        Args:
            sql: SQL查询语句
            database: 数据库名称
            limit: 返回记录数限制

        Returns:
            查询结果
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
            limit=limit
        )

        try:
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
                    "summary": f"SQL验证失败: {error_msg}。请使用 execute_sql_query(describe_table='表名', database='{database}') 查看正确的表结构信息。"
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

            return {
                "success": True,
                "data": results,
                "summary": f"查询到{len(results)}条记录"
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
                hint = f" 请使用 execute_sql_query(describe_table='{table_name}', database='{database}') 查看正确的字段名。"

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
                "summary": f"查询失败: {str(e)}。请使用 execute_sql_query(describe_table='表名', database='{database}') 查看正确的表结构信息。"
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

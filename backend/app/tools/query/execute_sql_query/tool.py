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
    - 最大返回10000条记录
    """

    # 默认返回记录数限制
    DEFAULT_LIMIT = 1000

    def __init__(self):
        """初始化工具"""

        # 初始化SQL验证器，扩展表名白名单
        self.sql_validator = SQLValidator(max_limit=10000)
        # 添加业务表到白名单
        self.sql_validator.ALLOWED_TABLES.extend([
            'working_orders',
            'qc_history',  # 自动质控历史数据表
            # 系统视图（用于动态查询表结构）
            'information_schema.columns',
            'information_schema.tables',
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

**⚠️ 重要：中文查询注意事项**
SQL Server 查询中文字符串时，必须使用 N 前缀（表示 Unicode）：
- ❌ 错误：WHERE StationName LIKE '%增城派潭%'
- ✅ 正确：WHERE StationName LIKE N'%增城派潭%'
- ✅ 正确：WHERE StationCode = '1428A'（英文和数字不需要 N 前缀）
- 建议：优先使用 StationCode（站点编码）进行查询，避免中文编码问题

**可用数据表**：
- qc_history: 自动质控历史数据表（包含 StationCode、StationName 等字段）
- working_orders: 运维工单记录表

**安全限制**：
- 只允许SELECT查询
- 禁止DROP/DELETE/INSERT/UPDATE等操作
- 表名白名单验证
- 最大返回10000条记录

**使用流程**：
1. 先查看表结构：execute_sql_query(describe_table='qc_history')
2. 根据表结构编写SQL（注意中文字符串使用 N 前缀）
3. 执行查询：execute_sql_query(sql='SELECT ...')
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
                    "limit": {
                        "type": "integer",
                        "description": "返回记录数限制（默认1000，最大10000，仅用于sql查询）",
                        "default": 1000
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

    async def execute(self, describe_table: Optional[str] = None, sql: Optional[str] = None, limit: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        """
        执行工具

        Args:
            describe_table: 查看表结构（与sql二选一，不能为空）
            sql: SQL查询语句（与describe_table二选一）
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

        # 判断是查看表结构还是执行SQL
        if describe_table:
            return self._describe_table(describe_table)
        else:
            return await self._execute_sql_query(sql, limit)

    def _describe_table(self, table_name: str) -> Dict[str, Any]:
        """
        查看表结构（动态从数据库获取）

        Args:
            table_name: 表名

        Returns:
            表结构信息
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
            # 动态查询表结构
            sql = f"""
                SELECT
                    COLUMN_NAME,
                    DATA_TYPE,
                    CHARACTER_MAXIMUM_LENGTH,
                    IS_NULLABLE,
                    COLUMN_DEFAULT
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = '{table_name}'
                ORDER BY ORDINAL_POSITION
            """

            columns = self._execute_query(sql)

            if not columns:
                return {
                    "success": False,
                    "data": None,
                    "summary": f"未找到表 '{table_name}' 的结构信息"
                }

            # 格式化字段列表
            fields_text = "\n".join([
                f"  - {col['COLUMN_NAME']} ({col['DATA_TYPE']}{'(' + str(col['CHARACTER_MAXIMUM_LENGTH']) + ')' if col['CHARACTER_MAXIMUM_LENGTH'] else ''}, {'可空' if col['IS_NULLABLE'] == 'YES' else '非空'})"
                for col in columns
            ])

            result = {
                "success": True,
                "data": {
                    "table_name": table_name,
                    "columns": columns
                },
                "summary": f"""表名: {table_name}

字段列表:
{fields_text}

字段总数: {len(columns)}

提示：使用 execute_sql_query(sql='SELECT TOP 100 * FROM {table_name}') 查看数据示例"""
            }

            logger.info(
                "table_schema_described",
                table_name=table_name,
                field_count=len(columns)
            )

            return result

        except Exception as e:
            logger.error("describe_table_failed", table_name=table_name, error=str(e))
            return {
                "success": False,
                "data": None,
                "summary": f"查询表结构失败: {str(e)}"
            }

    async def _execute_sql_query(self, sql: str, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        执行SQL查询

        Args:
            sql: SQL查询语句
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
                    "summary": f"SQL验证失败: {error_msg}。请使用 execute_sql_query(describe_table='表名') 查看正确的表结构信息。"
                }

            # 2. 添加TOP子句（SQL Server使用TOP而非LIMIT）
            safe_sql = self._sanitize_limit_for_sqlserver(sql, limit)

            # 3. 执行查询
            results = self._execute_query(safe_sql)

            logger.info(
                "sql_query_success",
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
                hint = f" 请使用 execute_sql_query(describe_table='{table_name}') 查看正确的字段名。"

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
                "summary": f"查询失败: {str(e)}。请使用 execute_sql_query(describe_table='表名') 查看正确的表结构信息。"
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

    def _get_connection_string(self) -> str:
        """获取数据库连接字符串"""
        try:
            from config.settings import Settings
            settings = Settings()
            return settings.sqlserver_connection_string
        except Exception as e:
            logger.error("获取数据库配置失败", error=str(e))
            raise

    def _execute_query(self, sql: str) -> list:
        """执行SQL查询"""
        connection_string = self._get_connection_string()

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

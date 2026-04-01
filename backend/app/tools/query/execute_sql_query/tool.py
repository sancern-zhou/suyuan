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

    # 表结构定义（无需维护文档，集中在此管理）
    TABLE_SCHEMAS = {
        "quality_control_records": {
            "description": "质控例行检查记录表",
            "fields": [
                {"name": "id", "type": "int", "description": "记录ID"},
                {"name": "province", "type": "nvarchar", "description": "省份"},
                {"name": "city", "type": "nvarchar", "description": "城市"},
                {"name": "operation_unit", "type": "nvarchar", "description": "运维单位"},
                {"name": "station", "type": "nvarchar", "description": "站点名称"},
                {"name": "start_time", "type": "datetime", "description": "开始时间"},
                {"name": "end_time", "type": "datetime", "description": "结束时间"},
                {"name": "task_group", "type": "nvarchar", "description": "任务组"},
                {"name": "qc_item", "type": "nvarchar", "description": "质控项目（如：NO_零点检查、O3_跨度检查）"},
                {"name": "qc_result", "type": "nvarchar", "description": "质控结果（合格、超控制限、超警告限、钼转换效率偏低）"},
                {"name": "response_value", "type": "float", "description": "响应值"},
                {"name": "target_value", "type": "float", "description": "目标值"},
                {"name": "error_value", "type": "float", "description": "误差值"},
                {"name": "molybdenum_efficiency", "type": "float", "description": "钼转换效率（%）"},
                {"name": "warning_limit", "type": "float", "description": "警告限"},
                {"name": "control_limit", "type": "float", "description": "控制限"},
            ],
            "sample_queries": [
                "SELECT * FROM quality_control_records WHERE city = N'广州市'",
                "SELECT station, qc_result, COUNT(*) as cnt FROM quality_control_records GROUP BY station, qc_result",
                "SELECT * FROM quality_control_records WHERE molybdenum_efficiency < 95 ORDER BY molybdenum_efficiency"
            ]
        },
        "working_orders": {
            "description": "运维工单记录表",
            "fields": [
                {"name": "WORKINGORDERID", "type": "int", "description": "工单ID"},
                {"name": "STATIONID", "type": "nvarchar", "description": "站点ID"},
                {"name": "DEVICEID", "type": "nvarchar", "description": "设备ID"},
                {"name": "WORKINGORDERCODE", "type": "nvarchar", "description": "工单编号"},
                {"name": "CREATETIME", "type": "datetime", "description": "创建时间"},
                {"name": "UPDATETIME", "type": "datetime", "description": "更新时间"},
                {"name": "FINISHTIME", "type": "datetime", "description": "完成时间"},
                {"name": "DDORDERCREATETYPE", "type": "nvarchar", "description": "工单创建类型"},
                {"name": "DDWORKINGORDERTYPE", "type": "nvarchar", "description": "工单类型（SupCheck巡检/Check检查/Fault故障/QCBlackOut质控）"},
                {"name": "DDURGENCYTYPE", "type": "nvarchar", "description": "紧急程度（Urgent紧急/Middle中等/Normal普通）"},
                {"name": "DDWORKINGORDERSTATUS", "type": "nvarchar", "description": "工单状态（Finish完成/Doing进行中/Wait待办/ToAssign待分配）"},
                {"name": "ORDERTITLE", "type": "nvarchar", "description": "工单标题"},
                {"name": "ORDERCONTENT", "type": "nvarchar", "description": "工单内容"},
                {"name": "CURRENTWORKFLOWSTATUS", "type": "nvarchar", "description": "当前工作流状态"},
                {"name": "CURRENTWORKFLOWPOINT", "type": "nvarchar", "description": "当前工作流节点"},
                {"name": "MAINTENANCETYPE", "type": "nvarchar", "description": "维护周期（Day/Week/Month/Quarter/HalfYear）"},
                {"name": "PLANFINISHTIME", "type": "datetime", "description": "计划完成时间"},
                {"name": "TOTALOVERTIME", "type": "int", "description": "总超时时间（分钟）"},
                {"name": "TOTALEXPENSE", "type": "decimal", "description": "总费用"},
            ],
            "sample_queries": [
                "SELECT * FROM working_orders WHERE DDWORKINGORDERSTATUS = N'Doing'",
                "SELECT DDWORKINGORDERTYPE, COUNT(*) as cnt FROM working_orders GROUP BY DDWORKINGORDERTYPE",
                "SELECT * FROM working_orders WHERE DDURGENCYTYPE = N'Urgent' ORDER BY CREATETIME DESC"
            ]
        }
    }

    def __init__(self):
        """初始化工具"""

        # 初始化SQL验证器，扩展表名白名单
        self.sql_validator = SQLValidator(max_limit=10000)
        # 添加业务表到白名单
        self.sql_validator.ALLOWED_TABLES.extend([
            'quality_control_records',
            'working_orders'
        ])

        function_schema = {
            "name": "execute_sql_query",
            "description": """
通用SQL执行工具，直接执行SQL查询语句访问SQL Server历史数据库。

**【重要】使用前请先查看表结构**：
在执行SQL查询前，请先使用 describe_table 参数查看表结构，了解字段名称和数据类型。

**当前可用数据表**：
- quality_control_records: 质控例行检查记录
- working_orders: 运维工单记录

**两种使用方式**：
1. 查看表结构：execute_sql_query(describe_table='表名') 或 describe_table='all'
2. 执行SQL查询：execute_sql_query(sql='SQL语句')

**describe_table 参数说明**：
- describe_table='all' 或 describe_table=True：返回所有可用表的列表
- describe_table='quality_control_records'：返回该表的详细结构（字段列表、类型、示例查询）
- describe_table='working_orders'：返回该表的详细结构
- 当表数量很多时，建议先使用 describe_table='all' 查看所有表，再选择具体表查看详细结构

**安全限制**：
- 只允许SELECT查询
- 禁止DROP/DELETE/INSERT/UPDATE等操作
- 表名白名单验证
- 最大返回10000条记录

**使用流程**：
1. 先查看表结构：execute_sql_query(describe_table='quality_control_records')
2. 根据表结构编写SQL
3. 执行查询：execute_sql_query(sql='SELECT ...')

**返回格式**：
- 查看表列表：返回所有可用表的名称和描述
- 查看表结构：返回表的字段列表、类型、说明和示例查询
- 执行查询：返回查询结果数据
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "describe_table": {
                        "type": "string",
                        "description": "查看表结构。可选值：'all'（返回所有可用表列表）、'quality_control_records'（质控记录表结构）、'working_orders'（运维工单表结构）。查看表结构时使用此参数，不需要提供sql参数。"
                    },
                    "sql": {
                        "type": "string",
                        "description": "SQL查询语句。执行查询时使用此参数，不需要提供describe_table参数。"
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
            version="2.1.0",
            requires_context=False
        )

    async def execute(self, describe_table: Optional[str] = None, sql: Optional[str] = None, limit: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        """
        执行工具

        Args:
            describe_table: 查看表结构（'all'或具体表名）
            sql: SQL查询语句
            limit: 返回记录数限制

        Returns:
            查询结果或表结构信息
        """

        # 判断是查看表结构还是执行SQL
        if describe_table:
            return self._describe_table(describe_table)
        elif sql:
            return await self._execute_sql_query(sql, limit)
        else:
            return {
                "success": False,
                "data": None,
                "summary": "请提供 describe_table（查看表结构）或 sql（执行查询）参数"
            }

    def _describe_table(self, table_name: str) -> Dict[str, Any]:
        """
        查看表结构

        Args:
            table_name: 表名或'all'

        Returns:
            表结构信息或所有表列表
        """
        # 处理 'all' 或 'true' 情况，返回所有表列表
        if table_name.lower() in ['all', 'true', '1']:
            tables_list = []
            for name, schema in self.TABLE_SCHEMAS.items():
                tables_list.append({
                    "table_name": name,
                    "description": schema['description'],
                    "field_count": len(schema['fields'])
                })

            # 格式化表列表
            tables_text = "\n".join([
                f"  {i+1}. {t['table_name']}: {t['description']} ({t['field_count']}个字段)"
                for i, t in enumerate(tables_list)
            ])

            result = {
                "success": True,
                "data": {
                    "tables": tables_list,
                    "total_count": len(tables_list)
                },
                "summary": f"""可用数据表列表（共{len(tables_list)}个）：
{tables_text}

查看具体表结构：execute_sql_query(describe_table='表名')"""
            }

            logger.info(
                "all_tables_listed",
                table_count=len(tables_list)
            )

            return result

        # 处理具体表名情况
        if table_name not in self.TABLE_SCHEMAS:
            available_tables = ", ".join(self.TABLE_SCHEMAS.keys())
            return {
                "success": False,
                "data": None,
                "summary": f"表 '{table_name}' 不存在。可用表: {available_tables}。提示：使用 describe_table='all' 查看所有可用表。"
            }

        schema = self.TABLE_SCHEMAS[table_name]

        # 格式化字段列表
        fields_text = "\n".join([
            f"  - {f['name']} ({f['type']}): {f['description']}"
            for f in schema['fields']
        ])

        # 格式化示例查询
        sample_queries_text = "\n".join([
            f"  {i+1}. {q}"
            for i, q in enumerate(schema['sample_queries'])
        ])

        result = {
            "success": True,
            "data": {
                "table_name": table_name,
                "description": schema['description'],
                "fields": schema['fields']
            },
            "summary": f"""表名: {table_name}
描述: {schema['description']}

字段列表:
{fields_text}

示例查询:
{sample_queries_text}"""
        }

        logger.info(
            "table_schema_described",
            table_name=table_name,
            field_count=len(schema['fields'])
        )

        return result

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

            # 2. 添加LIMIT
            safe_sql = self.sql_validator.sanitize_limit(sql, limit)

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
            if table_name and table_name in self.TABLE_SCHEMAS:
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

    def _extract_table_name(self, sql: str) -> Optional[str]:
        """从SQL中提取表名"""
        import re
        sql_lower = sql.lower()

        # 尝试提取FROM后的表名
        from_match = re.search(r'\bfrom\s+(\w+)', sql_lower)
        if from_match:
            table = from_match.group(1)
            if table in self.TABLE_SCHEMAS:
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

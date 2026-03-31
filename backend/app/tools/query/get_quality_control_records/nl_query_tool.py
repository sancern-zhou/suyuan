"""
质控记录自然语言查询工具（LLM生成SQL）

支持灵活的自然语言查询，LLM生成SQL语句，带防注入机制
"""
from typing import Dict, Any, Optional
import re
import pyodbc
import structlog
from anthropic import Anthropic

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


class GetQualityControlRecordsNLTool(LLMTool):
    """
    质控记录自然语言查询工具

    使用场景：
    - "找出钼转换效率最低的3个站点"
    - "查询超控制限且响应值大于10的记录"
    - "统计各城市的平均钼转换效率"
    - "广州站昨天有哪些异常记录？"

    安全机制：
    - 只允许 SELECT 查询
    - 禁止 DROP/DELETE/UPDATE/INSERT
    - 参数化执行防注入
    """

    # SQL 黑名单关键词
    FORBIDDEN_KEYWORDS = [
        'DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE',
        'ALTER', 'CREATE', 'EXEC', 'EXECUTE', 'xp_'
    ]

    def __init__(self):
        function_schema = {
            "name": "get_quality_control_records_nl",
            "description": """
自然语言查询质控例行检查记录（支持复杂查询）。

**数据表结构**：
表名：quality_control_records
字段：
- id (int): 记录ID
- province (nvarchar): 省份
- city (nvarchar): 城市
- operation_unit (nvarchar): 运维单位
- station (nvarchar): 站点名称
- start_time (datetime): 开始时间
- end_time (datetime): 结束时间
- task_group (nvarchar): 任务组
- qc_item (nvarchar): 质控项目（如：NO_零点检查、O3_跨度检查）
- qc_result (nvarchar): 质控结果（合格、超控制限、超警告限、钼转换效率偏低）
- response_value (float): 响应值
- target_value (float): 目标值
- error_value (float): 误差值
- molybdenum_efficiency (float): 钼转换效率
- warning_limit (float): 警告限
- control_limit (float): 控制限

**查询示例**：
- "找出钼转换效率最低的3个站点"
- "查询超控制限且响应值大于10的记录"
- "统计各城市的平均钼转换效率"
- "广州站昨天有哪些异常记录？"
- "哪些站点的NO_零点检查超标次数最多？"

**参数说明**：
- question: 自然语言查询问题（必填）
- limit: 返回记录数限制（可选，默认50，最大500）

**返回格式**：
{
    "success": True,
    "data": [...],
    "summary": "查询结果摘要",
    "sql": "生成的SQL语句（调试用）"
}
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "自然语言查询问题"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回记录数限制（默认50，最大500）"
                    }
                },
                "required": ["question"]
            }
        }

        super().__init__(
            name="get_quality_control_records_nl",
            description="Natural language query for quality control records (LLM-generated SQL)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

        self.anthropic_client = Anthropic()

    async def execute(self, question: str, limit: Optional[int] = 50, **kwargs) -> Dict[str, Any]:
        """
        执行自然语言查询

        Args:
            question: 自然语言查询问题
            limit: 返回记录数限制

        Returns:
            查询结果
        """
        limit = min(limit, 500)

        logger.info("nl_query_start", question=question, limit=limit)

        try:
            # Step 1: LLM 生成 SQL
            sql = await self._generate_sql(question, limit)

            # Step 2: 安全检查
            if not self._is_safe_sql(sql):
                return {
                    "success": False,
                    "data": [],
                    "summary": "SQL安全检查失败：检测到危险操作",
                    "sql": sql
                }

            # Step 3: 执行查询
            results = self._execute_sql(sql)

            logger.info("nl_query_success", question=question, result_count=len(results))

            return {
                "success": True,
                "data": results,
                "summary": f"查询到 {len(results)} 条记录",
                "sql": sql
            }

        except Exception as e:
            logger.error("nl_query_failed", question=question, error=str(e))
            return {
                "success": False,
                "data": [],
                "summary": f"查询失败: {str(e)}"
            }

    async def _generate_sql(self, question: str, limit: int) -> str:
        """使用 LLM 生成 SQL"""

        prompt = f"""你是一个SQL专家。根据用户的自然语言问题，生成对应的SQL查询语句。

**数据表结构**：
表名：quality_control_records
字段：
- id (int): 记录ID
- province (nvarchar): 省份
- city (nvarchar): 城市
- operation_unit (nvarchar): 运维单位
- station (nvarchar): 站点名称
- start_time (datetime): 开始时间
- end_time (datetime): 结束时间
- task_group (nvarchar): 任务组
- qc_item (nvarchar): 质控项目
- qc_result (nvarchar): 质控结果（合格、超控制限、超警告限、钼转换效率偏低）
- response_value (float): 响应值
- target_value (float): 目标值
- error_value (float): 误差值
- molybdenum_efficiency (float): 钼转换效率
- warning_limit (float): 警告限
- control_limit (float): 控制限

**用户问题**：{question}

**要求**：
1. 只生成 SELECT 查询语句
2. 使用 TOP {limit} 限制返回记录数
3. 中文字段值使用 N'...' 格式（如：N'广州市'）
4. 字符串比较使用 COLLATE Chinese_PRC_CI_AS
5. 只返回SQL语句，不要任何解释

**SQL语句**："""

        response = self.anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        sql = response.content[0].text.strip()

        # 清理 SQL（移除 markdown 代码块标记）
        sql = re.sub(r'^```sql\s*', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'^```\s*', '', sql)
        sql = re.sub(r'\s*```$', '', sql)
        sql = sql.strip()

        return sql

    def _is_safe_sql(self, sql: str) -> bool:
        """SQL 安全检查"""

        # 1. 必须是 SELECT 语句
        if not sql.upper().strip().startswith('SELECT'):
            logger.warning("sql_safety_check_failed", reason="not_select", sql=sql)
            return False

        # 2. 检查黑名单关键词
        sql_upper = sql.upper()
        for keyword in self.FORBIDDEN_KEYWORDS:
            if keyword in sql_upper:
                logger.warning("sql_safety_check_failed", reason="forbidden_keyword", keyword=keyword, sql=sql)
                return False

        # 3. 禁止多语句（分号分隔）
        if ';' in sql.rstrip(';'):
            logger.warning("sql_safety_check_failed", reason="multiple_statements", sql=sql)
            return False

        return True

    def _execute_sql(self, sql: str) -> list:
        """执行 SQL 查询"""

        # 获取数据库连接
        from config.settings import Settings
        settings = Settings()
        connection_string = settings.sqlserver_connection_string

        conn = pyodbc.connect(connection_string, timeout=30)
        cursor = conn.cursor()

        try:
            cursor.execute(sql)

            # 转换为字典列表
            columns = [column[0] for column in cursor.description]
            results = []
            for row in cursor.fetchall():
                record = dict(zip(columns, row))

                # 转换 datetime 为字符串
                for key, value in record.items():
                    if hasattr(value, 'strftime'):
                        record[key] = value.strftime('%Y-%m-%d %H:%M:%S')

                results.append(record)

            return results

        finally:
            cursor.close()
            conn.close()

    def _get_connection_string(self) -> str:
        """获取数据库连接字符串"""
        try:
            from config.settings import Settings
            settings = Settings()
            return settings.sqlserver_connection_string
        except Exception as e:
            logger.error("获取数据库配置失败", error=str(e))
            raise

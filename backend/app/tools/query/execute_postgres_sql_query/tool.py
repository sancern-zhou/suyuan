"""Read-only PostgreSQL/KingbaseES SQL queries for permit-license data."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import re
from typing import Any, Optional, TYPE_CHECKING

import structlog
from sqlalchemy import text

from app.db.database import engine
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.sql_validator import SQLValidator

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext


logger = structlog.get_logger()


PERMIT_SQL_TABLES = [
    "permit_licenses",
    "permit_license_versions",
    "permit_pollution_details",
    "permit_documents",
]

MAX_LIMIT = 1000
DEFAULT_LIMIT = 50


class ExecutePostgresSQLQueryTool(LLMTool):
    """Execute read-only SQL against the configured PostgreSQL/KingbaseES database."""

    def __init__(self) -> None:
        schema_description = (
            "PostgreSQL/KingbaseES 只读 SQL 查询工具。首期仅查询许昌市企业排污许可证数据；"
            "支持 describe_table 查看表结构，或 sql 执行 SELECT/CTE 查询，二者必须二选一。"
            "仅允许 permit_licenses、permit_license_versions、permit_pollution_details、"
            "permit_documents 四张业务表；禁止采集运行日志和失败记录。"
            "只允许 SELECT，禁止 INSERT/UPDATE/DELETE/DDL、注释和多语句；"
            f"使用 PostgreSQL LIMIT 分页，最大返回 {MAX_LIMIT} 条。"
            "不确定字段时先调用 describe_table，不要查询 information_schema。"
            "\n\n表说明："
            "\n- permit_licenses：许可证主表，含企业名称、许可证编号、统一社会信用代码、"
            "地址、行业、有效期、管理类别、当前状态和详情页链接。"
            "\n- permit_license_versions：许可证历史/业务版本，以 license_id 关联主表。"
            "\n- permit_pollution_details：大气/水污染物、排放方式和执行标准，以 license_id 关联主表。"
            "\n- permit_documents：已下载的许可证正副本及分页文件，以 license_id 关联主表。"
            "\n\n示例："
            "\n- 企业查询：SELECT enterprise_name, permit_number, current_status FROM permit_licenses "
            "WHERE enterprise_name ILIKE '%水泥%' ORDER BY updated_at DESC LIMIT 50"
            "\n- 大气污染物：SELECT l.enterprise_name, p.air_pollutant_types, p.air_emission_standard "
            "FROM permit_licenses l JOIN permit_pollution_details p ON p.license_id = l.id "
            "WHERE l.city_name = '许昌市' LIMIT 50"
        )
        function_schema = {
            "name": "execute_postgres_sql_query",
            "description": schema_description,
            "parameters": {
                "type": "object",
                "properties": {
                    "describe_table": {
                        "type": "string",
                        "enum": PERMIT_SQL_TABLES,
                        "description": "查看白名单业务表的字段及一条样例；与 sql 二选一。",
                    },
                    "sql": {
                        "type": "string",
                        "description": "仅允许使用白名单表的 PostgreSQL/KingbaseES SELECT 或 WITH...SELECT 查询；与 describe_table 二选一。",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_LIMIT,
                        "default": DEFAULT_LIMIT,
                        "description": "未在 SQL 中指定 LIMIT 时使用的返回上限；最大 1000。",
                    },
                },
            },
        }
        super().__init__(
            name="execute_postgres_sql_query",
            description="Execute read-only PostgreSQL/KingbaseES permit-license SQL queries",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )
        self.sql_validator = SQLValidator(
            max_limit=MAX_LIMIT,
            allowed_tables=PERMIT_SQL_TABLES,
        )

    async def execute(
        self,
        context: Optional["ExecutionContext"] = None,
        describe_table: Optional[str] = None,
        sql: Optional[str] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kwargs
        if bool(describe_table) == bool(sql):
            return {
                "success": False,
                "data": None,
                "summary": "请且只能提供 describe_table 或 sql 其中一个参数。",
            }
        if describe_table is not None:
            return await self._describe_table(describe_table)
        return await self._execute_sql(sql or "", limit, context)

    async def _describe_table(self, table_name: str) -> dict[str, Any]:
        if table_name not in PERMIT_SQL_TABLES:
            return {
                "success": False,
                "data": None,
                "summary": f"表 '{table_name}' 不在许可证业务表白名单中。可用表: {', '.join(PERMIT_SQL_TABLES)}",
            }

        try:
            columns = await self._run_query(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = :table_name
                ORDER BY ordinal_position
                """,
                {"table_name": table_name},
            )
            sample_rows = await self._run_query(f"SELECT * FROM {table_name} LIMIT 1")
        except Exception as exc:
            logger.error("postgres_sql_describe_failed", table_name=table_name, error=str(exc))
            return {"success": False, "data": None, "summary": f"查询表结构失败: {exc}"}

        if not columns:
            return {
                "success": False,
                "data": None,
                "summary": f"当前数据库中未找到白名单表 '{table_name}'。",
            }
        return {
            "success": True,
            "data": {
                "table_name": table_name,
                "columns": columns,
                "sample_data": sample_rows[0] if sample_rows else None,
            },
            "summary": f"表 {table_name} 共 {len(columns)} 个字段；已返回字段结构和一条样例。",
        }

    async def _execute_sql(
        self,
        sql: str,
        limit: Optional[int],
        context: Optional["ExecutionContext"],
    ) -> dict[str, Any]:
        normalized_sql = self.sql_validator.normalize_sql(sql)
        valid, error = self.sql_validator.validate(normalized_sql)
        if not valid:
            return {
                "success": False,
                "data": [],
                "summary": f"SQL 验证失败: {error}。字段不确定时请先调用 describe_table。",
            }

        effective_limit = self._resolve_limit(limit)
        safe_sql, limit_error = self._sanitize_limit(normalized_sql, effective_limit)
        if limit_error:
            return {"success": False, "data": [], "summary": limit_error}

        logger.info(
            "postgres_sql_query_start",
            sql_preview=normalized_sql[:200],
            limit=effective_limit,
            session_id=getattr(context, "session_id", "unknown") if context else "unknown",
        )
        try:
            rows = await self._run_query(safe_sql)
        except Exception as exc:
            logger.error("postgres_sql_query_failed", error=str(exc), sql_preview=normalized_sql[:200])
            return {
                "success": False,
                "data": [],
                "summary": f"查询失败: {exc}。字段不确定时请先调用 describe_table。",
            }

        return self._format_result(rows, normalized_sql, effective_limit, context)

    @staticmethod
    def _resolve_limit(limit: Optional[int]) -> int:
        if limit is None:
            return DEFAULT_LIMIT
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            return DEFAULT_LIMIT
        return min(limit, MAX_LIMIT)

    @staticmethod
    def _sanitize_limit(sql: str, default_limit: int) -> tuple[str, Optional[str]]:
        if re.search(r"\b(fetch|offset)\b", sql, re.IGNORECASE):
            return "", "请仅使用 LIMIT 分页，不支持 FETCH 或 OFFSET。"
        if not re.search(r"\blimit\b", sql, re.IGNORECASE):
            return f"{sql.rstrip(' ;')} LIMIT {default_limit}", None

        limit_match = re.search(r"\blimit\s+(\d+)\b", sql, re.IGNORECASE)
        if not limit_match:
            return "", "LIMIT 必须是 1 到 1000 的整数。"
        limit_value = int(limit_match.group(1))
        if limit_value < 1:
            return "", "LIMIT 必须大于 0。"
        if limit_value <= MAX_LIMIT:
            return sql, None
        return (
            re.sub(r"\blimit\s+\d+\b", f"LIMIT {MAX_LIMIT}", sql, count=1, flags=re.IGNORECASE),
            None,
        )

    async def _run_query(
        self,
        sql: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        async with engine.connect() as connection:
            result = await connection.execute(text(sql), parameters or {})
            return [self._serialize_row(dict(row)) for row in result.mappings()]

    def _format_result(
        self,
        rows: list[dict[str, Any]],
        sql: str,
        limit: int,
        context: Optional["ExecutionContext"],
    ) -> dict[str, Any]:
        columns = list(rows[0]) if rows else []
        if context and len(rows) > 24:
            try:
                data_id = context.save_data(
                    data=rows,
                    schema="permit_sql_query_result",
                    metadata={
                        "database": "postgresql_or_kingbase",
                        "sql": sql,
                        "row_count": len(rows),
                        "columns": columns,
                        "limit": limit,
                    },
                )
                sample = rows[:12] + rows[-12:]
                return {
                    "success": True,
                    "data": sample,
                    "data_id": data_id,
                    "count": len(rows),
                    "sample_count": len(sample),
                    "summary": f"查询到 {len(rows)} 条许可证记录，完整结果已保存，当前返回 24 条样例。",
                    "metadata": {"columns": columns, "externalized": True},
                }
            except Exception as exc:
                logger.warning("postgres_sql_externalize_failed", error=str(exc))

        return {
            "success": True,
            "data": rows,
            "count": len(rows),
            "summary": f"查询到 {len(rows)} 条记录。",
            "metadata": {"columns": columns, "externalized": False},
        }

    @staticmethod
    def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
        return {key: ExecutePostgresSQLQueryTool._serialize_value(value) for key, value in row.items()}

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, bytes):
            return value.hex()
        return value

"""Read-only MySQL queries against the DataCrawler long-history monitoring database."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import re
from typing import Any, Optional, TYPE_CHECKING

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.sql_validator import SQLValidator

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext


logger = structlog.get_logger()


# DataCrawler（MySQL 8，采集库）长历史表：站点/城市逐小时、逐日与年度均值。
CRAWLER_SQL_TABLES = [
    "StationHour",
    "CityHour",
    "StationDay",
    "CityDay",
    "CityYearPm25Avg",
    "Station",
]

MAX_LIMIT = 1000
DEFAULT_LIMIT = 50

_engine = None


def _get_engine():
    """Lazily create the shared async engine for the crawler MySQL database."""
    global _engine
    if _engine is None:
        from config.settings import settings

        # aiomysql 方言与 pool_pre_ping 不兼容（ping 缺 reconnect 参数），
        # 用较短的 pool_recycle 保证连接新鲜度。
        _engine = create_async_engine(
            settings.crawler_mysql_url,
            echo=False,
            pool_recycle=240,
            pool_timeout=30,
        )
    return _engine


class ExecuteCrawlerSQLQueryTool(LLMTool):
    """Execute read-only SQL against the DataCrawler MySQL long-history database."""

    def __init__(self) -> None:
        from app.tools.query.execute_crawler_sql_query.table_contracts import (
            render_table_contracts,
        )

        contracts_block = render_table_contracts()
        if not contracts_block:
            contracts_block = (
                "\n\n表字段契约缺失：写 SQL 前必须先用 describe_table 确认字段名与大小写。"
            )
        schema_description = (
            "大气监测采集库（MySQL）只读 SQL 查询工具，提供中台接口未覆盖的长历史数据："
            "站点/城市逐小时与逐日历史、PM2.5 年均值、站点目录。"
            "支持 describe_table 查看表结构，或 sql 执行 SELECT/CTE 查询，二者必须二选一。"
            f"仅允许白名单表：{', '.join(CRAWLER_SQL_TABLES)}；禁止采集运行日志和失败记录表。"
            "只允许 SELECT，禁止 INSERT/UPDATE/DELETE/DDL、注释和多语句；"
            f"使用 LIMIT 分页，最大返回 {MAX_LIMIT} 条。"
            "不确定字段时先调用 describe_table，不要查询 information_schema。"
            f"{contracts_block}"
            "\n注意：以上表都在同一个 MySQL 采集库，可跨表 JOIN；"
            "与 SQL Server 历史库、PostgreSQL 主库不支持跨库 JOIN。"
            "\n\n示例："
            "\n- 站点小时历史：SELECT TimePoint, StationName, Pm25Value, So2Value "
            "FROM StationHour WHERE StationName LIKE '%许昌%' AND TimePoint >= '2016-01-01' "
            "ORDER BY TimePoint LIMIT 100"
            "\n- 城市日历史：SELECT Date, Area, AQI, PM2_5, O3_8h FROM CityDay "
            "WHERE Area LIKE '%许昌%' AND Date >= '2020-01-01' ORDER BY Date LIMIT 100"
            "\n- PM2.5 年均值：SELECT Year, ActualPm25Avg, StandardPm25Avg FROM CityYearPm25Avg "
            "WHERE CityName LIKE '%许昌%' ORDER BY Year"
        )
        function_schema = {
            "name": "execute_crawler_sql_query",
            "description": schema_description,
            "parameters": {
                "type": "object",
                "properties": {
                    "describe_table": {
                        "type": "string",
                        "enum": CRAWLER_SQL_TABLES,
                        "description": "查看白名单业务表的字段及一条样例；与 sql 二选一。",
                    },
                    "sql": {
                        "type": "string",
                        "description": "仅允许使用白名单表的 MySQL SELECT 或 WITH...SELECT 查询；与 describe_table 二选一。",
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
            name="execute_crawler_sql_query",
            description="Execute read-only MySQL queries against the DataCrawler long-history monitoring database",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )
        self.sql_validator = SQLValidator(
            max_limit=MAX_LIMIT,
            allowed_tables=CRAWLER_SQL_TABLES,
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
        if table_name not in CRAWLER_SQL_TABLES:
            return {
                "success": False,
                "data": None,
                "summary": f"表 '{table_name}' 不在白名单中。可用表: {', '.join(CRAWLER_SQL_TABLES)}",
            }

        try:
            columns = await self._run_query(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = DATABASE() AND table_name = :table_name
                ORDER BY ordinal_position
                """,
                {"table_name": table_name},
                tables=[table_name],
            )
            sample_rows = await self._run_query(
                f"SELECT * FROM {table_name} LIMIT 1", tables=[table_name]
            )
        except Exception as exc:
            logger.error("crawler_sql_describe_failed", table_name=table_name, error=str(exc))
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

        referenced_tables = self.sql_validator.extract_tables(normalized_sql)

        logger.info(
            "crawler_sql_query_start",
            sql_preview=normalized_sql[:200],
            limit=effective_limit,
            session_id=getattr(context, "session_id", "unknown") if context else "unknown",
        )
        try:
            rows = await self._run_query(safe_sql, tables=referenced_tables)
        except Exception as exc:
            logger.error("crawler_sql_query_failed", error=str(exc), sql_preview=normalized_sql[:200])
            summary = f"查询失败: {exc}。"
            if self._is_column_error(exc):
                hint = self._columns_hint(referenced_tables)
                if hint:
                    summary += (
                        "\n涉及表的真实字段（大小写以此为准，直接据此修正 SQL 重试，"
                        "无需再调用 describe_table）：\n" + hint
                    )
                else:
                    summary += "字段不确定时请先调用 describe_table。"
            else:
                summary += "字段不确定时请先调用 describe_table。"
            return {
                "success": False,
                "data": [],
                "summary": summary,
            }

        return self._format_result(rows, normalized_sql, effective_limit, context)

    @staticmethod
    def _is_column_error(exc: Exception) -> bool:
        """MySQL 1054 Unknown column / 1054 类错误识别。"""
        original = getattr(exc, "orig", None)
        if original is not None and getattr(original, "args", None):
            if str(original.args[0]) == "1054":
                return True
        text = str(exc)
        return "1054" in text or "Unknown column" in text

    def _columns_hint(self, tables: Optional[list]) -> str:
        """渲染涉及表的真实字段清单（优先取契约文件，逐表限量防刷屏）。"""
        from app.tools.query.execute_crawler_sql_query.table_contracts import table_columns

        lines: list[str] = []
        for table in (tables or [])[:4]:
            columns = table_columns(str(table))
            display_name = str(table)
            if not columns:
                # sql_validator.extract_tables 会把表名转小写，这里按大小写不敏感回查
                for candidate in CRAWLER_SQL_TABLES:
                    if candidate.lower() == str(table).lower():
                        columns = table_columns(candidate)
                        display_name = candidate
                        break
            if not columns:
                continue
            rendered = ", ".join(columns)
            if len(rendered) > 700:
                rendered = rendered[:700] + " …"
            lines.append(f"{display_name}: {rendered}")
        return "\n".join(lines)

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
        tables: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        async with _get_engine().connect() as connection:
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
                    schema="crawler_sql_query_result",
                    metadata={
                        "database": "datacrawler_mysql",
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
                    "summary": f"查询到 {len(rows)} 条记录，完整结果已保存，当前返回 24 条样例。",
                    "metadata": {"columns": columns, "externalized": True},
                }
            except Exception as exc:
                logger.warning("crawler_sql_externalize_failed", error=str(exc))

        return {
            "success": True,
            "data": rows,
            "count": len(rows),
            "summary": f"查询到 {len(rows)} 条记录。",
            "metadata": {"columns": columns, "externalized": False},
        }

    @staticmethod
    def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
        return {key: ExecuteCrawlerSQLQueryTool._serialize_value(value) for key, value in row.items()}

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, bytes):
            return value.hex()
        return value

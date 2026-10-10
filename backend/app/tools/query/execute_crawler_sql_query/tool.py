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
from app.agent.context.data_shape import shape_summary_suffix
from app.utils.sql_validator import SQLValidator

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext


logger = structlog.get_logger()


# DataCrawler（MySQL 8，采集库）：许昌本地长历史表 + 河南实时发布采集表（Ssfb*）。
CRAWLER_SQL_TABLES = [
    "StationHour",
    "CityHour",
    "StationDay",
    "CityDay",
    "CityYearPm25Avg",
    "Station",
    "SsfbCityHour",
    "SsfbCityDay",
    "SsfbSiteHour",
    "SsfbSiteDay",
    "SsfbCityRanking",
]

# 各表白名单对应的数据时间范围（实测），供 Agent 直接判断可查窗口、避免空查。
TABLE_TIME_RANGES: dict[str, str] = {
    "StationHour": "2016-01 起，许昌 6 国控站逐小时，更新至实时",
    "CityHour": "2020-07 起，许昌市逐小时",
    "StationDay": "2018-09 起，许昌站点逐日",
    "CityDay": "2018-09 起，许昌市逐日",
    "CityYearPm25Avg": "2014-2025，许昌市 PM2.5 年均值（每年 1 行）",
    "Station": "许昌站点目录（覆盖有限，站名可能为空）",
    "SsfbCityHour": "2026-10-09 起，河南 18 城市组逐小时（含济源）",
    "SsfbCityDay": "2026-10-03 起，河南 18 城市组逐日（含济源）",
    "SsfbSiteHour": "2026-10-09 起，许昌县级站逐小时",
    "SsfbSiteDay": "2026-10-08 起，许昌县级站逐日",
    "SsfbCityRanking": "2026-10 月度 / 2026 年度起（随 SsfbCityDay 每日 06:10 重算）",
}

MAX_LIMIT = 5000
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
            "大气监测采集库（MySQL）只读 SQL 查询工具：许昌本地长历史数据"
            "（站点/城市逐小时与逐日、PM2.5 年均值、站点目录）+ 河南实时发布采集表"
            "（Ssfb*：18 城市组含济源的小时/日/单项浓度排名、许昌县级站）。"
            "支持 describe_table 查看表结构，或 sql 执行 SELECT/CTE 查询，二者必须二选一。"
            f"仅允许白名单表：{', '.join(CRAWLER_SQL_TABLES)}；禁止采集运行日志和失败记录表。"
            "只允许 SELECT，禁止 INSERT/UPDATE/DELETE/DDL、注释和多语句；"
            f"使用 LIMIT 分页，最大返回 {MAX_LIMIT} 条。"
            "不确定字段时先调用 describe_table，不要查询 information_schema。"
            "\n\n【查询优先级】常规指标（18 城含济源的排名/最新小时日值/县级站）优先走"
            " xuchang_cube_metrics 语义层；本工具用于长历史、同比、跨年趋势和语义层未覆盖的明细。"
            "省内排名（含济源）：SsfbCityRanking（Rank* 升序=1 最优，相同值并列，"
            "需 periodType+period 过滤），不要用 SQL Server 的 HenanCityAccumulateRanking"
            "（省APP已停服，仅至2026-08）。"
            "月均/年均等自定义聚合：SsfbCityDay 可从 2026-10-03 聚合，"
            "更早历史用 CityDay（许昌，缺济源）并在结论注明数据源与覆盖差异。"
            "\n\n【各表数据时间范围】（查询窗口必须在范围内，否则空结果）：\n"
            + "\n".join(f"- {name}: {desc}" for name, desc in TABLE_TIME_RANGES.items())
            + "\n注意：StationHour 站名列是 StationName；StationDay/CityDay 没有 StationName 列，"
            "站名/城市名用 PositionName/Area，不要跨表套用列名。"
            "\n注意：老表（StationHour/CityHour/StationDay/CityDay/CityYearPm25Avg）仅覆盖许昌单城市，"
            "Ssfb* 表覆盖河南 18 城市组与许昌县级站，两套口径不要混算同比。"
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
            "\n- 18城排名（含济源）：SELECT City, RankPm25, PM25 FROM SsfbCityRanking "
            "WHERE PeriodType='monthly' AND Period='2026-10' ORDER BY RankPm25"
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
                        "description": f"未在 SQL 中指定 LIMIT 时使用的返回上限；最大 {MAX_LIMIT}。",
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

        return self._format_result(rows, normalized_sql, effective_limit, context, tables=referenced_tables)

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
            return "", f"LIMIT 必须是 1 到 {MAX_LIMIT} 的整数。"
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
        tables: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        columns = list(rows[0]) if rows else []
        data_shape = self._build_data_shape(columns, rows, len(rows), tables)
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
                        "data_shape": data_shape,
                    },
                )
                sample = rows[:12] + rows[-12:]
                return {
                    "success": True,
                    "data": sample,
                    "data_id": data_id,
                    "count": len(rows),
                    "sample_count": len(sample),
                    "summary": f"查询到 {len(rows)} 条记录，完整结果已保存，当前返回 24 条样例。{shape_summary_suffix(data_shape)}",
                    "data_shape": data_shape,
                    "metadata": {"columns": columns, "externalized": True},
                }
            except Exception as exc:
                logger.warning("crawler_sql_externalize_failed", error=str(exc))

        return {
            "success": True,
            "data": rows,
            "count": len(rows),
            "summary": f"查询到 {len(rows)} 条记录。{shape_summary_suffix(data_shape)}",
            "data_shape": data_shape,
            "metadata": {"columns": columns, "externalized": False},
        }

    def _build_data_shape(
        self,
        columns: list[str],
        rows: list[dict[str, Any]],
        row_count: int,
        tables: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """库侧精确类型优先（表契约），派生/跨表列回退样本推断。"""
        from app.agent.context.data_shape import (
            build_data_shape,
            infer_column_types,
        )
        from app.tools.query.execute_crawler_sql_query.table_contracts import (
            table_column_types,
        )

        exact_types: dict[str, str] = {}
        for table_name in tables or CRAWLER_SQL_TABLES:
            exact_types.update(table_column_types(str(table_name)))
        inferred_types = infer_column_types(rows, columns)
        columns_with_types = {
            str(name): exact_types.get(str(name)) or inferred_types.get(str(name), "str")
            for name in columns
        }
        source = "db" if exact_types else "inferred"
        return build_data_shape(columns_with_types, row_count, source)

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

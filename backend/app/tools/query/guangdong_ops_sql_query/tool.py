"""广东运维工单主数据集受控 SQL 查询工具（本地 PostgreSQL 同步层）。

对称 jiangsu 分支的 jiangsu_ops_sql_query：查询本地 guangdong_mart schema 的
工单同步数据集，SELECT-only、表白名单、行数上限、强制超时由外层包裹实现，
每次查询审计写入 guangdong_sync.query_audit。数据新鲜度见
guangdong_sync.sync_watermark（guangdong_work_order_fetcher 维护）。

数据集字段契约见同目录 contract.txt（与 fetcher 的 mart 表结构保持一致）。
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import asyncpg
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.sql_validator import SQLValidator

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

MART_SCHEMA = "guangdong_mart"
AUDIT_SCHEMA = "guangdong_sync"
FRESHNESS_COLUMN = {
    "working_orders": "update_time",
    "working_order_details": "process_start_time",
    "wo_commonfile_links": "create_time",
    "dim_station": "station_id",
    "dim_device": "device_id",
}


def _load_contract() -> tuple:
    """Load the dataset contract (single source kept in sync with the fetcher)."""
    text = (Path(__file__).with_name("contract.txt")).read_text(encoding="utf-8")
    tables: List[str] = []
    guide_lines: List[str] = []
    in_guide = False
    for line in text.splitlines():
        if line.startswith("TABLES:"):
            tables = [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]
        elif line.strip() == "GUIDE_START":
            in_guide = True
        elif line.strip() == "GUIDE_END":
            in_guide = False
        elif in_guide:
            guide_lines.append(line)
    if not tables or not guide_lines:
        raise RuntimeError(
            "contract.txt invalid (missing TABLES or GUIDE block)"
        )
    return tables, "\n".join(guide_lines)


MART_TABLES, MART_SCHEMA_GUIDE = _load_contract()


class ExecuteGuangdongMartSQLTool(LLMTool):
    """对 guangdong_mart 主数据集执行受控 SELECT 查询。"""

    DEFAULT_LIMIT = 50

    def __init__(self) -> None:
        self.tool_name = "execute_guangdong_mart_sql"
        self.sql_validator = SQLValidator(
            max_limit=1000,
            allowed_tables=MART_TABLES + ["information_schema.columns"],
        )
        function_schema = {
            "name": self.tool_name,
            "description": (
                "查询广东运维工单主数据集（本地PostgreSQL受控同步层）。"
                "只允许SELECT；表名白名单见工具说明；返回数据附数据截至时间与同步状态。"
                "此工具用于工单字段级取证与统计；实时状态核对优先 execute_ops_sql_query。"
                + MART_SCHEMA_GUIDE
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "describe_table": {
                        "type": "string",
                        "description": "查看数据集字段结构（与sql二选一），输入白名单中的表名",
                    },
                    "sql": {
                        "type": "string",
                        "description": "PostgreSQL SELECT查询语句（与describe_table二选一）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回记录数上限（默认50，最大1000）",
                        "default": 50,
                    },
                },
            },
        }
        super().__init__(
            name=self.tool_name,
            description="查询广东运维工单主数据集（工单/明细/附件/站点/设备，受控只读SQL）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    # ------------------------------------------------------------------ 入口
    async def execute(
        self,
        context: Optional["ExecutionContext"] = None,
        describe_table: Optional[str] = None,
        sql: Optional[str] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if describe_table and sql:
            return {"success": False, "data": None,
                    "summary": "describe_table 和 sql 参数不能同时使用"}
        if not describe_table and not sql:
            return {"success": False, "data": None,
                    "summary": "请提供 sql 或 describe_table 参数，二者必选其一"}

        if describe_table is not None:
            table = describe_table.strip().split(".")[-1].strip().lower()
            if table not in MART_TABLES:
                return {"success": False, "data": None,
                        "summary": f"表 {describe_table} 不在白名单中。允许: {', '.join(MART_TABLES)}"}
            return await self._describe_table(table)

        if limit is None:
            limit = self.DEFAULT_LIMIT
        limit = min(limit, self.sql_validator.max_limit)
        return await self._execute_sql(sql, limit, context)

    def _mart_dsn(self) -> str:
        dsn = os.getenv("OPS_MART_DATABASE_URL", "")
        if not dsn:
            raise RuntimeError("OPS_MART_DATABASE_URL 未配置（本地同步库连接）")
        return dsn

    # ------------------------------------------------------------ 表结构
    async def _describe_table(self, table: str) -> Dict[str, Any]:
        conn = await asyncpg.connect(self._mart_dsn())
        try:
            rows = await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = $1 AND table_name = $2 ORDER BY ordinal_position",
                MART_SCHEMA,
                table,
            )
            columns = [{"name": r["column_name"], "type": r["data_type"]} for r in rows]
            return {
                "success": True,
                "table": table,
                "columns": columns,
                "summary": f"{table}: {len(columns)} 列。字段业务含义以工具说明中的数据集约束为准。",
            }
        finally:
            await conn.close()

    # ------------------------------------------------------------ 查询
    async def _execute_sql(
        self, sql: str, limit: int, context: Optional["ExecutionContext"]
    ) -> Dict[str, Any]:
        started = time.monotonic()
        status = "ok"
        row_count = 0
        try:
            sql = self.sql_validator.normalize_sql(sql)
            is_valid, error_msg = self.sql_validator.validate(sql)
            if not is_valid:
                status = "rejected"
                return {
                    "success": False,
                    "data": [],
                    "summary": f"SQL校验失败: {error_msg}。允许的表: {', '.join(MART_TABLES)}",
                }

            # 行数上限由外层包裹强制，不依赖 LLM 写 LIMIT；多取一行用于判定截断。
            safe_sql = f"SELECT * FROM ({sql.rstrip('; ')}) AS _mart_query LIMIT {limit + 1}"
            statement = await self._statement_timeout_sql(safe_sql)

            conn = await asyncpg.connect(self._mart_dsn())
            try:
                # 契约中的表名为裸名（如 working_orders），指向 guangdong_mart schema。
                await conn.execute(f"SET search_path TO {MART_SCHEMA}, public")
                rows = await conn.fetch(statement)
                truncated = len(rows) > limit
                results = [dict(r) for r in rows[:limit]]
                row_count = len(results)
                data_as_of = await self._data_as_of(conn, sql)
            finally:
                await conn.close()

            sample_data = results
            file_path = None
            if context and len(results) > 24:
                columns = list(results[0].keys()) if results else []
                file_path = context.save_data(
                    data=results,
                    schema="sql_query_result",
                    metadata={"database": MART_SCHEMA, "sql": sql,
                              "row_count": len(results), "columns": columns},
                )
                sample_data = results[:12] + results[-12:]

            elapsed_ms = int((time.monotonic() - started) * 1000)
            return {
                "success": True,
                "data": sample_data,
                "file_path": file_path,
                "count": len(results),
                "sample_count": len(sample_data),
                "limit": limit,
                "truncated": truncated,
                "data_as_of": data_as_of,
                "summary": (
                    f"返回 {len(results)} 行（数据截至 {data_as_of}，耗时 {elapsed_ms}ms）"
                    + (f"；已达返回上限 {limit} 行，结果被截断，匹配行数更多" if truncated else "")
                ),
            }
        except Exception as exc:  # noqa: BLE001
            status = "error"
            logger.warning("guangdong_mart_sql_failed", error=str(exc))
            return {
                "success": False,
                "data": [],
                "summary": f"查询失败: {exc}。可用 describe_table 查看白名单表结构。",
            }
        finally:
            await self._audit_query(sql, row_count, status)

    async def _statement_timeout_sql(self, sql: str) -> str:
        return sql

    async def _data_as_of(self, conn: asyncpg.Connection, sql: str) -> Optional[str]:
        """以查询涉及的首个可判定表的水位给出数据截至时间。"""
        try:
            tables = self.sql_validator.extract_tables(sql)
            for table in tables:
                table = str(table).strip().strip('"').split(".")[-1].lower()
                column = FRESHNESS_COLUMN.get(table)
                if not column:
                    continue
                value = await conn.fetchval(
                    f"SELECT MAX({column})::text FROM {MART_SCHEMA}.{table}"
                )
                if value:
                    return value
            watermark = await conn.fetchval(
                f"SELECT MAX(updated_at)::text FROM {AUDIT_SCHEMA}.sync_watermark"
            )
            return watermark
        except Exception:  # noqa: BLE001
            return None

    async def _audit_query(self, sql: str, row_count: int, status: str) -> None:
        try:
            conn = await asyncpg.connect(self._mart_dsn())
            try:
                await conn.execute(
                    f"INSERT INTO {AUDIT_SCHEMA}.query_audit (tool, sql_text, row_count, status) "
                    "VALUES ($1, $2, $3, $4)",
                    self.tool_name,
                    (sql or "")[:8000],
                    row_count,
                    status,
                )
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            logger.debug("guangdong_mart_query_audit_skipped")

"""江苏运维主题数据集受控 SQL 查询工具（PostgreSQL / agent_reader）。

DEPLOYMENT ADDITION (2026-09-21): serves the jiangsu-ops mart semantic layer
(jiangsu_mart schema, local PostgreSQL). Follows the guarded-SQL decision:
one tool, SELECT-only, table whitelist, row cap, statement timeout and forced
read-only are enforced by the agent_reader database role; every query is
audited into jiangsu_sync.query_audit via the application database user.

The dataset field contracts embedded below mirror sync/datasets/*.yaml on the
deployment server (single governance source; keep both in sync).
"""

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


def _load_contract() -> tuple:
    """Load the dataset contract generated from sync/datasets/*.yaml (single source).

    contract.txt is produced by sync/gen_tool_contract.py (E:\\Tools\\suyuan-jiangsu);
    drift between the yaml sources and this file is checked daily by dq_check.py.
    """
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
            "contract.txt invalid (missing TABLES or GUIDE block) — "
            "regenerate with sync/gen_tool_contract.py"
        )
    return tables, "\n".join(guide_lines)


MART_TABLES, MART_SCHEMA_GUIDE = _load_contract()

class ExecuteJiangsuOpsSQLQueryTool(LLMTool):
    """对 jiangsu_mart 主题数据集执行受控 SELECT 查询。"""

    DEFAULT_LIMIT = 50

    def __init__(self):
        self.tool_name = "execute_jiangsu_mart_sql"
        self.sql_validator = SQLValidator(
            max_limit=1000,
            allowed_tables=MART_TABLES + ["information_schema.columns"],
        )
        function_schema = {
            "name": self.tool_name,
            "description": (
                "查询江苏运维主题数据集（本地PostgreSQL语义层：工单/告警/站点健康/站点日概况/质控执行/质控安排6张宽表+设备台账维度表）。"
                "只允许SELECT；表名白名单见工具说明；返回带数据截至时间。"
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
            description="查询江苏运维主题数据集（工单/告警/站点健康/日概况宽表，受控只读SQL）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    async def execute(
        self,
        context: Optional["ExecutionContext"] = None,
        describe_table: Optional[str] = None,
        sql: Optional[str] = None,
        limit: Optional[int] = None,
        **kwargs,
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
        import os
        dsn = os.getenv("OPS_MART_DATABASE_URL", "")
        if not dsn:
            raise RuntimeError("OPS_MART_DATABASE_URL 未配置（agent_reader 只读连接）")
        return dsn

    async def _describe_table(self, table: str) -> Dict[str, Any]:
        conn = await asyncpg.connect(self._mart_dsn())
        try:
            rows = await conn.fetch(
                """SELECT column_name, data_type
                   FROM information_schema.columns
                   WHERE table_schema='jiangsu_mart' AND table_name=$1
                   ORDER BY ordinal_position""",
                table,
            )
            columns = [{"name": r["column_name"], "type": r["data_type"]} for r in rows]
            return {
                "success": True,
                "table": table,
                "columns": columns,
                "summary": f"{table}: {len(columns)} 列。字段业务含义见工具说明中的契约。",
            }
        finally:
            await conn.close()

    async def _execute_sql(
        self, sql: str, limit: int, context: Optional["ExecutionContext"]
    ) -> Dict[str, Any]:
        started = time.monotonic()
        conn = None
        status = "ok"
        error = None
        row_count = 0
        data_as_of = None
        try:
            sql = self.sql_validator.normalize_sql(sql)
            is_valid, error_msg = self.sql_validator.validate(sql)
            if not is_valid:
                status = "rejected"
                error = error_msg
                return {
                    "success": False,
                    "data": [],
                    "summary": f"SQL验证失败: {error_msg}。允许的表: {', '.join(MART_TABLES)}",
                }

            # 行数上限用外层包裹强制，不依赖LLM写LIMIT
            safe_sql = f"SELECT * FROM ({sql.rstrip('; ')}) AS _mart_query LIMIT {limit}"

            conn = await asyncpg.connect(self._mart_dsn())
            rows = await conn.fetch(safe_sql)
            data_as_of = await conn.fetchval(
                "SELECT max(refreshed_at)::text FROM jiangsu_mart.mart_work_order_analysis"
            )
            results = [dict(r) for r in rows]
            row_count = len(results)

            sample_data = results
            file_path = None
            if context and len(results) > 24:
                columns = list(results[0].keys()) if results else []
                file_path = context.save_data(
                    data=results,
                    schema="sql_query_result",
                    metadata={"database": "jiangsu_mart", "sql": sql,
                              "row_count": len(results), "columns": columns},
                )
                sample_data = results[:12] + results[-12:]

            payload = {
                "success": True,
                "data": sample_data,
                "file_path": file_path,
                "count": len(results),
                "sample_count": len(sample_data),
                "data_as_of": data_as_of,
                "summary": f"返回 {len(results)} 行（数据截至 {data_as_of}）",
            }
            return payload
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("jiangsu_mart_sql_failed", error=error)
            return {"success": False, "data": [], "summary": f"查询失败: {error}"}
        finally:
            if conn is not None:
                await conn.close()
            await self._audit(
                context, sql, row_count, status, error,
                int((time.monotonic() - started) * 1000),
            )

    async def _audit(self, context, sql, row_count, status, error, duration_ms) -> None:
        """Best-effort 审计；失败只记日志不影响查询。"""
        try:
            import json
            import os
            app_dsn = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
            if not app_dsn:
                return
            session_id = getattr(context, "session_id", None) if context else None
            conn = await asyncpg.connect(app_dsn)
            try:
                await conn.execute(
                    """INSERT INTO jiangsu_sync.query_audit
                       (user_id, agent_mode, tool, dataset, params, rows_returned,
                        truncated, duration_ms, error)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                    str(getattr(context, "user_id", "") or "") if context else "",
                    str(getattr(context, "agent_mode", "") or "") if context else "",
                    self.tool_name,
                    "jiangsu_mart",
                    json.dumps({"sql": (sql or "")[:4000], "status": status}, ensure_ascii=False),
                    row_count,
                    False,
                    duration_ms,
                    error,
                )
                _ = session_id
            finally:
                await conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("jiangsu_mart_audit_failed", error=str(exc))

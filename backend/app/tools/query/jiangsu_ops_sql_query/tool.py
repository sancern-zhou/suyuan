"""江苏运维主题数据集受控 SQL 查询工具（PostgreSQL / agent_reader）。

DEPLOYMENT ADDITION (2026-09-21): serves the jiangsu-ops mart semantic layer
(jiangsu_mart schema, local PostgreSQL). Follows the guarded-SQL decision:
one tool, SELECT-only, table whitelist, row cap, statement timeout and forced
read-only are enforced by the agent_reader database role; every query is
audited into jiangsu_sync.query_audit via the application database user.

The dataset field contracts embedded below mirror sync/datasets/*.yaml on the
deployment server (single governance source; keep both in sync).
"""

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import asyncpg
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.sql_validator import SQLValidator
from app.tools.query.jiangsu_cube_metrics.semantic_registry import dataset_metadata
from app.tools.query.jiangsu_cube_metrics.result_contract import validate_result
from app.tools.query.jiangsu_cube_metrics.quality_policy import quality_guidance

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


def _load_contract_file(path: Path, label: str) -> tuple:
    """Load a generated dataset contract (TABLES line + GUIDE block)."""
    text = path.read_text(encoding="utf-8")
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
            f"{label} invalid (missing TABLES or GUIDE block) — "
            "regenerate with sync/gen_*contract.py"
        )
    return tables, "\n".join(guide_lines)


def _load_contract() -> tuple:
    """Load the dataset contract generated from sync/datasets/*.yaml (single source).

    contract.txt is produced by sync/gen_tool_contract.py (E:\\Tools\\suyuan-jiangsu);
    drift between the yaml sources and this file is checked daily by dq_check.py.
    """
    return _load_contract_file(Path(__file__).with_name("contract.txt"), "contract.txt")


def _load_ods_contract() -> tuple:
    """Load the ODS fallback whitelist generated from sync_config.json.

    ods_contract.txt is produced by sync/gen_ods_fallback_contract.py: every synced
    ODS table that no mart/dim contract covers stays queryable here, so no synced
    data is unreachable to the agent (low-frequency raw fallback).
    """
    path = Path(__file__).with_name("ods_contract.txt")
    if not path.exists():
        logger.warning(
            "jiangsu_ods_contract_missing",
            path=str(path),
            hint="run sync/gen_ods_fallback_contract.py to restore the ODS fallback channel",
        )
        return [], ""
    return _load_contract_file(path, "ods_contract.txt")


MART_TABLES, MART_SCHEMA_GUIDE = _load_contract()
ODS_TABLES, ODS_SCHEMA_GUIDE = _load_ods_contract()
ODS_TABLE_SET = set(ODS_TABLES)
MART_TABLE_SET = set(MART_TABLES)

class ExecuteJiangsuOpsSQLQueryTool(LLMTool):
    """对 jiangsu_mart 主题数据集执行受控 SELECT 查询。"""

    DEFAULT_LIMIT = 50

    def __init__(self):
        self.tool_name = "execute_jiangsu_mart_sql"
        self.sql_validator = SQLValidator(
            max_limit=1000,
            allowed_tables=MART_TABLES + ODS_TABLES + ["information_schema.columns"],
        )
        function_schema = {
            "name": self.tool_name,
            "description": (
                "查询江苏运维主题数据集（本地PostgreSQL受控取证层）。"
                "只允许SELECT；表名白名单见工具说明；返回数据截至时间、语义上下文和质量状态。"
                "此工具用于字段级取证，官方指标计算优先使用 jiangsu_query_metrics。"
                + MART_SCHEMA_GUIDE
                + ODS_SCHEMA_GUIDE
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
            schema = self._schema_of(table)
            if schema is None:
                return {"success": False, "data": None,
                        "summary": f"表 {describe_table} 不在白名单中。允许: {', '.join(MART_TABLES + ODS_TABLES)}"}
            return await self._describe_table(table, schema)

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

    @staticmethod
    def _schema_of(table: str) -> Optional[str]:
        """Resolve which schema a whitelisted table lives in (None = not allowed)."""
        if table in MART_TABLE_SET:
            return "jiangsu_mart"
        if table in ODS_TABLE_SET:
            return "jiangsu_ods"
        return None

    async def _connect(self):
        """Read-only connection; search_path exposes mart and ODS fallback tables."""
        return await asyncpg.connect(
            self._mart_dsn(),
            server_settings={"search_path": "jiangsu_mart,jiangsu_ods"},
        )

    async def _describe_table(self, table: str, schema: str = "jiangsu_mart") -> Dict[str, Any]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                """SELECT column_name, data_type
                   FROM information_schema.columns
                   WHERE table_schema=$2 AND table_name=$1
                   ORDER BY ordinal_position""",
                table, schema,
            )
            columns = [
                {"name": r["column_name"], "type": r["data_type"]}
                for r in rows
                # ODS 同步内部列（_src_incremental/_sync_batch/_synced_at）不是业务字段，
                # 且 _synced_at 只在首插时写入，露出来会误导"数据新鲜度"判断。
                if not r["column_name"].startswith("_")
            ]
            semantic = dataset_metadata(table)
            payload = {
                "success": True,
                "table": table,
                "schema": schema,
                "layer": "mart" if schema == "jiangsu_mart" else "ods_fallback",
                "columns": columns,
                "semantic_context": {
                    "query_role": "schema_introspection",
                    "official_metric_calculation": False,
                    "dataset": table,
                    "cube": semantic.get("cube"),
                    "grain": semantic.get("grain"),
                    "applicability": semantic.get("applicability"),
                    "source_window": semantic.get("source_window"),
                    "limitations": semantic.get("limitations", []),
                    "registry_version": semantic.get("registry_version", 0),
                },
                "summary": f"{table}: {len(columns)} 列。字段业务含义见工具说明中的契约。",
            }
            contract_errors = validate_result("schema_introspection", payload)
            if contract_errors:
                logger.warning("jiangsu_schema_result_contract_violation", errors=contract_errors)
            return payload
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
        truncated = False
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
                    "summary": f"SQL验证失败: {error_msg}",
                }

            # 行数上限用外层包裹强制，不依赖LLM写LIMIT；多取一行用于判定是否被截断
            safe_sql = f"SELECT * FROM ({sql.rstrip('; ')}) AS _mart_query LIMIT {limit + 1}"

            conn = await self._connect()
            rows = await conn.fetch(safe_sql)
            truncated = len(rows) > limit
            results = [dict(r) for r in rows[:limit]]
            row_count = len(results)
            datasets = self._datasets_from_sql(sql)
            ods_tables = self._ods_tables_from_sql(sql)
            semantic_entries = [dataset_metadata(table) for table in datasets]
            primary_semantic = semantic_entries[0] if semantic_entries else {}
            time_column = self._freshness_column(datasets[0]) if datasets else None
            if time_column:
                data_as_of = await conn.fetchval(
                    f"SELECT max({time_column})::text FROM jiangsu_mart.{datasets[0]}"
                )
            elif ods_tables:
                data_as_of = await self._ods_data_as_of(conn, ods_tables)
            quality_checks = await self._quality_checks(conn, datasets + ods_tables)
            quality_status = self._quality_status_from_checks(quality_checks)

            sample_data = results
            file_path = None
            if context and len(results) > 24:
                columns = list(results[0].keys()) if results else []
                file_path = context.save_data(
                    data=results,
                    schema="sql_query_result",
                    metadata={"database": "jiangsu_mart", "sql": sql,
                              "row_count": len(results), "columns": columns,
                              "semantic_registry_version": primary_semantic.get("registry_version", 0),
                              "quality_status": quality_status},
                )
                sample_data = results[:12] + results[-12:]

            payload = {
                "success": True,
                "data": sample_data,
                "file_path": file_path,
                "count": len(results),
                "sample_count": len(sample_data),
                "limit": limit,
                "truncated": truncated,
                "data_as_of": data_as_of,
                "quality_status": quality_status,
                "semantic_context": {
                    "query_role": "field_evidence",
                    "official_metric_calculation": False,
                    "datasets": datasets,
                    "ods_tables": ods_tables,
                    "layer": "ods_fallback" if ods_tables and not datasets else "mart",
                    "dataset": primary_semantic.get("dataset"),
                    "cube": primary_semantic.get("cube"),
                    "grain": primary_semantic.get("grain"),
                    "applicability": primary_semantic.get("applicability"),
                    "source_window": primary_semantic.get("source_window"),
                    "data_as_of": data_as_of,
                    "limitations": primary_semantic.get("limitations", []),
                    "registry_version": primary_semantic.get("registry_version", 0),
                    "quality_checks": quality_checks,
                    "quality_guidance": quality_guidance(quality_status),
                    "interpretation": (
                        "此结果用于字段级取证；官方汇总指标应优先使用 jiangsu_query_metrics。"
                        if not (ods_tables and not datasets)
                        else "此结果为 ODS 原始层兜底查询，字段为平台原值、无业务口径加工；"
                             "汇总口径问题请优先用 mart/dim 表或 jiangsu_query_metrics。"
                    ),
                },
                "summary": (
                    f"返回 {len(results)} 行（数据截至 {data_as_of}，质量状态：{quality_status}）"
                    + (f"；已达返回上限 {limit} 行，结果被截断，匹配行数更多" if truncated else "")
                ),
            }
            contract_errors = validate_result("evidence_sql", payload)
            if contract_errors:
                logger.warning("jiangsu_sql_result_contract_violation", errors=contract_errors)
            return payload
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("jiangsu_mart_sql_failed", error=error)
            hint = await self._schema_hint_for_error(exc, sql)
            return {"success": False, "data": [], "summary": f"查询失败: {error}{hint}"}
        finally:
            if conn is not None:
                await conn.close()
            await self._audit(
                context, sql, row_count, status, error, truncated,
                int((time.monotonic() - started) * 1000),
            )

    @staticmethod
    def _referenced_tables(sql: str) -> List[str]:
        """Table names referenced after FROM/JOIN, schema qualifier stripped."""
        found: List[str] = []
        for match in re.finditer(
            r"(?:from|join)\s+(?:jiangsu_(?:mart|ods)\s*\.\s*)?\"?([a-zA-Z_][\w]*)\"?",
            sql,
            re.IGNORECASE,
        ):
            table = match.group(1).lower()
            if table in {"jiangsu_mart", "jiangsu_ods"}:
                continue
            if table not in found:
                found.append(table)
        return found

    @classmethod
    def _datasets_from_sql(cls, sql: str) -> List[str]:
        return [t for t in cls._referenced_tables(sql) if t in MART_TABLE_SET]

    @classmethod
    def _ods_tables_from_sql(cls, sql: str) -> List[str]:
        return [t for t in cls._referenced_tables(sql) if t in ODS_TABLE_SET]

    @staticmethod
    async def _ods_data_as_of(conn, tables: List[str]) -> Optional[str]:
        """ODS 兜底表的数据时点 = 最近一次成功同步完成时间。

        ODS 表的 _synced_at 只在首次 INSERT 写入、upsert 冲突不刷新，不能用来判断新鲜度；
        心跳表 sync_watermark.updated_at 才是每轮同步刷新的时间。
        """
        try:
            ts = await conn.fetchval(
                """SELECT max(updated_at)::text FROM jiangsu_sync.sync_watermark
                   WHERE table_name = ANY($1::text[]) AND last_status = 'ok'""",
                tables,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("jiangsu_ods_data_as_of_unavailable", error=str(exc))
            return None
        return ts

    @staticmethod
    def _freshness_column(table: str) -> Optional[str]:
        if table in {"mart_work_order_analysis", "mart_alarm_event_analysis",
                     "mart_station_device_health", "mart_station_daily_profile"}:
            return "refreshed_at"
        return "synced_at"

    @staticmethod
    async def _quality_checks(conn, datasets: List[str]) -> List[Dict[str, str]]:
        if not datasets:
            return []
        try:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (table_name, check_name) table_name, check_name, status, detail
                FROM jiangsu_sync.dq_results
                WHERE table_name = ANY($1::text[])
                ORDER BY table_name, check_name, checked_at DESC
                """,
                datasets,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("jiangsu_mart_quality_checks_unavailable", error=str(exc))
            return []
        return [
            {"table": row["table_name"], "check": row["check_name"],
             "status": row["status"], "detail": row["detail"]}
            for row in rows
        ]

    @staticmethod
    def _quality_status_from_checks(checks: List[Dict[str, str]]) -> str:
        if not checks:
            return "unknown"
        statuses = {item["status"] for item in checks}
        if "FAIL" in statuses:
            return "blocked"
        if "WARN" in statuses:
            return "degraded"
        return "ok"

    async def _schema_hint_for_error(self, exc: Exception, sql: str) -> str:
        """列/表不存在时附上相关白名单表的实际列结构，让模型在同一轮自纠，
        避免再花一轮迭代调 describe_table。失败静默，不影响原始错误返回。"""
        try:
            import asyncpg.exceptions as _pgexc
            if not isinstance(exc, (_pgexc.UndefinedColumnError, _pgexc.UndefinedTableError)):
                return ""
            candidates: List[str] = [
                t for t in self._referenced_tables(sql) if self._schema_of(t)
            ]
            if not candidates:
                if isinstance(exc, _pgexc.UndefinedTableError):
                    return f" 提示: 表不在白名单。允许: {', '.join(MART_TABLES + ODS_TABLES)}"
                return ""
            conn = await self._connect()
            try:
                hints = []
                for table in candidates[:3]:
                    rows = await conn.fetch(
                        """SELECT column_name, data_type FROM information_schema.columns
                           WHERE table_schema=$2 AND table_name=$1
                           ORDER BY ordinal_position""",
                        table, self._schema_of(table),
                    )
                    cols = ", ".join(f"{r['column_name']} {r['data_type']}" for r in rows)
                    hints.append(f"{table}({cols})")
                text = " | ".join(hints)
                return " 可用列结构: " + (text[:1500] + "…" if len(text) > 1500 else text)
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            return ""

    async def _audit(self, context, sql, row_count, status, error, truncated, duration_ms) -> None:
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
                    (
                        "jiangsu_mart"
                        if self._datasets_from_sql(sql or "")
                        or not self._ods_tables_from_sql(sql or "")
                        else "jiangsu_ods"
                    ),
                    json.dumps({"sql": (sql or "")[:4000], "status": status}, ensure_ascii=False),
                    row_count,
                    truncated,
                    duration_ms,
                    error,
                )
                _ = session_id
            finally:
                await conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("jiangsu_mart_audit_failed", error=str(exc))

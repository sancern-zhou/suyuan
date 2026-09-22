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
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import asyncpg
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.sql_validator import SQLValidator

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

MART_TABLES = [
    "mart_work_order_analysis",
    "mart_alarm_event_analysis",
    "mart_station_device_health",
    "mart_station_daily_profile",
]

MART_SCHEMA_GUIDE = (
    "\n\n【江苏运维主题数据集契约（PostgreSQL，仅下列4张表）】"
    "\n数据自2026-07-01起；不支持同比/年度；实时状态请走平台API工具，不在本数据集。"
    "\n生成SQL前先读契约，直接生成SQL，不要先describe_table；仅当契约未列字段时才describe_table。"
    "\n- mart_work_order_analysis（工单宽表，一行=一张故障工单）："
    "维度 working_order_code/station_code/station_name/city_name/device_id/order_type/order_status_cn"
    "(处理中/已完成/已作废)/urgency_type；时间 create_time/dispatch_time/arrival_time/finish_time/plan_finish_time；"
    "指标 response_minutes(响应=派单→到站)/process_minutes/repair_minutes/is_overdue(按plan_finish_time)/"
    "is_repeat_fault(同站同设备30天)/repeat_fault_basis/repeat_count_30d/alarm_count_1d/node_count。"
    "注意：派单/到站为工作流节点代理口径；平台存在大量长期未闭环单，超期率~85%是数据现状。"
    "\n- mart_alarm_event_analysis（告警宽表，一行=一条站点告警）："
    "维度 station_code/station_name/city_name/alarm_level_cn(紧急/中级/一般)/alarm_state_cn(未处理/已解除)/rule_type/alarm_content；"
    "时间 alarm_time/handle_time/remove_time；指标 duration_minutes/handle_minutes/is_unresolved/linked_work_orders_24h。"
    "\n- mart_station_device_health（站点健康，一行=一个站点）："
    "work_orders_30d/overdue_orders_30d/overdue_rate_30d/repeat_fault_orders_30d/avg_response_minutes_30d/"
    "alarms_7d/alarms_30d/unresolved_alarms/last_alarm_time/last_work_order_time/device_count/"
    "risk_level(高/中/低/稳定)。当前态势类问题优先查本表。"
    "\n- mart_station_daily_profile（站点日概况，一行=站点×日）："
    "profile_date/station_code/city_name/work_orders_created/work_orders_finished/overdue_orders_created/alarms/"
    "attendance_signins(源数据稀疏)。趋势/对比类问题查本表，当日数据次日凌晨才完整。"
    "\n【SQL方言】PostgreSQL：用 LIMIT 不用 TOP；日期截断用 date_trunc('day', col)；"
    "布尔列直接用 IS TRUE / = TRUE；时间比较用 '2026-09-01' 字面量。"
    "查询务必带 LIMIT（上限1000）；聚合统计优先 GROUP BY 城市或站点返回小结果集。"
)


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
                "查询江苏运维主题数据集（本地PostgreSQL语义层：工单/告警/站点健康/站点日概况4张宽表）。"
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

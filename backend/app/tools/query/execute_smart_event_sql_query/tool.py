"""Read-only PostgreSQL SQL query tool for the smart-event center tables.

The smart-event center persists structured events, task cards and review state
in PostgreSQL (see ``app.services.smart_event_db``).  Alarm-history analysis is
much cheaper against those promoted/indexed columns than against the raw
operations alarm API, so this tool is exposed to the operations-analysis mode
instead of forcing a full platform sweep.

The whitelist and field contract below are injected for that mode: the tool
only reads the event-center tables and never touches other business schemas.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.sql_validator import SQLValidator

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger(__name__)


SMART_EVENT_SQL_TABLES: list[str] = [
    "smart_events",
    "smart_event_tasks",
    "smart_event_state",
    "task_reviews",
]


SMART_EVENT_SCHEMA_GUIDE = (
    "\n\n【事件中心表字段契约（PostgreSQL）】"
    "\n- smart_events：智能事件主表，一行一个事件（同站同日归并后的结果）。"
    "提升列可直接过滤/排序：event_id、event_status、event_type、ai_event_type、ai_suggested_level、"
    "site_id、site_name、event_name、primary_clue_tag、source_alarm_rule_type、"
    "latest_occurrence_time、event_start_time、created_at、updated_at、archived。"
    "完整事件文档在 data (JSONB)，原始证据在 evidence (JSONB)。"
    "JSONB 取值示例：data->>'alarm_content'、data->>'city_name'、data->>'district_name'、"
    "data->>'ai_data_impact'、data->'clue_tags'、data #>> '{ai_judgment,final_response}'；"
    "归并的原始告警条数用 jsonb_array_length(data->'merged_alarm_ids')，"
    "原始告警明细在 evidence->'alarms'。"
    "\n- smart_event_tasks：事件关联任务卡。列为 task_id、event_id、status、scheduled_task_id、"
    "created_at、updated_at；完整任务文档在 data (JSONB)。"
    "\n- smart_event_state：键值状态表。列为 key、value (JSONB)、updated_at；"
    "例如 key='last_sync' 记录最近同步状态。"
    "\n- task_reviews：人工复核与处置状态。列为 review_id、event_id、subject_id、category、title、"
    "summary、decision、status、task_id、created_at、updated_at；"
    "有效处置状态以 task_reviews.status 为准（archived/in_disposal/rejected 等），"
    "smart_events.event_status 可能滞后。"
    "\n【口径提醒】"
    "\n- 按“原始告警条数”统计时不要直接数 smart_events 行数：事件已按站点+自然日归并，"
    "应使用 jsonb_array_length(data->'merged_alarm_ids') 或展开 evidence->'alarms'。"
    "\n- 事件状态过滤优先 LEFT JOIN task_reviews（review_id = task_reviews.review_id 或 event_id 关联），"
    "不要只用 smart_events.event_status。"
)


class ExecuteSmartEventSQLQueryTool(LLMTool):
    """Execute read-only SELECT queries against the smart-event PostgreSQL tables."""

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 200

    def __init__(self) -> None:
        self.sql_validator = SQLValidator(
            max_limit=self.MAX_LIMIT, allowed_tables=SMART_EVENT_SQL_TABLES
        )
        super().__init__(
            name="execute_smart_event_sql_query",
            description=(
                "在智能事件中心 PostgreSQL 库执行只读 SELECT 查询，按结构化字段检索事件、任务卡与处置状态。"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=True,
            function_schema={
                "name": "execute_smart_event_sql_query",
                "description": (
                    "智能事件中心结构化查询工具（PostgreSQL）。用于按站点、时间、事件类型、等级、状态、"
                    "线索、处置进展等字段查询已归并入库的事件与任务，适合报警积压、风险扫描、分单位/站点聚合等分析。"
                    "支持二选一：describe_table 查看白名单表结构，或 sql 执行只读 SELECT 查询。"
                    "硬约束：只允许 SELECT/WITH；禁止 INSERT/UPDATE/DELETE/DDL；禁止 SQL 注释和多条语句；"
                    "必须带 LIMIT（默认 50，最大 200），返回最多 200 行。"
                    "PostgreSQL 语法：JSONB 用 ->> / #>> 取值；字符串用单引号；时间过滤用 ::timestamptz 或标准 ISO 字面量。"
                    "只能查询下方列出的白名单表，禁止查询 information_schema 或其他系统表做表名发现（describe_table 除外）。"
                    + SMART_EVENT_SCHEMA_GUIDE
                    + "\n\n提示：字段不确定时先调用 describe_table。原始告警接口（jiangsu_fetch_alarm_records）"
                    "只作为按站点复核的兜底通道，优先使用本工具。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "describe_table": {
                            "type": "string",
                            "description": "查看白名单表结构（与 sql 二选一），输入表名，如 smart_events。",
                        },
                        "sql": {
                            "type": "string",
                            "description": "只读 SELECT 查询语句（与 describe_table 二选一），必须带 LIMIT。",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回记录数限制（默认 50，最大 200），仅用于 sql 查询。",
                            "default": 50,
                        },
                    },
                },
            },
        )

    async def execute(
        self,
        context: ExecutionContext | None = None,
        describe_table: str | None = None,
        sql: str | None = None,
        limit: int | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        if describe_table and sql:
            return {"success": False, "data": None, "summary": "describe_table 和 sql 不能同时使用，请只提供其中一个"}
        if not describe_table and not sql:
            return {"success": False, "data": None, "summary": "请提供 describe_table（查看表结构）或 sql（执行查询）"}

        from app.services.smart_event_db import smart_event_db_enabled

        if not smart_event_db_enabled():
            return {
                "success": False,
                "data": [],
                "summary": "事件中心当前未启用 PostgreSQL 存储（SMART_EVENT_STORAGE/DATABASE_URL 未配置），无法执行结构化查询。",
            }

        if describe_table:
            return await self._describe_table(str(describe_table).strip())
        return await self._execute_sql(str(sql or ""), limit, context)

    async def _describe_table(self, table_name: str) -> dict[str, Any]:
        if table_name not in SMART_EVENT_SQL_TABLES:
            return {
                "success": False,
                "data": None,
                "summary": f"表 '{table_name}' 不在白名单中。可用表: {', '.join(SMART_EVENT_SQL_TABLES)}",
            }
        try:
            rows = await self._run_sql(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = :table_name "
                "ORDER BY ordinal_position",
                {"table_name": table_name},
            )
            if not rows:
                return {"success": False, "data": None, "summary": f"未找到表 '{table_name}' 的结构信息"}
            fields = "\n".join(
                f"  - {row['column_name']} ({row['data_type']}, {'可空' if row['is_nullable'] == 'YES' else '非空'})"
                for row in rows
            )
            return {
                "success": True,
                "data": {"table_name": table_name, "columns": rows},
                "summary": f"表 {table_name} 字段（{len(rows)} 个）:\n{fields}",
            }
        except Exception as exc:  # noqa: BLE001 - surface DB errors to the Agent
            logger.warning("smart_event_describe_table_failed", table=table_name, error=str(exc))
            return {"success": False, "data": None, "summary": f"查询表结构失败: {exc}"}

    async def _execute_sql(
        self,
        sql: str,
        limit: int | None,
        context: ExecutionContext | None,
    ) -> dict[str, Any]:
        default_limit = self.DEFAULT_LIMIT if limit is None else limit
        if not isinstance(default_limit, int) or default_limit < 1:
            return {"success": False, "data": [], "summary": "limit 必须是正整数"}
        default_limit = min(default_limit, self.MAX_LIMIT)

        sql = self.sql_validator.normalize_sql(sql)
        if not sql:
            return {"success": False, "data": [], "summary": "SQL 语句为空"}

        referenced = self.sql_validator.extract_tables(sql)
        information_schema_tables = [
            table for table in referenced if table.lower().startswith("information_schema.")
        ]
        if information_schema_tables:
            return {
                "success": False,
                "data": [],
                "summary": (
                    "不允许直接查询 "
                    f"{', '.join(information_schema_tables)} 做表名发现；"
                    "请使用 describe_table 查看白名单表结构，并只查询工具说明列出的白名单表。"
                ),
            }

        is_valid, error_msg = self.sql_validator.validate(sql)
        if not is_valid:
            return {"success": False, "data": [], "summary": f"SQL 验证失败: {error_msg}"}

        safe_sql = self.sql_validator.sanitize_limit(sql, default_limit)
        try:
            rows = await self._run_sql(safe_sql)
        except Exception as exc:  # noqa: BLE001 - surface DB errors to the Agent
            logger.warning("smart_event_sql_query_failed", error=str(exc), sql_preview=safe_sql[:120])
            return {"success": False, "data": [], "summary": f"查询失败: {exc}"}

        rows = [{key: _jsonable(value) for key, value in row.items()} for row in rows]
        return self._externalize(rows, safe_sql, default_limit, context)

    @staticmethod
    async def _run_sql(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from sqlalchemy import text

        from app.db.sync_bridge import bridge_session, run_db_async

        async def _run() -> list[dict[str, Any]]:
            async with bridge_session() as session:
                result = await session.execute(text(sql), params or {})
                return [dict(row) for row in result.mappings().all()]

        return await run_db_async(_run())

    @staticmethod
    def _externalize(
        rows: list[dict[str, Any]],
        sql: str,
        limit: int,
        context: ExecutionContext | None,
    ) -> dict[str, Any]:
        columns = list(rows[0].keys()) if rows else []
        if context is not None and hasattr(context, "save_data") and len(rows) > 24:
            try:
                file_path = context.save_data(
                    data=rows,
                    schema="smart_event_sql_query_result",
                    metadata={"sql": sql, "row_count": len(rows), "columns": columns, "limit": limit},
                )
                head = rows[:12]
                tail = rows[-12:]
                return {
                    "success": True,
                    "data": head + tail,
                    "file_path": file_path,
                    "count": len(rows),
                    "sample_count": len(head) + len(tail),
                    "summary": f"查询到 {len(rows)} 条记录（已外部化，返回首尾样本 {len(head) + len(tail)} 条）",
                    "metadata": {"columns": columns, "externalized": True},
                }
            except Exception as exc:  # noqa: BLE001 - fall back to inline result
                logger.warning("smart_event_sql_externalize_failed", error=str(exc))
        return {
            "success": True,
            "data": rows,
            "count": len(rows),
            "summary": f"查询到 {len(rows)} 条记录",
            "metadata": {"columns": columns, "externalized": False},
        }


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)

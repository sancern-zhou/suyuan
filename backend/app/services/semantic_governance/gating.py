# -*- coding: utf-8 -*-
"""DQ 质量门查询与宽表新鲜度探针（schema/表/列/DSN 全部参数化）。

标识符插值（dq_table / schema / table / column）只允许来自部署配置常量，
禁止拼接用户输入。所有探针 fail-open：失败返回 unknown/None 并告警，
不阻塞指标查询本身。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import structlog

logger = structlog.get_logger()

LATEST_DQ_CHECKS_SQL = """
SELECT DISTINCT ON (check_name) check_name, status, detail
FROM {dq_table}
WHERE table_name = $1
ORDER BY check_name, checked_at DESC
"""


def aggregate_quality(checks: Sequence[Dict[str, Any]]) -> str:
    """checks → 状态：有 FAIL→blocked；有 WARN→degraded；全 OK→ok；空→unknown。"""
    if not checks:
        return "unknown"
    statuses = {item.get("status") for item in checks}
    if "FAIL" in statuses:
        return "blocked"
    if "WARN" in statuses:
        return "degraded"
    return "ok"


def _checks_from_rows(rows: Sequence[Any]) -> List[Dict[str, str]]:
    return [
        {"check": row["check_name"], "status": row["status"], "detail": row["detail"]}
        for row in rows
    ]


async def quality_status(dsn: str, dq_table: str,
                         table_name: str) -> "tuple[str, List[Dict[str, str]]]":
    """读取某宽表最新一轮 DQ 门结果（不阻塞指标查询）。"""
    if not dsn or not table_name:
        return "unknown", []
    try:
        import asyncpg
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                LATEST_DQ_CHECKS_SQL.format(dq_table=dq_table), table_name)
        finally:
            await conn.close()
        checks = _checks_from_rows(rows)
        return aggregate_quality(checks), checks
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_governance_quality_unavailable", error=str(exc))
        return "unknown", []


async def data_as_of(dsn: str, schema: str, table: str, column: str) -> Optional[str]:
    """宽表新鲜度（与 SQL 取证工具同源）；失败不阻塞查询。"""
    if not dsn:
        return None
    try:
        import asyncpg
        conn = await asyncpg.connect(dsn)
        try:
            return await conn.fetchval(
                f"SELECT max({column})::text FROM {schema}.{table}")
        finally:
            await conn.close()
    except Exception:  # noqa: BLE001
        return None

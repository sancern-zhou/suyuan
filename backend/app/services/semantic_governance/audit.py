# -*- coding: utf-8 -*-
"""best-effort 查询审计写入；列形状由调用方定义。

同一部署里不同工具的审计列形状不同（如指标工具 9 列、SQL 工具 4 列），
共享层只负责"dict → INSERT"的通用构造与失败吞噬；表名来自部署配置常量。
审计失败只记日志，绝不影响查询结果本身。
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

import structlog

logger = structlog.get_logger()


def build_insert(table: str, record: Dict[str, Any]) -> Tuple[str, list]:
    """record（列名→值，键序即列序）→ (INSERT SQL, 值列表)。"""
    columns = list(record)
    if not columns:
        raise ValueError("audit record requires at least one column")
    column_list = ", ".join(columns)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
    sql = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"
    return sql, [record[column] for column in columns]


async def write_audit(dsn: str, table: str, record: Dict[str, Any], *,
                      log_event: str = "semantic_governance_audit_failed") -> bool:
    """写一条审计；任何失败只告警并返回 False。"""
    if not dsn or not record:
        return False
    try:
        import asyncpg
        sql, values = build_insert(table, record)
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(sql, *values)
        finally:
            await conn.close()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(log_event, error=str(exc))
        return False

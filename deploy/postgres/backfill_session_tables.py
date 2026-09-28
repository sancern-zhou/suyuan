"""把远端 DATABASE_URL 中的会话相关表回补到本机 SESSION_DATABASE_URL。

用于本机 PostgreSQL 部署（见同目录 README.md）：先迁移最近 N 天，历史数据在带宽空闲时
再分批回补。覆盖的表见 TABLES 配置（会话消息、目录、资源、Draw.io、社交、定时任务执行）。

环境变量：
  SRC_DATABASE_URL     源库（如远端 weather_db），形如 postgresql://user:pass@host:5432/db；
                       未设置时读取 backend/.env 的 DATABASE_URL
  SESSION_DATABASE_URL 目标库，未设置时读取本目录 .env 的 LOCAL_PG_*

用法：
  python backfill_session_tables.py recent --days 7
  python backfill_session_tables.py recent --days 7 --tables drawio_boards,drawio_board_versions
  python backfill_session_tables.py delta --since 2026-09-21T09:55:00
  python backfill_session_tables.py history --before 2026-09-14T00:00:00
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

import asyncpg

HERE = Path(__file__).resolve().parent

# key: primary key column (用于 upsert)
# mode: "id"  仅追加整型主键（消息），按 key > 本机最大值 增量
#       "ts"  用 time_col 做时间窗口增量 + 按 key upsert
#       "scope" 按活跃会话范围整体覆盖（规避 text 主键跨库排序差异）
#       "all" 全量 upsert（小表）
# scope_col: recent 模式取数范围列；"session" 表示按活跃会话过滤
# time_col: delta 模式增量列
TABLES = {
    "sessions": dict(key="id", mode="ts", scope_col="updated_at", time_col="updated_at", scope="ts"),
    "session_messages": dict(key="id", mode="id", scope="session"),
    "session_resources": dict(key="resource_id", mode="ts", scope_col="updated_at", time_col="updated_at", scope="session"),
    "session_resource_versions": dict(key="session_id", mode="scope", scope="session"),
    "scheduled_task_executions": dict(key="execution_id", mode="ts", scope_col="started_at", time_col="updated_at", scope="ts"),
    "conversation_catalog": dict(key="session_id", mode="ts", scope_col="updated_at", time_col="updated_at", scope="session"),
    "drawio_boards": dict(key="id", mode="ts", scope_col="updated_at", time_col="updated_at", scope="all"),
    "drawio_board_versions": dict(key="id", mode="ts", scope_col="created_at", time_col="created_at", scope="all"),
    "social_users": dict(key="id", mode="all", scope="all"),
    "social_session_mappings": dict(key="social_user_id", mode="all", scope="all"),
    "weixin_scan_tasks": dict(key="id", mode="all", scope="all"),
    "social_report_results": dict(key="report_id", mode="all", scope="all"),
}

ACTIVE_SESSIONS = "SELECT session_id FROM sessions WHERE updated_at >= $1::timestamp"

# 自引用外键的表必须保证父行先写入
ORDER_SUFFIX = {
    "session_resources": " ORDER BY parent_resource_id IS NOT NULL, updated_at",
}


def _conn_kwargs(url: str, **extra):
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    if not parsed.hostname:
        raise SystemExit(f"invalid database url: {url}")
    return dict(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=(parsed.path or "/").lstrip("/"),
        **extra,
    )


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _src_url() -> str:
    url = os.getenv("SRC_DATABASE_URL", "").strip()
    if url:
        return url
    _load_env_file(HERE.parent.parent / "backend" / ".env")
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("SRC_DATABASE_URL is required")
    return url


def _dst_url() -> str:
    url = os.getenv("SESSION_DATABASE_URL", "").strip()
    if url:
        return url
    _load_env_file(HERE / ".env")
    pwd = os.getenv("LOCAL_PG_PASSWORD", "")
    if not pwd:
        raise SystemExit("SESSION_DATABASE_URL or deploy/postgres/.env is required")
    return (f"postgresql://{os.getenv('LOCAL_PG_USER', 'suyuan')}:{pwd}@127.0.0.1:"
            f"{os.getenv('LOCAL_PG_PORT', '5433')}/{os.getenv('LOCAL_PG_DB', 'suyuan_app')}")


def _scope_where(table: str, cfg: dict) -> str | None:
    scope = cfg.get("scope")
    if scope == "all":
        return None
    if scope == "ts":
        return f"{cfg['scope_col']} >= $1::timestamp"
    if scope == "session":
        return f"session_id IN ({ACTIVE_SESSIONS})"
    return None


async def _cols(conn, table):
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=$1 ORDER BY ordinal_position", table)
    return [r["column_name"] for r in rows]


async def _upsert(dst, table, cols, rows):
    if not rows:
        return
    key = TABLES[table]["key"]
    col_list = ", ".join(cols)
    placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != key)
    sql = (f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
           f"ON CONFLICT ({key}) DO UPDATE SET {updates}")
    await dst.executemany(sql, [tuple(r) for r in rows])


async def _fix_sequences(dst):
    for table in ("sessions", "session_messages"):
        seq = await dst.fetchval("SELECT pg_get_serial_sequence($1, 'id')", table)
        if seq:
            await dst.execute(
                f"SELECT setval('{seq}', GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), 1))")


async def cmd_recent(src, dst, days, tables):
    cutoff = datetime.utcnow() - timedelta(days=days)
    await dst.execute(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
    for table in tables:
        cfg = TABLES[table]
        cols = await _cols(dst, table)
        where = _scope_where(table, cfg)
        order = ORDER_SUFFIX.get(table, "")
        sql = f"SELECT {', '.join(cols)} FROM {table}"
        rows = await src.fetch(f"{sql} WHERE {where}{order}", cutoff) if where else await src.fetch(f"{sql}{order}")
        if rows:
            await dst.copy_records_to_table(table, records=rows, columns=cols)
        print(f"{table}: {len(rows)} rows", flush=True)
    await _fix_sequences(dst)


async def cmd_delta(src, dst, since, tables):
    for table in tables:
        cfg = TABLES[table]
        cols = await _cols(dst, table)
        col_list = ", ".join(cols)
        if cfg["mode"] == "id":
            local_max = await dst.fetchval(f"SELECT MAX({cfg['key']}) FROM {table}")
            order = ORDER_SUFFIX.get(table, "")
            rows = await src.fetch(
                f"SELECT {col_list} FROM {table} WHERE {cfg['key']} > $1{order}", local_max) \
                if local_max is not None else await src.fetch(f"SELECT {col_list} FROM {table}{order}")
            if rows:
                await dst.copy_records_to_table(table, records=rows, columns=cols)
            print(f"{table}: +{len(rows)} rows", flush=True)
        elif cfg["mode"] == "scope":
            rows = await src.fetch(
                f"SELECT {col_list} FROM {table} WHERE {_scope_where(table, cfg)}"
                f"{ORDER_SUFFIX.get(table, '')}", since)
            await _upsert(dst, table, cols, rows)
            print(f"{table}: upserted {len(rows)} rows", flush=True)
        elif cfg["mode"] == "ts":
            rows = await src.fetch(
                f"SELECT {col_list} FROM {table} WHERE {cfg['time_col']} > $1::timestamp"
                f"{ORDER_SUFFIX.get(table, '')}", since)
            await _upsert(dst, table, cols, rows)
            print(f"{table}: upserted {len(rows)} rows", flush=True)
        else:  # all
            rows = await src.fetch(f"SELECT {col_list} FROM {table}{ORDER_SUFFIX.get(table, '')}")
            await _upsert(dst, table, cols, rows)
            print(f"{table}: upserted {len(rows)} rows", flush=True)
    await _fix_sequences(dst)


async def cmd_history(src, dst, before, tables):
    """回补 before 之前创建的历史会话及其关联数据（每批 200 个会话）。"""
    scanned = 0
    while True:
        sessions = await src.fetch(
            "SELECT session_id FROM sessions WHERE created_at < $1::timestamp "
            "ORDER BY created_at LIMIT 200 OFFSET $2", before, scanned)
        if not sessions:
            break
        ids = [r["session_id"] for r in sessions]
        local = await dst.fetch(
            "SELECT session_id FROM sessions WHERE session_id = ANY($1::text[])", ids)
        missing = [s for s in ids if s not in {r["session_id"] for r in local}]
        if missing:
            for table in tables:
                if table == "scheduled_task_executions":
                    cols = await _cols(dst, table)
                    rows = await src.fetch(
                        f"SELECT {', '.join(cols)} FROM {table} WHERE session_id = ANY($1::text[])"
                        f"{ORDER_SUFFIX.get(table, '')}", missing)
                elif table == "drawio_board_versions":
                    cols = await _cols(dst, table)
                    rows = await src.fetch(
                        f"SELECT {', '.join(cols)} FROM {table} WHERE board_id IN "
                        "(SELECT id FROM drawio_boards WHERE session_id = ANY($1::text[]))", missing)
                elif "session_id" in await _cols(dst, table):
                    cols = await _cols(dst, table)
                    rows = await src.fetch(
                        f"SELECT {', '.join(cols)} FROM {table} WHERE session_id = ANY($1::text[])"
                        f"{ORDER_SUFFIX.get(table, '')}", missing)
                else:
                    continue  # 非会话维度的表已在 recent 阶段全量迁移
                await _upsert(dst, table, cols, rows)
                print(f"{table}: +{len(rows)} rows", flush=True)
        scanned += len(sessions)
        print(f"history progress: {scanned} sessions scanned", flush=True)
    await _fix_sequences(dst)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    p_recent = sub.add_parser("recent")
    p_recent.add_argument("--days", type=int, default=7)
    p_delta = sub.add_parser("delta")
    p_delta.add_argument("--since", required=True)
    p_history = sub.add_parser("history")
    p_history.add_argument("--before", required=True)
    for p in (p_recent, p_delta, p_history):
        p.add_argument("--tables", default="", help="逗号分隔，默认全部；顺序须保持 sessions 在前")
    args = parser.parse_args()

    tables = [t.strip() for t in args.tables.split(",") if t.strip()] or list(TABLES)
    unknown = [t for t in tables if t not in TABLES]
    if unknown:
        raise SystemExit(f"unknown tables: {unknown}")

    src = await asyncpg.connect(**_conn_kwargs(_src_url(), statement_cache_size=0, timeout=600))
    dst = await asyncpg.connect(**_conn_kwargs(_dst_url(), statement_cache_size=0))
    try:
        if args.mode == "recent":
            await cmd_recent(src, dst, args.days, tables)
        elif args.mode == "delta":
            await cmd_delta(src, dst, datetime.fromisoformat(args.since), tables)
        else:
            await cmd_history(src, dst, datetime.fromisoformat(args.before), tables)
    finally:
        await src.close()
        await dst.close()
    print("done", flush=True)


if __name__ == "__main__":
    if sys.version_info < (3, 9):
        raise SystemExit("python 3.9+ required")
    asyncio.run(main())

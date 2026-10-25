# -*- coding: utf-8 -*-
"""盘点：同步进 guangdong_ods 的表里，Agent 到底能查哪些、不能查哪些。

不变式（由 dq_check 每日校验）：**同步的数据不允许 Agent 查不到**。
主契约（contract.txt）覆盖不到的表，必须落在 ods_contract.txt 兜底白名单里。

用法: PYTHONPATH=backend python projects/guangdong/data-ops/sync/audit_ods_coverage.py
数据源优先 OPS_MART_DATABASE_URL，其次 sync_config.json target.dsn。
输出: GAP(同步但两边都够不到) / ODS-FALLBACK(走兜底通道) / MART(有主契约) 三档。
另列"库里有但 sources.yml 未声明"的表（同步与声明漂移，同样必须修）。
退出码: 存在 GAP 返回 1。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_ods_fallback_contract as ods_contract  # noqa: E402

# 库里存在但**有意**不纳入 sources.yml / 兜底白名单的表（必须登记理由）。
# 除此之外的未声明表都视为同步/声明漂移，审计 FAIL。
KNOWN_UNDECLARED = {
    # 历史停运报告主表：2019 年后停更，主契约 sec_blackoutreportdetail 已注明勿用。
    "sec_blackoutreport",
}


def _dsn() -> str:
    dsn = os.getenv("OPS_MART_DATABASE_URL", "").replace("+asyncpg", "")
    if dsn:
        return dsn
    cfg = Path(__file__).resolve().parent / "sync_config.json"
    if cfg.is_file():
        try:
            dsn = json.loads(cfg.read_text(encoding="utf-8"))["target"]["dsn"]
        except Exception:  # noqa: BLE001
            dsn = ""
    if not dsn:
        raise SystemExit("OPS_MART_DATABASE_URL / sync_config.json target.dsn 均未配置")
    return dsn


async def main() -> int:
    import asyncpg

    fallback, covered = ods_contract.fallback_tables()
    declared = set(ods_contract.synced_logical_tables())
    conn = await asyncpg.connect(_dsn())
    try:
        rows = await conn.fetch(
            """SELECT c.relname AS table_name, c.reltuples::bigint AS est_rows
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'guangdong_ods' AND c.relkind = 'r'"""
        )
        grants = await conn.fetch(
            """SELECT table_name FROM information_schema.role_table_grants
               WHERE grantee='agent_reader' AND table_schema='guangdong_ods'"""
        )
    finally:
        await conn.close()
    est = {r["table_name"]: r["est_rows"] for r in rows}
    granted = {r["table_name"] for r in grants}

    fallback_set, covered_set = set(fallback), set(covered)
    gap = sorted(declared - fallback_set - covered_set)
    undeclared = sorted((set(est) - declared) - KNOWN_UNDECLARED)
    known_undeclared = sorted((set(est) - declared) & KNOWN_UNDECLARED)

    def show(title: str, tables: list[str]) -> None:
        print(f"== {title} ({len(tables)})")
        for t in tables:
            flag = "" if t in granted else "  [agent_reader 未授权]"
            print(f"   {t:<36} rows~{est.get(t, 'n/a(未建表)')}{flag}")
        print()

    print(f"sources.yml 声明: {len(declared)} | 库里实有: {len(est)} | "
          f"主契约覆盖: {len(covered_set)} | ODS 兜底: {len(fallback_set)} | "
          f"GAP: {len(gap)} | 未声明: {len(undeclared)} | 已知排除: {len(known_undeclared)}\n")
    show("GAP: 同步了但 Agent 查不到（必须修）", gap)
    show("UNDECLARED: 库里有但 sources.yml 未声明（同步/声明漂移，必须修）", undeclared)
    show("KNOWN-EXCLUDED: 库里有但有意不接入（见 KNOWN_UNDECLARED）", known_undeclared)
    show("ODS-FALLBACK: 走原始层兜底", fallback)
    show("MART: 有主契约", covered)
    ungranted_fallback = [t for t in fallback if t in est and t not in granted]
    if ungranted_fallback:
        print(f"agent_reader 缺 SELECT 授权 {len(ungranted_fallback)} 张: "
              + ", ".join(ungranted_fallback[:8])
              + "（run gen_ods_fallback_contract.py --grant）")
        return 1
    return 1 if gap or undeclared else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

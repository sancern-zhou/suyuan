# -*- coding: utf-8 -*-
"""Generate passthrough dbt models for ODS tables that have no mart model yet.

背景（2026-11-09 组分站审核复盘）：组分网 78 张 sup_rf_* 表单表全部同步进了
guangdong_ods，但 guangdong_mart 只建模了 7 张，导致审核取数时大量工单被判
"无表单"，组分站专属规则（OCEC/NH3/GAC/Chromatotec 等）无法生效。

约定（与既有 sup_rf_deviceflowcheck.sql 一致）：
  - 一行一文件的纯透传模型：select 全部列, now()::timestamp as refreshed_at
    from {{ source('guangdong_ods', '<table>') }}；
  - 列名与 ODS 完全一致（源列名小写），不做任何加工——审核引擎在 Python 侧
    做大写化与档案匹配，mart 层只负责"可查、可授权、有刷新戳"；
  - id 唯一索引 + GRANT agent_reader（与既有模型同款 post_hook）。

不做的事：不改列名、不做过滤、不 join。各分表头列结构并不统一（78 张里
workingordercode 缺 3 张、updatetime 缺 15 张），因此必须一表一文件、按各自
实际列生成，不能合并成一个 union 模型。

用法:
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_passthrough_models.py --dry-run
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_passthrough_models.py
  PYTHONPATH=backend python projects/guangdong/data-ops/sync/gen_passthrough_models.py --prefix sup_rf_
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DBT_DIR = Path(__file__).resolve().parent.parent / "dbt"
MODELS_DIR = DBT_DIR / "models"

HEADER = '''{{{{ config(
    indexes=[
        {{'columns': ['id'], 'unique': True}},
        {{'columns': ['workingordercode']}},
    ],
    post_hook=[
        "GRANT SELECT ON {{{{ this }}}} TO agent_reader",
    ],
) }}}}

-- {table}：组分网/业务表同步透传层（源 dbo.{source_table}；ops_audit 本地取数依赖）。
-- 列名与 ODS 一致（源列名小写）。由 sync/gen_passthrough_models.py 生成。
select
{columns}
    now()::timestamp         as refreshed_at
from {{{{ source('guangdong_ods', '{table}') }}}}
'''

# 这些列在部分源表里缺失，逐表按实际列生成，不硬编码。


# 审核取数按 workingordercode 过滤表单，缺该列的表无法被 ops_audit 消费，
# 建模出来只会多一张空跑的表（查询必然抛 "column does not exist"），因此跳过。
REQUIRED_COLUMN = "workingordercode"


def _connect():
    import psycopg2

    from dotenv import load_dotenv

    backend_root = Path(__file__).resolve().parents[4] / "backend"
    for env_name in (".env.guangdong", ".env"):
        candidate = backend_root / env_name
        if candidate.exists():
            load_dotenv(candidate, override=False)

    dsn = os.getenv("OPS_MART_DATABASE_URL")
    if not dsn:
        raise SystemExit("OPS_MART_DATABASE_URL 未配置，无法读取 ODS 表结构")
    return psycopg2.connect(dsn)


def _ods_tables(cur, prefix: str) -> list[str]:
    cur.execute(
        """select table_name from information_schema.tables
           where table_schema = 'guangdong_ods' and table_name like %s
           order by table_name""",
        (f"{prefix}%",),
    )
    return [row[0] for row in cur.fetchall()]


def _mart_tables(cur) -> set[str]:
    cur.execute(
        "select table_name from information_schema.tables where table_schema = 'guangdong_mart'"
    )
    return {row[0] for row in cur.fetchall()}


def _columns(cur, table: str) -> list[str]:
    cur.execute(
        """select column_name from information_schema.columns
           where table_schema = 'guangdong_ods' and table_name = %s
           order by ordinal_position""",
        (table,),
    )
    return [row[0] for row in cur.fetchall()]


def _source_table_name(table: str) -> str:
    """sup_rf_nh3calibration -> Sup_RF_NH3Calibration（仅用于注释，尽力还原）。"""
    return table


def build_model_sql(table: str, columns: list[str]) -> str:
    body = ",\n".join(f"    {column}" for column in columns)
    return HEADER.format(
        table=table,
        source_table=_source_table_name(table),
        columns=body + ",",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="sup_rf_", help="ODS 表名前缀（默认 sup_rf_）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将生成的模型，不写文件")
    args = parser.parse_args()

    conn = _connect()
    try:
        with conn.cursor() as cur:
            ods = _ods_tables(cur, args.prefix)
            mart = _mart_tables(cur)
            missing = [table for table in ods if table not in mart]

            if not missing:
                print(f"所有 {len(ods)} 张 {args.prefix}* 表均已建模，无需生成。")
                return 0

            print(f"ODS {args.prefix}* 共 {len(ods)} 张，已建模 {len(ods) - len(missing)} 张，待生成 {len(missing)} 张。")
            skipped: list[tuple[str, str]] = []
            written = 0
            for table in missing:
                columns = _columns(cur, table)
                if not columns:
                    skipped.append((table, "无列信息"))
                    continue
                if REQUIRED_COLUMN not in columns:
                    skipped.append((table, f"缺少 {REQUIRED_COLUMN} 列，审核取数无法按工单过滤"))
                    continue
                sql = build_model_sql(table, columns)
                target = MODELS_DIR / f"{table}.sql"
                if args.dry_run:
                    print(f"  WOULD WRITE {target.name} ({len(columns)} 列)")
                else:
                    target.write_text(sql, encoding="utf-8")
                    print(f"  WROTE {target.name} ({len(columns)} 列)")
                written += 1

            if skipped:
                print()
                print(f"跳过 {len(skipped)} 张（不可被审核取数消费）：")
                for table, reason in skipped:
                    print(f"  SKIP {table}: {reason}")
            print()
            print(f"生成 {written} 张透传模型。")
    finally:
        conn.close()

    print()
    print("下一步：")
    print("  1) 在 dbt/dbt_project.yml 的 models.guangdong_marts 下补 tag（如 +tags: [\"daily\"]）")
    print("  2) 运行 dbt build --select <表名> 物化")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Add independent tender query columns and backfill saved facts, transactionally.

Default is a read-only preview; --apply performs DDL/backfill. No API/LLM calls.
"""
import argparse
import json
import pyodbc

from config.settings import settings
from app.services.tenders.columns import QUERY_COLUMNS, query_column_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    conn = pyodbc.connect(settings.sqlserver_connection_string, timeout=20)
    conn.timeout = 60
    try:
        cur = conn.cursor()
        cur.execute("SET LOCK_TIMEOUT 10000")
        cur.execute("SELECT name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.tender_notices')")
        existing = {r[0] for r in cur.fetchall()}
        if not existing:
            raise RuntimeError("dbo.tender_notices is missing")
        missing = {k:v for k,v in QUERY_COLUMNS.items() if k not in existing}
        cur.execute("""SELECT id,extraction_meta_json FROM dbo.tender_notices
            WHERE ISJSON(extraction_meta_json)=1
            AND JSON_QUERY(extraction_meta_json,'$.classification') IS NOT NULL""")
        rows = cur.fetchall()
        prepared = [(id,query_column_values(json.loads(meta)["classification"])) for id,meta in rows]
        if args.apply:
            for name,sql_type in missing.items():
                cur.execute(f"ALTER TABLE dbo.tender_notices ADD [{name}] {sql_type} NULL")
            assignments = ", ".join(f"[{k}]=?" for k in QUERY_COLUMNS)
            for id,values in prepared:
                cur.execute(f"UPDATE dbo.tender_notices SET {assignments} WHERE id=?",values+(id,))
                if cur.rowcount != 1:
                    raise RuntimeError(f"Unexpected backfill count for {id}")
            indexes = {
                "IX_tender_notices_bid_id": "(bid_id) WHERE bid_id IS NOT NULL",
                "IX_tender_notices_business_stage_date": "(business_type,notice_stage,publish_date)",
                "IX_tender_notices_region": "(province,city,county)",
            }
            for name,definition in indexes.items():
                cur.execute("SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.tender_notices') AND name=?",name)
                if not cur.fetchone():
                    cur.execute(f"CREATE INDEX [{name}] ON dbo.tender_notices {definition}")
            # Read back every projected value, including array order and nulls.
            columns = ",".join(f"[{k}]" for k in QUERY_COLUMNS)
            for id,values in prepared:
                cur.execute(f"SELECT {columns} FROM dbo.tender_notices WHERE id=?",id)
                saved=cur.fetchone()
                if any(actual != expected for actual,expected in zip(saved,values)):
                    raise RuntimeError(f"Backfill verification failed for {id}")
            conn.commit()
        else:
            conn.rollback()
        print(json.dumps(dict(applied=args.apply,added_columns=missing,backfilled_records=len(prepared),
                              verified=args.apply),ensure_ascii=False))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

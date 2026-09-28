"""Transactionally merge the content table; abort on orphans or unequal text."""
import argparse
import json

import pyodbc
from config.settings import settings


COLUMNS = {
    "raw_content": "nvarchar(max)",
    "detail_json": "nvarchar(max)",
    "attachment_urls_json": "nvarchar(max)",
    "detail_fetched_at": "datetime2",
    "detail_cost_units": "decimal(18,4)",
    "content_created_at": "datetime2",
    "content_updated_at": "datetime2",
}


def migrate(apply=False):
    conn = pyodbc.connect(settings.sqlserver_connection_string, timeout=20)
    conn.timeout = 60
    try:
        cur = conn.cursor()
        cur.execute("SET XACT_ABORT ON; SET LOCK_TIMEOUT 10000")
        cur.execute("SELECT name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.tender_notices')")
        existing = {r[0] for r in cur.fetchall()}
        if not existing:
            raise RuntimeError("tender_notices does not exist")
        cur.execute("SELECT OBJECT_ID('dbo.tender_notice_contents','U')")
        has_old = cur.fetchone()[0] is not None
        count = 0
        if has_old:
            cur.execute("SELECT COUNT(*) FROM dbo.tender_notice_contents WITH (TABLOCKX,HOLDLOCK)")
            count = cur.fetchone()[0]
            cur.execute("""SELECT COUNT(*) FROM dbo.tender_notice_contents c
                LEFT JOIN dbo.tender_notices n WITH (UPDLOCK,HOLDLOCK) ON n.url=c.url WHERE n.id IS NULL""")
            if cur.fetchone()[0]:
                raise RuntimeError("Unmatched content rows; refusing to drop table")
        if apply:
            for name, kind in COLUMNS.items():
                if name not in existing:
                    cur.execute(f"ALTER TABLE dbo.tender_notices ADD [{name}] {kind} NULL")
            if has_old:
                cur.execute("""UPDATE n SET raw_content=c.raw_content,
                    content_created_at=c.created_at,content_updated_at=c.updated_at
                    FROM dbo.tender_notices n JOIN dbo.tender_notice_contents c ON c.url=n.url
                    WHERE n.detail_fetched_at IS NULL""")
                cur.execute("""SELECT COUNT(*) FROM dbo.tender_notice_contents c
                    JOIN dbo.tender_notices n ON n.url=c.url
                    WHERE n.detail_fetched_at IS NULL AND (
                    (n.raw_content IS NULL AND c.raw_content IS NOT NULL) OR
                    (n.raw_content IS NOT NULL AND c.raw_content IS NULL) OR
                    DATALENGTH(n.raw_content)<>DATALENGTH(c.raw_content) OR
                    n.raw_content COLLATE Latin1_General_100_BIN2<>c.raw_content COLLATE Latin1_General_100_BIN2)""")
                if cur.fetchone()[0]:
                    raise RuntimeError("Content mismatch; transaction rolled back")
                cur.execute("DROP TABLE dbo.tender_notice_contents")
            # A view holds no data. It keeps already-running old workers compatible
            # while all new code reads and writes the single physical notice table.
            cur.execute("""CREATE OR ALTER VIEW dbo.tender_notice_contents AS
                SELECT id,url,raw_content,content_created_at AS created_at,
                    content_updated_at AS updated_at FROM dbo.tender_notices""")
            cur.execute("""CREATE OR ALTER TRIGGER dbo.tr_tender_contents_compat_update
                ON dbo.tender_notice_contents INSTEAD OF UPDATE AS
                BEGIN
                    SET NOCOUNT ON;
                    UPDATE n SET raw_content=i.raw_content,content_updated_at=i.updated_at
                    FROM dbo.tender_notices n JOIN inserted i ON i.id=n.id
                    WHERE n.detail_fetched_at IS NULL;
                END""")
            conn.commit()
        else:
            conn.rollback()
        return dict(applied=apply,content_rows=count,old_table_present_before=has_old,
                    added_columns=[k for k in COLUMNS if k not in existing],verified=apply)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    print(json.dumps(migrate(parser.parse_args().apply), ensure_ascii=False))

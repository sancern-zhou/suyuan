"""Normalize an explicitly dated API batch using stored list facts, no API/LLM calls."""
import argparse
import json
from datetime import date

import pyodbc
from config.settings import settings
from app.services.tenders.models import NoticeType, TenderCandidate, TenderNotice
from app.services.tenders.sources.zhiliao_ai import apply_list_fields
from app.services.tenders.taxonomy import legacy_category_from_classification
from app.services.tenders.columns import QUERY_COLUMNS, query_column_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    conn = pyodbc.connect(settings.sqlserver_connection_string, timeout=20)
    conn.timeout = 60
    changes = []
    try:
        cur = conn.cursor()
        cur.execute("""SELECT n.id,n.title,n.url,n.notice_type,n.publish_date,n.summary,n.project_category,
            n.budget_amount,n.budget_amount_wan_yuan,n.extraction_meta_json,c.metadata_json
            FROM tender_notices n JOIN tender_candidates c ON n.url=c.url
            WHERE c.source='zhiliao_ai' AND c.publish_date=? AND n.publish_date=? ORDER BY n.id""", args.date,args.date)
        for id,title,url,kind,pub,summary,category,budget,budget_wan,meta,source in cur.fetchall():
            extraction_meta = json.loads(meta)
            classification = extraction_meta["classification"]
            candidate = TenderCandidate(title=title,url=url,source="zhiliao_ai",publish_date=pub,
                                        metadata=json.loads(source))
            notice = TenderNotice(title=title,url=url,notice_type=NoticeType(kind),raw_content="",
                                  classification=classification)
            apply_list_fields(notice,candidate)
            new_category = legacy_category_from_classification(classification,title)
            classification["legacy_category_source"] = "business_type_mapping"
            classification["validation_version"] = "list-facts-v2"
            extraction_meta["classification"] = classification
            changes.append(dict(id=id,title=title,old_category=category,new_category=new_category,
                                old_summary=summary,new_summary=notice.summary,
                                old_budget=budget,old_budget_wan=budget_wan,
                                classification_status=classification["classification_status"]))
            if args.apply:
                cur.execute("""UPDATE tender_notices SET summary=?,project_category=?,budget_amount=NULL,
                    budget_amount_wan_yuan=NULL,extraction_meta_json=?,updated_at=sysdatetime()
                    WHERE id=? AND publish_date=?""",notice.summary,new_category,
                    json.dumps(extraction_meta,ensure_ascii=False),id,args.date)
                if cur.rowcount != 1:
                    raise RuntimeError(f"Unexpected update count for notice {id}")
                assignments = ", ".join(f"[{k}]=?" for k in QUERY_COLUMNS)
                cur.execute(f"UPDATE tender_notices SET {assignments} WHERE id=?",
                            query_column_values(classification)+(id,))
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print("AUDIT_JSON=" + json.dumps(dict(date=args.date,applied=args.apply,changes=changes),ensure_ascii=False,default=str))


if __name__ == "__main__":
    main()

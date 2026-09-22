"""Read-only checks of the retained Zhiliao classification records."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from decimal import Decimal
import json

import pyodbc
from config.settings import settings
from app.services.tenders.taxonomy import BUSINESS_TYPES, CONTENT_TAGS


def audit(target_date):
    conn = pyodbc.connect(settings.sqlserver_connection_string, timeout=20)
    conn.timeout = 60
    try:
        cur = conn.cursor()
        cur.execute("""SELECT c.title,c.url,c.publish_date,c.metadata_json,c.filter_status,
            n.id,n.title,n.publish_date,n.notice_type,n.purchaser,n.winning_bidder,
            n.winning_amount_wan_yuan,n.project_category,n.summary,n.extraction_meta_json,
            CASE WHEN n.raw_content IS NULL THEN 0 ELSE 1 END
            FROM tender_candidates c LEFT JOIN tender_notices n ON n.url=c.url
            WHERE c.source='zhiliao_ai' AND c.publish_date=? ORDER BY c.id""", target_date)
        records = cur.fetchall()
    finally:
        conn.close()
    failures, rows = [], []
    for record in records:
        title,url,pub,metadata,status,notice_id,ntitle,npub,kind,purchaser,winner,amount,category,summary,meta,has_content = record
        errors = []
        original = json.loads(metadata or "{}")
        item = original.get("api_list_fields", {})
        classification = json.loads(meta or "{}").get("classification", {})
        tags = classification.get("content_tags", [])
        stage = classification.get("notice_stage")
        if notice_id is None: errors.append("missing_notice")
        if not has_content: errors.append("missing_content_record")
        if title != ntitle or pub != npub: errors.append("title_or_date_mismatch")
        if status != "accepted": errors.append("candidate_not_retained")
        if classification.get("business_type") not in BUSINESS_TYPES: errors.append("invalid_business_type")
        if any(t not in CONTENT_TAGS for t in tags): errors.append("invalid_content_tag")
        if any(not classification.get("tag_evidence", {}).get(t) for t in tags): errors.append("tag_without_evidence")
        if classification.get("classification_status") not in {"classified", "needs_review"}: errors.append("invalid_classification_status")
        if stage not in {"final_result", "contract"} and (winner or amount is not None): errors.append("nonfinal_has_award")
        if stage in {"candidate", "unknown", "other"} and kind == "winning_bid": errors.append("nonfinal_counted_as_winning")
        if item.get("caller_name") and purchaser != item["caller_name"]: errors.append("purchaser_mismatch")
        amounts = item.get("winner_moneys") or []
        expected_amount = None
        if stage in {"final_result", "contract"} and amounts and all(a and Decimal(str(a)) > 0 for a in amounts):
            expected_amount = (sum(Decimal(str(a)) for a in amounts) / 10000).quantize(Decimal("0.0001"))
        if amount != expected_amount: errors.append("award_amount_mismatch")
        if errors: failures.append({"id":notice_id,"title":title,"errors":errors})
        rows.append(dict(id=notice_id,bid_id=item.get("bid_id"),title=title,url=url,
            type=classification.get("business_type"),tags=tags,stage=stage,
            classification_status=classification.get("classification_status"),
            notice_type=kind,purchaser=purchaser,winner=winner,amount_wan=amount,
            summary=summary,category=category,tag_evidence=classification.get("tag_evidence"),
            environment_relevance=classification.get("environment_relevance")))
    return dict(target_date=target_date,records=len(rows),failures=failures,
        types=dict(Counter(r["type"] for r in rows)),stages=dict(Counter(r["stage"] for r in rows)),
        statuses=dict(Counter(r["classification_status"] for r in rows)),
        tags=dict(Counter(t for r in rows for t in r["tags"])),
        rows_with_no_tags=sum(not r["tags"] for r in rows),
        rows_with_winner=sum(bool(r["winner"]) for r in rows),
        rows_with_amount=sum(r["amount_wan"] is not None for r in rows),rows=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    result = audit(parser.parse_args().date)
    print("AUDIT_JSON=" + json.dumps(result,ensure_ascii=False,default=str))
    raise SystemExit(bool(result["failures"]))

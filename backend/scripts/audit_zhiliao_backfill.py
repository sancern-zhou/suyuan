"""Read-only month coverage and independent-column verification against page cache."""
import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json

import pyodbc
from config.settings import settings
from app.utils.path_config import resolve_agent_path, get_data_registry
from app.services.tenders.columns import QUERY_COLUMNS, query_column_values


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--start",type=date.fromisoformat,required=True)
    parser.add_argument("--end",type=date.fromisoformat,required=True)
    args=parser.parse_args()
    config=json.loads(resolve_agent_path("backend/app/services/tenders/zhiliao_strategy.json").read_text())
    folder=get_data_registry() / "tenders/backfills" / f"{args.start}_{args.end}_{config['strategy_version']}"
    expected={}
    pages=[]
    routes=defaultdict(lambda:dict(ids=set(),totals=set(),pages=set(),raw=0))
    for path in folder.glob("*.json"):
        entry=json.loads(path.read_text())
        if "payload" not in entry:
            continue
        data=entry.get("data") or {}
        route="main" if entry["endpoint"]=="/search_bids" else ("agent" if entry["payload"]["match_modes"]==["caller"] else "pollutants")
        routes[route]["totals"].add(data.get("total"))
        routes[route]["pages"].add(entry["payload"]["page"])
        routes[route]["raw"]+=len(data.get("items") or [])
        pages.append(dict(endpoint=entry["endpoint"],page=entry["payload"]["page"],
                          total=data.get("total"),returned=len(data.get("items") or []),cost=entry["meta"].get("cost_units",0)))
        for item in data.get("items") or []:
            expected[item["bid_id"]]=item
            routes[route]["ids"].add(item["bid_id"])
    conn=pyodbc.connect(settings.sqlserver_connection_string,timeout=20)
    conn.timeout=60
    fields=",".join(f"n.[{k}]" for k in QUERY_COLUMNS)
    try:
        cur=conn.cursor()
        cur.execute(f"""SELECT n.id,n.publish_date,n.extraction_meta_json,{fields},n.winning_amount_wan_yuan
             FROM tender_notices n JOIN tender_candidates c ON c.url=n.url
             WHERE c.source='zhiliao_ai' AND c.publish_date>=? AND c.publish_date<=?""",args.start,args.end)
        rows=cur.fetchall()
        cur.execute("""SELECT c.metadata_json,c.filter_reason,c.decision_source FROM tender_candidates c
             LEFT JOIN tender_notices n ON n.url=c.url
             WHERE c.source='zhiliao_ai' AND c.publish_date>=? AND c.publish_date<=?
             AND c.filter_status='rejected' AND c.decision_source IN ('rules','llm_business_filter') AND n.id IS NULL""",args.start,args.end)
        excluded={}
        for metadata,reason,source in cur.fetchall():
            bid_id=json.loads(metadata or '{}').get('zhiliao_ai_bid_id')
            accepted_exclusion = (
                source == 'rules' and config.get('enable_business_prefilter', False)
                and (reason or '').startswith('规则预过滤:')
            ) or (
                source == 'llm_business_filter' and config.get('enable_llm_business_filter', False)
                and (reason or '').startswith('LLM业务排除:')
            )
            if bid_id in expected and accepted_exclusion:
                excluded[bid_id]=reason
        cur.execute("""SELECT COUNT(*) FROM tender_candidates c LEFT JOIN tender_notices n ON n.url=c.url
             WHERE c.source='zhiliao_ai' AND c.publish_date>=? AND c.publish_date<=? AND n.id IS NULL""",args.start,args.end)
        missing_notices=cur.fetchone()[0]-len(excluded)
        cur.execute("""SELECT COUNT(*) FROM tender_notices n JOIN tender_candidates c ON c.url=n.url
             WHERE c.source='zhiliao_ai' AND c.publish_date>=? AND c.publish_date<=? AND n.raw_content IS NULL""",args.start,args.end)
        missing_contents=cur.fetchone()[0]
        cur.execute("""SELECT COUNT(*) FROM tender_notices n JOIN tender_candidates c ON c.url=n.url
             WHERE c.source='zhiliao_ai' AND c.publish_date>=? AND c.publish_date<=?
             AND n.notice_stage NOT IN ('final_result','contract')
             AND (n.winning_bidder IS NOT NULL OR n.winning_amount_wan_yuan IS NOT NULL)""",args.start,args.end)
        nonfinal_awards=cur.fetchone()[0]
    finally:
        conn.close()
    found=set();errors=[];types=Counter();statuses=Counter();stages=Counter();saved_dates=Counter()
    for row in rows:
        classification=json.loads(row[2])["classification"]
        actual=dict(zip(QUERY_COLUMNS,row[3:]))
        found.add(actual["bid_id"])
        wanted=query_column_values(classification)
        differences=[k for k,a,b in zip(QUERY_COLUMNS,row[3:],wanted) if a!=b]
        item=expected.get(actual["bid_id"])
        if item is None or str(row[1])!=item["pub_time"][:10]:
            differences.append("cache_id_or_date")
        amounts=(item or {}).get("winner_moneys") or []
        amount=None
        if actual["notice_stage"] in {"final_result","contract"} and amounts and all(v and Decimal(str(v))>0 for v in amounts):
            amount=(sum(Decimal(str(v)) for v in amounts)/10000).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP)
        if row[-1]!=amount:
            differences.append("verified_award_amount")
        if differences:errors.append(dict(id=row[0],fields=differences))
        types[actual["business_type"]]+=1;statuses[actual["classification_status"]]+=1;stages[actual["notice_stage"]]+=1
        saved_dates[str(row[1])]+=1
    expected_dates=Counter(i["pub_time"][:10] for i in expected.values())
    route_coverage={k:dict(unique=len(v["ids"]),raw=v["raw"],advertised=sorted(v["totals"]),pages=sorted(v["pages"])) for k,v in routes.items()}
    incomplete_routes=[k for k,v in routes.items() if v["totals"]!={len(v["ids"])} or v["pages"]!=set(range(1,max(v["pages"])+1))]
    days=[];day=args.start
    while day<=args.end:
        days.append(dict(date=str(day),expected=expected_dates[str(day)],saved=saved_dates[str(day)]))
        day+=timedelta(days=1)
    result=dict(start=args.start,end=args.end,cached_unique=len(expected),saved=len(rows),
                missing_ids=sorted(set(expected)-found-set(excluded)),unexpected_ids=sorted(found-set(expected)),
                filtered_out=len(excluded),filtered_reasons=dict(Counter(excluded.values())),
                duplicate_bid_ids=len(rows)-len(found),missing_notices=missing_notices,missing_contents=missing_contents,
                nonfinal_awards=nonfinal_awards,column_errors=errors,types=dict(types),statuses=dict(statuses),
                stages=dict(stages),days=days,pages=pages,route_coverage=route_coverage,incomplete_routes=incomplete_routes,
                original_search_cost=sum(p["cost"] for p in pages))
    print("AUDIT_JSON="+json.dumps(result,ensure_ascii=False,default=str))
    raise SystemExit(bool(result["missing_ids"] or result["unexpected_ids"] or errors or missing_notices or missing_contents or nonfinal_awards or result["duplicate_bid_ids"] or incomplete_routes))


if __name__=="__main__":
    main()

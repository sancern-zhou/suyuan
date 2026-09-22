"""Complete a dated API backfill with durable page cache and per-day SQL runs.

Runtime cache contains paid API data, never credentials. Re-execution reuses
successful pages and the repository's idempotent candidate/notice writes.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
import os

import httpx

from app.fetchers.tenders.tender_information_fetcher import TenderInformationFetcher
from app.services.tenders.models import NoticeType, PipelineRunResult
from app.services.tenders.pipeline import TenderPipeline
from app.services.tenders.repository import SQLServerTenderRepository
from app.services.tenders.sources.zhiliao_ai import ZhiliaoAiClient
from app.services.tenders.batch_classification import BatchClassificationClient
from app.utils.path_config import resolve_agent_path, format_agent_path, get_data_registry


def persist(path, value):
    """Atomically checkpoint generated runtime data (not source files)."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(path)


class CachedClient(ZhiliaoAiClient):
    def __init__(self, cache):
        super().__init__(timeout=60)
        self.cache = cache
        self.pages = []

    async def _post(self, endpoint, payload):
        key = hashlib.sha256(json.dumps([endpoint,payload],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        path = self.cache / (key + ".json")
        if path.exists():
            record=json.loads(path.read_text(encoding="utf-8"))
            data=record["data"]
            cached=True
        else:
            data=await super()._post(endpoint,payload)
            record=dict(endpoint=endpoint,payload=payload,data=data,meta=self.request_audit[-1])
            persist(path,record)
            cached=False
        self.pages.append(dict(endpoint=endpoint,page=payload.get("page"),total=(data or {}).get("total"),
                               returned=len((data or {}).get("items") or []),cached=cached,meta=record["meta"]))
        print("PAGE="+json.dumps(self.pages[-1],ensure_ascii=False),flush=True)
        return data

    async def balance(self):
        r=await self._client.get(self.base_url+"/account/balance")
        r.raise_for_status()
        return r.json()["data"]["available_units"]


class ProgressRepository(SQLServerTenderRepository):
    def __init__(self):
        super().__init__()
        self.saved=0

    async def save_notice(self, notice):
        await super().save_notice(notice)
        self.saved+=1
        if self.saved % 10 == 0:
            print(f"SAVED={self.saved} LAST_DATE={notice.publish_date} LAST_TYPE={notice.classification.get('business_type')}",flush=True)


async def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",type=date.fromisoformat,required=True)
    p.add_argument("--end",type=date.fromisoformat,required=True)
    p.add_argument("--batch-size",type=int,default=1)
    args=p.parse_args()
    if args.end < args.start:
        raise ValueError("Invalid date range")
    strategy=json.loads(resolve_agent_path("backend/app/services/tenders/zhiliao_strategy.json").read_text())
    cache=get_data_registry() / "tenders" / "backfills" / f"{args.start}_{args.end}_{strategy['strategy_version']}"
    cache.mkdir(parents=True,exist_ok=True)
    lock_file=(cache / "run.lock").open("a")
    try:
        fcntl.flock(lock_file,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        raise RuntimeError("This monthly backfill is already running")
    client=CachedClient(cache)
    repo=ProgressRepository()
    summary=dict(start=args.start,end=args.end,strategy=strategy["strategy_version"],days=[],cache=format_agent_path(cache))
    try:
        summary["balance_before"]=await client.balance()
        candidates=await client.search_plan([], [NoticeType.WINNING_BID], args.start, max_pages=0,end_date=args.end)
        summary["pages"]=client.pages
        summary["search_errors"]=client.search_errors
        summary["candidates"]=len(candidates)
        summary["balance_after_search"]=await client.balance()
        persist(cache / "summary.json",summary)
        print("SEARCH_SUMMARY="+json.dumps(summary,ensure_ascii=False,default=str),flush=True)
        # Save every fetched candidate even if a later page failed.
        await repo.save_candidates(candidates)
        groups=defaultdict(list)
        for candidate in candidates:
            if candidate.publish_date is None or not args.start <= candidate.publish_date <= args.end:
                raise RuntimeError(f"Unexpected publication date: {candidate.url} {candidate.publish_date}")
            groups[candidate.publish_date].append(candidate)
        llm=TenderInformationFetcher()._default_llm()
        if args.batch_size > 1:
            llm=BatchClassificationClient(llm,args.batch_size)
        pipeline=TenderPipeline(client,repo,llm_client=llm,classification_only=True,
                               enable_business_prefilter=strategy.get("enable_business_prefilter", False),
                               enable_llm_business_filter=strategy.get("enable_llm_business_filter", False))
        day=args.start
        while day <= args.end:
            rows=groups.get(day,[])
            run_id=await repo.create_run(target_date=day,keywords=[strategy["strategy_version"],"monthly_cached_search"],notice_types=[NoticeType.WINNING_BID])
            result=PipelineRunResult(total_candidates=len(rows))
            # A successful per-day ingestion does not imply incomplete search was complete.
            result.errors.extend(client.search_errors)
            try:
                await pipeline._process_candidates(rows,result)
            except Exception as exc:
                result.errors.append(f"day ingestion failed: {exc}")
            await repo.finish_run(run_id,result)
            record=dict(date=day,run_id=run_id,total=len(rows),saved=result.saved_notices,
                        duplicates=result.duplicate_candidates,filtered_out=result.filtered_out,errors=result.errors)
            summary["days"].append(record)
            persist(cache / "summary.json",summary)
            print("DAY="+json.dumps(record,ensure_ascii=False,default=str),flush=True)
            day+=timedelta(days=1)
        summary["balance_after"]=await client.balance()
        summary["saved_this_execution"]=repo.saved
        summary["filtered_out_this_execution"]=sum(d["filtered_out"] for d in summary["days"])
        summary["api_cost_units_this_execution"]=sum(float(a.get("cost_units") or 0) for a in client.request_audit)
        summary["original_search_cost_units"]=sum(float(p["meta"].get("cost_units") or 0) for p in client.pages)
        summary["status"]="failed" if client.search_errors or any(d["errors"] for d in summary["days"]) else "complete"
        persist(cache / "summary.json",summary)
        print("COMPLETE="+json.dumps(summary,ensure_ascii=False,default=str),flush=True)
        return 1 if client.search_errors or any(d["errors"] for d in summary["days"]) else 0
    finally:
        await client.close()
        lock_file.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

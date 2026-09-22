"""Run one explicitly dated Zhiliao acquisition and audit persisted records.

Uses the real API, configured LLM and SQL repository. Prints a JSON audit;
does not change scheduler/source environment configuration.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, timedelta

import httpx
import pyodbc

from app.fetchers.tenders.tender_information_fetcher import TenderInformationFetcher
from app.services.tenders.config import TenderFetcherConfig
from app.services.tenders.models import NoticeType
from app.services.tenders.repository import SQLServerTenderRepository
from app.services.tenders.sources.zhiliao_ai import ZhiliaoAiClient
from app.utils.path_config import resolve_agent_path
from config.settings import settings


class AuditedRepository(SQLServerTenderRepository):
    run_id = None
    result = None

    async def create_run(self, **kwargs):
        self.run_id = await super().create_run(**kwargs)
        print(f"RUN_ID={self.run_id}", flush=True)
        return self.run_id

    async def save_notice(self, notice):
        await super().save_notice(notice)
        print(f"SAVED={notice.title} | {notice.classification.get('business_type')} | {notice.classification.get('classification_status')}", flush=True)

    async def finish_run(self, run_id, result):
        self.result = result
        await super().finish_run(run_id, result)


class AuditedClient(ZhiliaoAiClient):
    def __init__(self):
        super().__init__()
        self.search_responses = []

    async def _post(self, path, payload):
        data = await super()._post(path, payload)
        self.search_responses.append({"endpoint": path, "payload": payload,
                                      "meta": self.request_audit[-1],
                                      "total": (data or {}).get("total"),
                                      "returned": len((data or {}).get("items") or [])})
        return data


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    strategy = json.loads(resolve_agent_path("backend/app/services/tenders/zhiliao_strategy.json").read_text())
    repo, client = AuditedRepository(), AuditedClient()
    async def balance():
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.get(client.base_url + "/account/balance", headers={"X-API-Key": client.api_key})
            response.raise_for_status()
            return response.json()
    before = await balance()
    config = TenderFetcherConfig(keywords=strategy["routes"][0]["payload"]["keywords"],
                                 notice_types=[NoticeType.WINNING_BID], classification_only=True)
    fetcher = TenderInformationFetcher(config=config, repository_factory=lambda: repo,
                                       client_factory=lambda: client,
                                       today_factory=lambda: args.date + timedelta(days=1))
    result = await fetcher.fetch_and_store()
    after = await balance()
    conn = pyodbc.connect(settings.sqlserver_connection_string, timeout=20)
    conn.timeout = 60
    try:
        cursor = conn.cursor()
        cursor.execute("""SELECT n.id,n.title,n.url,n.notice_type,n.project_name,n.purchaser,
                         n.winning_bidder,n.winning_amount,n.winning_amount_wan_yuan,
                         n.province,n.city,n.publish_date,n.summary,n.project_category,
                         n.extraction_meta_json,c.filter_status,c.source,
                         CASE WHEN n.raw_content IS NULL THEN 0 ELSE 1 END AS has_content
                         FROM tender_notices n JOIN tender_candidates c ON n.url=c.url
                         WHERE n.publish_date=? AND c.source='zhiliao_ai' ORDER BY n.id""", args.date)
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for row in rows:
            row["extraction_meta_json"] = json.loads(row["extraction_meta_json"] or "{}")
        cursor.execute("SELECT id,status,total_candidates,saved_notices,errors_json FROM tender_fetch_runs WHERE id=?", repo.run_id)
        run = dict(zip([d[0] for d in cursor.description], cursor.fetchone()))
    finally:
        conn.close()
    print("AUDIT_JSON=" + json.dumps(dict(target_date=args.date, strategy_version=strategy["strategy_version"],
           run=run,result=result,balance_before=before,balance_after=after,
           requests=client.search_responses,rows=rows), ensure_ascii=False,default=str), flush=True)


if __name__ == "__main__":
    asyncio.run(main())

"""Read cached August titles and evaluate classification without database writes or paid detail calls."""
import asyncio
from collections import Counter
import json
import re

from app.fetchers.tenders.tender_information_fetcher import TenderInformationFetcher
from app.services.tenders.batch_classification import BatchClassificationClient
from app.services.tenders.models import TenderFilterDecision
from app.services.tenders.sources.zhiliao_ai import ZhiliaoAiClient
from app.utils.path_config import get_data_registry


async def main():
    folder = get_data_registry() / 'tenders/backfills/2026-08-01_2026-08-31_xucheng-air-agent-v4'
    items = {}
    for path in folder.glob('*.json'):
        page = json.loads(path.read_text())
        if 'payload' in page:
            for item in (page.get('data') or {}).get('items', []):
                items[item['bid_id']] = item
    # Broad sample deliberately includes protected monitoring services whose
    # titles contain engineering/office organization names.
    selected = [i for i in items.values() if re.search(
        '工程|施工|EPC|办公|家具|打印|复印|保洁|物业|食堂|脱硫|脱硝|除尘|废气处理|修复|实验室|色谱|质谱|光谱|总有机碳', i.get('title', ''), re.I)]
    llm = BatchClassificationClient(TenderInformationFetcher()._default_llm(), 5)
    source = object.__new__(ZhiliaoAiClient)
    semaphore = asyncio.Semaphore(15)
    report_path = folder / 'business_filter_evaluation.json'
    previous = json.loads(report_path.read_text()).get('results', []) if report_path.exists() else []
    completed = [r for r in previous if 'error' not in r]
    done_ids = {r['bid_id'] for r in completed}
    async def classify(item):
        async with semaphore:
            candidate = source._to_candidate(item, 'evaluation')
            notice = await asyncio.wait_for(llm.review_and_extract_notice(
                candidate, candidate.raw_list_text, TenderFilterDecision(True, 'evaluation', 0)), timeout=180)
            c = notice.classification
            evidence = c.get('exclusion_evidence', '').strip()
            rejected = bool(c.get('exclusion_category') and c.get('exclusion_confidence', 0) >= .9
                            and c.get('exclusion_reason') and len(evidence) >= 4
                            and evidence in candidate.title + '\n' + candidate.raw_list_text)
            return dict(bid_id=item['bid_id'], title=candidate.title, rejected=rejected, classification=c)
    async def checked(item):
        try:
            return await classify(item)
        except Exception as exc:
            return dict(bid_id=item['bid_id'], title=item.get('title'),
                        error=type(exc).__name__, rejected=False)
    tasks = [asyncio.create_task(checked(i)) for i in selected if i['bid_id'] not in done_ids]
    for task in asyncio.as_completed(tasks):
        completed.append(await task)
        (folder / 'business_filter_evaluation_partial.json').write_text(
            json.dumps(completed, ensure_ascii=False, indent=2))
        print(f'EVALUATED={len(completed)}/{len(selected)}', flush=True)
    results = completed
    report = dict(total_cached=len(items), evaluated=len(results),
                  rejected=sum(r['rejected'] for r in results),
                  errors=sum('error' in r for r in results),
                  categories=dict(Counter(r['classification']['exclusion_category'] for r in results if r['rejected'])),
                  scope='Broad title sample, not a full-month rejection rate', results=results)
    path = report_path
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}, ensure_ascii=False))
    print(path)


if __name__ == '__main__':
    asyncio.run(main())

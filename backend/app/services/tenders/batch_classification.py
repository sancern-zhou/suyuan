"""Small-batch list classification: shared taxonomy, no duplicate fact extraction."""
import asyncio
import json

from .categories import normalize_project_category, project_category_options
from .models import TenderNotice
from .taxonomy import classification_prompt, normalize_classification


class BatchClassificationClient:
    def __init__(self, llm, batch_size=5):
        self.llm = llm
        self.batch_size = batch_size
        self.pending = []
        self.timer = None
        self.tasks = set()

    async def review_and_extract_notice(self, candidate, detail_text, decision):
        future = asyncio.get_running_loop().create_future()
        self.pending.append((candidate, detail_text, future))
        if len(self.pending) >= self.batch_size:
            self._flush()
        elif self.timer is None:
            self.timer = asyncio.get_running_loop().call_later(0.05, self._flush)
        return await future

    def _flush(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        if not self.pending:
            return
        batch,self.pending = self.pending[:self.batch_size],self.pending[self.batch_size:]
        task=asyncio.create_task(self._classify(batch))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        if self.pending:
            self.timer=asyncio.get_running_loop().call_later(0.05,self._flush)

    async def _classify(self,batch):
        try:
            taxonomy=classification_prompt()
            prompt=dict(task="批量分类已获取公告，并按classification规则识别明确的工程治理、办公采购及实验室仪器采购，其余保留；仅输出JSON。对每条独立判断，禁止跨公告混用依据。",
                classification=taxonomy,project_category_options=project_category_options(),
                rules=["只依据列表的标题、标的物和采购人，不把缺失当作公告全文没有。",
                       "大模型服务器只是设备，不能推定智能体软件。",
                       "不抽取或推断金额、供应商、日期，这些由API结构化字段直接入库。",
                       "类型、标签、证据、阶段使用classification中的规则；不得漏掉输入项。"],
                items=[dict(index=i,title=c.title,caller=c.metadata.get("api_list_fields",{}).get("caller_name"),
                            subjects=c.metadata.get("api_list_fields",{}).get("sm_names",[]),
                            api_stage=c.metadata.get("api_list_fields",{}).get("bid_process"))
                       for i,(c,_,_) in enumerate(batch)],
                output_schema={"items":[{"index":"输入index整数",**taxonomy["output_fields"],
                                         "project_category":"project_category_options中的value"}]})
            encoded=json.dumps(prompt,ensure_ascii=False)
            if hasattr(self.llm,"entries"):
                index=await self.llm._select_entry_index()
                data=await self.llm._call_with_rate_limit_failover(index,"_json_chat",encoded)
            else:
                data=await self.llm._json_chat(encoded)
            items=data.get("items",[])
            by_index={r["index"]:r for r in items if isinstance(r,dict) and type(r.get("index")) is int}
            if len(items)!=len(batch) or set(by_index)!=set(range(len(batch))):
                raise ValueError("Batch classifier returned missing/duplicate indexes")
            for i,(candidate,detail,future) in enumerate(batch):
                row=by_index[i]
                classification=normalize_classification(row)
                relevance=row.get("environment_relevance")
                classification["environment_relevance"]=relevance if isinstance(relevance,bool) else None
                notice=TenderNotice(title=candidate.title,url=candidate.url,notice_type=candidate.notice_type,
                    raw_content=detail,project_name=candidate.title,publish_date=candidate.publish_date,
                    industry_category=normalize_project_category(row.get("project_category")),
                    environment_relevance=relevance is True,classification=classification,
                    filter_reason="保留检索结果，批量分类打标签",filter_confidence=0)
                if not future.done():
                    future.set_result(notice)
        except Exception as exc:
            for _,_,future in batch:
                if not future.done():
                    future.set_exception(exc)

import asyncio
import json
import pytest
from unittest.mock import AsyncMock
from app.services.tenders.batch_classification import BatchClassificationClient
from app.services.tenders.models import TenderCandidate,TenderFilterDecision


@pytest.mark.asyncio
async def test_batch_keeps_identity_when_model_reorders_responses():
    raw=type("LLM",(),{})()
    raw._json_chat=AsyncMock(return_value={"items":[
        {"index":1,"business_type":"设备采购","content_tags":[],
         "exclusion_category":"laboratory_instruments", "exclusion_evidence":"实验室色谱仪采购",
         "exclusion_reason":"实验室仪器购置", "exclusion_confidence":0.99},
        {"index":0,"business_type":"运维服务","content_tags":[]}]})
    llm=BatchClassificationClient(raw,2)
    candidates=[TenderCandidate(title="空气站运维",url="a"),TenderCandidate(title="设备采购",url="b")]
    result=await asyncio.gather(*(llm.review_and_extract_notice(c,c.title,TenderFilterDecision(True,"",0)) for c in candidates))
    assert [n.url for n in result]==["a","b"]
    assert [n.classification["business_type"] for n in result]==["运维服务","设备采购"]
    assert raw._json_chat.await_count==1
    assert result[1].classification["exclusion_category"] == "laboratory_instruments"
    assert result[0].classification["exclusion_category"] is None


@pytest.mark.asyncio
async def test_partial_batch_flushes_and_missing_ids_fail_instead_of_misassigning():
    raw=type("LLM",(),{})()
    raw._json_chat=AsyncMock(return_value={"items":[]})
    llm=BatchClassificationClient(raw,5)
    with pytest.raises(ValueError,match="indexes"):
        await asyncio.wait_for(llm.review_and_extract_notice(TenderCandidate(title="x",url="x"),"x",None),1)

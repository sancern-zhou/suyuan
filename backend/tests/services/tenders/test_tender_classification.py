import json
from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.tenders.llm import OpenAICompatibleTenderLLMClient
from app.services.tenders.models import NoticeType, TenderCandidate, TenderFilterDecision
from app.services.tenders.pipeline import TenderPipeline
from app.services.tenders.repository import SQLServerTenderRepository
from app.services.tenders.sources.zhiliao_ai import ZhiliaoAiClient, apply_list_fields
from app.services.tenders.models import TenderNotice
from app.services.tenders.taxonomy import normalize_classification


def candidate(title="水质监测站运维", url="https://example.test/1"):
    return TenderCandidate(title=title, url=url, source="zhiliao_ai",
                           metadata={"classification_only": True}, raw_list_text=title)


@pytest.mark.asyncio
async def test_retains_water_engineering_and_unknown_without_screening_or_paid_detail():
    rows = [candidate(), candidate("污水处理工程", "https://example.test/2"),
            candidate("未知项目", "https://example.test/3")]
    source = type("Source", (), {})()
    source.search_plan = AsyncMock(return_value=rows)
    source.fetch_detail = AsyncMock(side_effect=AssertionError("No paid details"))
    repo = type("Repo", (), {})()
    repo.save_candidates = AsyncMock(return_value={c.url: True for c in rows})
    repo.update_candidate_decisions = AsyncMock()
    repo.save_notice = AsyncMock()
    llm = type("LLM", (), {})()
    llm.review_candidates = AsyncMock(side_effect=AssertionError("No screening"))
    llm.review_and_extract_notice = AsyncMock(side_effect=RuntimeError("model unavailable"))
    result = await TenderPipeline(source, repo, llm_client=llm, classification_only=True,
                                  enable_llm_business_filter=True).run_daily(["ignored"])
    assert result.saved_notices == 3
    assert result.filtered_out == 0
    source.fetch_detail.assert_not_awaited()
    llm.review_candidates.assert_not_awaited()
    for call in repo.save_notice.await_args_list:
        assert call.args[0].classification["classification_status"] == "needs_review"


@pytest.mark.asyncio
async def test_business_prefilter_rejects_before_classification_but_keeps_unknown():
    rows = [candidate("生态环境局办公采购中标", "https://example.test/office"),
            candidate("空气站运维", "https://example.test/air"),
            candidate("未知项目", "https://example.test/unknown")]
    source = type("Source", (), {})()
    source.search_plan = AsyncMock(return_value=rows)
    source.fetch_detail = AsyncMock(side_effect=AssertionError("No paid details"))
    repo = type("Repo", (), {})()
    repo.save_candidates = AsyncMock(return_value={c.url: True for c in rows})
    repo.update_candidate_decisions = AsyncMock()
    repo.save_notice = AsyncMock()
    llm = type("LLM", (), {})()
    llm.review_candidates = AsyncMock(side_effect=AssertionError("No LLM screening"))
    llm.review_and_extract_notice = AsyncMock(side_effect=RuntimeError("model unavailable"))
    result = await TenderPipeline(source, repo, llm_client=llm, classification_only=True,
                                  enable_business_prefilter=True).run_daily(["ignored"])
    assert result.filtered_out == 1
    assert result.saved_notices == 2
    assert llm.review_and_extract_notice.await_count == 2
    assert {call.args[0].url for call in repo.save_notice.await_args_list} == {c.url for c in rows[1:]}
    decisions = dict((c.url, d) for c, d in repo.update_candidate_decisions.await_args.args[0])
    assert decisions[rows[0].url].decision_source == "rules"
    assert decisions[rows[0].url].is_relevant is False
    assert "规则预过滤:" in decisions[rows[0].url].reason
    source.fetch_detail.assert_not_awaited()
    llm.review_candidates.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("category,evidence,confidence,filtered", [
    ("engineering_remediation", "烟气脱硝设施改造工程", 0.98, True),
    ("office_procurement", "办公家具采购", 0.96, True),
    ("laboratory_instruments", "实验室色谱仪采购", 0.98, True),
    ("engineering_remediation", "未出现在输入中的证据", 0.99, False),
    ("engineering_remediation", "烟气脱硝设施改造工程", 0.7, False),
    (None, "", 0, False),
])
async def test_llm_exclusion_requires_supported_evidence(category, evidence, confidence, filtered):
    row = candidate("烟气脱硝设施改造工程及办公家具采购及实验室色谱仪采购")
    classification = normalize_classification(dict(
        business_type="其他环保业务", content_tags=[], exclusion_category=category,
        exclusion_evidence=evidence, exclusion_confidence=confidence, exclusion_reason="主要交付不属于目标业务"))
    notice = TenderNotice(title=row.title, url=row.url, notice_type=row.notice_type,
                          raw_content=row.raw_list_text, classification=classification)
    source = type("Source", (), {})()
    source.search_plan = AsyncMock(return_value=[row])
    repo = type("Repo", (), {})()
    repo.save_candidates = AsyncMock(return_value={row.url: True})
    repo.update_candidate_decisions = AsyncMock()
    repo.update_candidate_decision = AsyncMock()
    repo.save_notice = AsyncMock()
    llm = type("LLM", (), {})()
    llm.review_and_extract_notice = AsyncMock(return_value=notice)
    result = await TenderPipeline(source, repo, llm_client=llm, classification_only=True,
                                  enable_llm_business_filter=True).run_daily(["ignored"])
    assert result.filtered_out == int(filtered)
    assert result.saved_notices == int(not filtered)
    if filtered:
        assert repo.update_candidate_decision.await_args.args[1].decision_source == "llm_business_filter"


@pytest.mark.asyncio
async def test_classification_prompt_and_tags_survive_repository_serialization():
    client = object.__new__(OpenAICompatibleTenderLLMClient)
    client._json_chat = AsyncMock(return_value={
        "is_relevant": False, "environment_relevance": True,
        "business_type": "运维服务", "content_tags": ["软件运维", "预报/预警"],
        "tag_evidence": {"软件运维": "软件运维", "预报/预警": "预报预警"},
        "classification_status": "classified", "notice_stage": "final_result",
        "notice_type": "winning_bid", "project_category": "operation_maintenance",
        "industry_category": "环保行业",
    })
    row = candidate("预报预警系统软件运维")
    decision = TenderFilterDecision(True, "retained", 0)
    notice = await client.review_and_extract_notice(row, row.title, decision)
    prompt = json.loads(client._json_chat.await_args.args[0])
    assert "水、土、固废、工程治理" in prompt["task"]
    assert len(prompt["classification"]["content_tag_options"]) == 20
    assert notice.classification["business_type"] == "运维服务"
    assert notice.classification["content_tags"] == ["软件运维", "预报/预警"]
    assert notice.industry_category == "operation_maintenance"
    meta = object.__new__(SQLServerTenderRepository)._extraction_meta(notice)
    assert json.loads(json.dumps(meta))["classification"] == notice.classification


@pytest.mark.asyncio
async def test_candidate_supplier_is_not_saved_as_final_winner():
    client = object.__new__(OpenAICompatibleTenderLLMClient)
    client._json_chat = AsyncMock(return_value={
        "business_type": "运维服务", "content_tags": [], "notice_stage": "candidate",
        "notice_type": "winning_bid", "winning_bidder": "候选供应商", "winning_amount": "100万元",
    })
    row = candidate("空气站运维成交候选公示")
    notice = await client.review_and_extract_notice(row, row.title, TenderFilterDecision(True, "", 0))
    assert notice.winning_bidder is None
    assert notice.winning_amount_wan_yuan is None
    assert notice.notice_type == NoticeType.OTHER


def test_unknown_types_and_unsupported_tags_do_not_create_new_vocabulary():
    result = normalize_classification({"business_type": "瞎编", "content_tags": ["AI", "编造", "AI"],
                                       "classification_status": "classified"})
    assert result["business_type"] == "待确认"
    assert result["content_tags"] == ["AI"]
    assert result["classification_status"] == "needs_review"


@pytest.mark.parametrize("title,amounts,expected", [
    ("空气站运维中标结果", [358000, 348000], 70.6),
    ("空气站运维中标结果", [0], None),
    ("空气站运维候选公示", [100000], None),
    ("空气站运维中标更正公告", [100000], None),
])
def test_list_amounts_preserve_lots_and_never_use_budget(title, amounts, expected):
    row = candidate(title)
    row.metadata["api_list_fields"] = {"winner_moneys": amounts, "money_wan": 999,
                                       "winner_names": ["供应商"], "caller_name": "采购人"}
    notice = TenderNotice(title=title, url=row.url, notice_type=NoticeType.WINNING_BID, raw_content=title)
    apply_list_fields(notice, row)
    assert notice.winning_amount_wan_yuan == expected
    assert notice.purchaser == "采购人"
    assert notice.classification["api_winner_moneys_yuan"] == amounts


def test_generic_money_never_becomes_budget_or_summary_award():
    row = candidate("温室气体清单编制中标结果")
    row.metadata["api_list_fields"] = {"money": 850000, "money_wan": 85,
        "winner_names": ["甲", "乙"], "winner_moneys": [850000, 0]}
    notice = TenderNotice(title=row.title,url=row.url,notice_type=NoticeType.WINNING_BID,
        raw_content="",budget_amount="850000元",budget_amount_wan_yuan=85,
        summary="中标金额850000元")
    apply_list_fields(notice,row)
    assert notice.budget_amount is None
    assert notice.winning_amount_wan_yuan is None
    assert "未完整提供" in notice.summary
    assert "中标金额850000元" not in notice.summary


def test_vague_pollution_control_is_retained_for_review():
    row = candidate("花都区2026-2027年大气污染防治项目结果公告")
    row.metadata["api_list_fields"] = {"sm_names": ["大气污染防治项目"]}
    notice = TenderNotice(title=row.title,url=row.url,notice_type=NoticeType.WINNING_BID,
        raw_content="",classification={"business_type": "防控服务项目", "classification_status": "classified"})
    apply_list_fields(notice,row)
    assert notice.classification["business_type"] == "待确认"
    assert notice.classification["classification_status"] == "needs_review"


@pytest.mark.asyncio
async def test_api_plan_batches_keywords_dedupes_and_records_actual_cost():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["begin_date"] == body["end_date"] == "2026-09-18"
        assert body["bid_type"] == "中标"
        return httpx.Response(200, json={"success": True, "meta": {"cost_units": 1, "request_id": str(len(calls))},
                                       "data": {"total": 1, "items": [{"bid_id": 1, "title": "空气站运维"}]}})

    client = ZhiliaoAiClient(api_key="test")
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        rows = await client.search_plan(["a", "b"], [NoticeType.TENDER, NoticeType.WINNING_BID], date(2026, 9, 18))
        assert len(calls) == 3
        assert len(calls[0]["keywords"]) == 84
        assert len(rows) == 1
        assert len(rows[0].metadata["query_routes"]) == 3
        assert sum(r["cost_units"] for r in client.request_audit) == 3
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_api_partial_failure_keeps_paid_results_and_reports_incomplete():
    client = ZhiliaoAiClient(api_key="test", page_size=1)
    client._post = AsyncMock(side_effect=[
        {"total": 2, "items": [{"bid_id": 1, "title": "项目1"}]},
        RuntimeError("timeout"), {"total": 0, "items": []},
    ])
    try:
        rows = await client.search_plan([], [], date(2026, 9, 18), max_pages=1)
        assert len(rows) == 1
        assert any("pagination incomplete" in e for e in client.search_errors)
        assert any("timeout" in e for e in client.search_errors)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_month_window_paginates_until_complete_without_per_day_requests():
    client = ZhiliaoAiClient(api_key="test", page_size=2)
    client._post = AsyncMock(side_effect=[
        {"total":3,"items":[{"bid_id":1,"title":"甲"},{"bid_id":2,"title":"乙"}]},
        {"total":3,"items":[{"bid_id":3,"title":"丙"}]},
        {"total":0,"items":[]},{"total":0,"items":[]},
    ])
    try:
        rows=await client.search_plan([],[],date(2026,8,1),end_date=date(2026,8,31))
        assert len(rows)==3
        assert not client.search_errors
        assert client._post.await_count==4
        for call in client._post.await_args_list:
            assert call.args[1]["begin_date"]=="2026-08-01"
            assert call.args[1]["end_date"]=="2026-08-31"
        assert client._post.await_args_list[1].args[1]["page"]==2
    finally:
        await client.close()

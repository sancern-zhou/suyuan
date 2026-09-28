import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.services.tenders.detail_service import TenderDetailService
from app.tools.query.zhiliao_tender_detail.tool import ZhiliaoTenderDetailTool
from app.tools.query.execute_sql_query.tool import ExecuteTenderSQLQueryTool, TENDER_SQL_TABLES


class Cursor:
    def __init__(self, cached=None):
        self.cached = cached or ("列表",None,None,None)
        self.statements = []
        self.rowcount = 1

    def execute(self, sql, *params):
        self.statements.append((sql,params))
        return self

    def fetchone(self):
        return (0,) if "sp_getapplock" in self.statements[-1][0] else self.cached


class Connection:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


ROW = (1,123,"空气质量监测服务中标公告","https://example.com/1",None,"环境局","中标")


def test_detail_saved_with_raw_payload_and_cost():
    service = TenderDetailService()
    service._fetch = AsyncMock(return_value=({"source":"<p>完整正文</p>","attachment_urls":["https://example.com/a.pdf"]},{"cost_units":2}))
    conn,cur = Connection(),Cursor()
    result = service._resolve(conn,cur,[ROW],False)
    assert result["stored"] and result["content"] == "完整正文"
    assert result["cost_units"] == 2 and conn.commits == 1
    sql,params = cur.statements[-1]
    assert "UPDATE dbo.tender_notices" in sql
    assert json.loads(params[1])["data"]["source"] == "<p>完整正文</p>"
    assert "detail_fetched_at" in sql


def test_cached_detail_does_not_spend_again():
    service = TenderDetailService()
    service._fetch = AsyncMock(side_effect=AssertionError("must not call API"))
    result = service._resolve(Connection(),Cursor(("正文","{}","[]",datetime(2026,9,21))),[ROW],False)
    assert result["status"] == "cached" and result["cost_units"] == 0
    service._fetch.assert_not_called()


def test_ambiguity_and_legacy_do_not_spend():
    service = TenderDetailService()
    service._fetch = AsyncMock(side_effect=AssertionError("must not call API"))
    assert service._resolve(Connection(),Cursor(),[ROW,ROW],False)["status"] == "needs_selection"
    legacy = (ROW[0],None,*ROW[2:])
    assert service._resolve(Connection(),Cursor(),[legacy],False)["status"] == "legacy_source"


def test_empty_body_not_saved_or_committed():
    service = TenderDetailService()
    service._fetch = AsyncMock(return_value=({"source":"<p> </p>"},{"cost_units":2}))
    conn,cur = Connection(),Cursor()
    with pytest.raises(ValueError):
        service._resolve(conn,cur,[ROW],True)
    assert conn.commits == 0
    assert not any("UPDATE dbo.tender_notices" in sql for sql,_ in cur.statements)


def test_wrong_bid_id_is_never_saved():
    service = TenderDetailService()
    service._fetch = AsyncMock(return_value=({"bid_id":456,"source":"其他公告"},{"cost_units":1}))
    conn,cur = Connection(),Cursor()
    with pytest.raises(ValueError,match="ID"):
        service._resolve(conn,cur,[ROW],False)
    assert conn.commits == 0


@pytest.mark.asyncio
async def test_detail_api_uses_numeric_type_code():
    from app.services.tenders.sources.zhiliao_ai import ZhiliaoAiClient
    client = ZhiliaoAiClient(api_key="test")
    client._post = AsyncMock(return_value={"source":"公告正文"})
    try:
        await client.get_bid_detail(123,"中标")
        client._post.assert_awaited_once_with("/get_bid_detail",{"bid_id":123,"bid_type":2})
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_tool_validates_identity_and_hides_errors():
    service = AsyncMock()
    tool = ZhiliaoTenderDetailTool(service)
    assert not (await tool.execute(bid_id=True))["success"]
    assert not (await tool.execute(title="监测"))["success"]
    service.get.assert_not_called()
    service.get.side_effect = RuntimeError("secret connection string")
    result = await tool.execute(bid_id=123)
    assert result["status"] == "failed"
    assert result["data"]["status"] == "detail_failed"
    assert "secret" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("state,cost", [("fetched", 1), ("cached", 0)])
async def test_full_detail_survives_agent_standardization(state, cost):
    from app.agent.tool_adapter import _standardize_tool_result
    payload = dict(success=True, status=state, bid_id=513319817, title="公告",
                   content="完整正文" * 5000, details={"service": "服务要求"},
                   attachment_urls=["https://example.com/a.pdf"], stored=True, cost_units=cost)
    tool = ZhiliaoTenderDetailTool(AsyncMock(get=AsyncMock(return_value=payload)))
    result = _standardize_tool_result(tool.name, await tool.execute(bid_id=513319817), 0.1)
    assert result["success"] is True
    assert result["data"] == {k: v for k, v in payload.items() if k != "success"}
    assert len(result["data"]["content"]) == 20000


@pytest.mark.asyncio
async def test_selection_candidates_survive_agent_standardization():
    from app.agent.tool_adapter import _standardize_tool_result
    payload = dict(success=True, status="needs_selection", cost_units=0,
                   has_more=True, candidates=[{"bid_id": 123, "title": "待选择公告"}],
                   summary="请选择具体公告")
    service = AsyncMock(get=AsyncMock(return_value=payload))
    tool = ZhiliaoTenderDetailTool(service)
    result = _standardize_tool_result(tool.name, await tool.execute(title="空气质量"), 0.1)
    assert result["data"]["candidates"] == payload["candidates"]
    assert result["data"]["has_more"] is True


def test_sql_schema_uses_single_table_and_routes_details():
    description = ExecuteTenderSQLQueryTool().function_schema["description"]
    assert "tender_notice_contents" not in TENDER_SQL_TABLES
    for field in ("raw_content","detail_fetched_at","bid_id","content_tags","winner_names","money_wan","zhiliao_tender_detail"):
        assert field in description


def test_json_tag_query_allows_function_but_not_hidden_tables():
    validator = ExecuteTenderSQLQueryTool().sql_validator
    good = "SELECT TOP 10 n.title FROM tender_notices n WHERE EXISTS (SELECT 1 FROM OPENJSON(n.content_tags) t WHERE t.value=N'AI')"
    assert validator.validate(good)[0]
    assert not validator.validate("SELECT TOP 10 * FROM openjson")[0]
    assert not validator.validate("SELECT TOP 10 * FROM dbo.openjson(N'[]')")[0]
    assert not validator.validate("SELECT TOP 10 * FROM OPENJSON((SELECT secret FROM secret_table))")[0]

import json
import pytest
from decimal import Decimal
from app.services.tenders.columns import QUERY_COLUMNS, query_column_values
from app.services.tenders.models import TenderNotice, NoticeType
from app.services.tenders.repository import SQLServerTenderRepository


def test_independent_columns_preserve_lists_zero_and_raw_roles():
    c={"business_type":"运维服务","content_tags":["站点运维"],"notice_stage":"candidate",
       "source_metadata":{"api_list_fields":{"county":"奎文区","money_wan":11.8,
         "winner_names":["甲公司","乙公司"],"winner_moneys":[358000,0],
         "brand_names":[],"sm_names":["空气站运维","质控服务"],"caller_id":123}}}
    values=dict(zip(QUERY_COLUMNS,query_column_values(c)))
    assert values["county"]=="奎文区"
    assert values["money_wan"]==Decimal("11.8000")
    assert json.loads(values["winner_names"])==["甲公司","乙公司"]
    assert json.loads(values["winner_moneys"])==[358000,0]
    assert values["brand_names"]=="[]"
    assert values["winner_ids"] is None
    assert values["notice_stage"]=="candidate"
    assert json.loads(values["content_tags"])==["站点运维"]


def test_missing_api_fields_do_not_invent_values_for_legacy_sources():
    values=dict(zip(QUERY_COLUMNS,query_column_values({"business_type":"其他环保业务"})))
    assert values["business_type"]=="其他环保业务"
    assert values["winner_names"] is None
    assert values["county"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("exists", [False, True])
async def test_save_notice_writes_independent_columns_on_insert_and_update(exists):
    class Connection:
        rowcount = 1
        calls = []
        committed = False

        def cursor(self): return self
        def execute(self, sql, params):
            self.calls.append((sql,params))
            self.rowcount = int(exists) if "SET title = ?" in sql else 1
        def commit(self): self.committed = True
        def close(self): pass

    conn=Connection()
    repo=SQLServerTenderRepository()
    repo._connect=lambda:conn
    notice=TenderNotice(title="监测设备",url="https://example.test/1",
        notice_type=NoticeType.WINNING_BID,raw_content="监测设备",
        classification={"business_type":"设备采购","source_metadata":{"api_list_fields":{
            "bid_id":123,"county":"越秀区","brand_names":["品牌甲","品牌乙"],
            "winner_names":["供应商甲","供应商乙"]}}})
    await repo.save_notice(notice)
    projection=[(s,p) for s,p in conn.calls if "SET [bid_id]" in s]
    assert len(projection)==1
    values=dict(zip(QUERY_COLUMNS,projection[0][1][:-1]))
    assert values["county"]=="越秀区"
    assert json.loads(values["brand_names"])==["品牌甲","品牌乙"]
    assert projection[0][1][-1]==notice.url
    assert conn.committed

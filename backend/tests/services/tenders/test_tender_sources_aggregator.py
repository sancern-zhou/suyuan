from datetime import date, timedelta

import pytest

from app.services.tenders.models import NoticeType, TenderCandidate
from app.services.tenders.sources.aggregator import MultiSourceTenderClient
from app.services.tenders.sources import zhiliao


class FakeSource:
    def __init__(self, name, candidates=None, fail=False):
        self.name = name
        self._candidates = candidates or []
        self._fail = fail
        self.detail_calls = []
        self.closed = False

    async def search(self, keyword, notice_type, publish_date=None, max_pages=1):
        if self._fail:
            raise RuntimeError("boom")
        return [
            TenderCandidate(title=c["title"], url=c["url"], keyword=keyword)
            for c in self._candidates
        ]

    async def fetch_detail(self, candidate):
        self.detail_calls.append(candidate.url)
        return f"<html>{candidate.source}</html>"

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_aggregator_merges_sources_and_tags_origin():
    qianlima = FakeSource("qianlima", [{"title": "A公告标题", "url": "https://q/a"}])
    zhiliao_src = FakeSource(
        "zhiliaobiaoxun", [{"title": "B公告标题", "url": "https://z/b"}]
    )
    client = MultiSourceTenderClient([qianlima, zhiliao_src])

    results = await client.search("生态环境局", NoticeType.OTHER)

    assert {c.source for c in results} == {"qianlima", "zhiliaobiaoxun"}
    assert {c.url for c in results} == {"https://q/a", "https://z/b"}


@pytest.mark.asyncio
async def test_aggregator_isolates_source_failures():
    ok = FakeSource("qianlima", [{"title": "A公告标题", "url": "https://q/a"}])
    broken = FakeSource("zhiliaobiaoxun", fail=True)
    client = MultiSourceTenderClient([ok, broken])

    results = await client.search("生态环境局", NoticeType.OTHER)

    assert [c.url for c in results] == ["https://q/a"]


@pytest.mark.asyncio
async def test_aggregator_routes_detail_by_source():
    qianlima = FakeSource("qianlima", [{"title": "A公告标题", "url": "https://q/a"}])
    zhiliao_src = FakeSource(
        "zhiliaobiaoxun", [{"title": "B公告标题", "url": "https://z/b"}]
    )
    client = MultiSourceTenderClient([qianlima, zhiliao_src])
    candidate = TenderCandidate(title="B公告标题", url="https://z/b")
    candidate.source = "zhiliaobiaoxun"

    detail = await client.fetch_detail(candidate)

    assert "zhiliaobiaoxun" in detail
    assert zhiliao_src.detail_calls == ["https://z/b"]
    assert qianlima.detail_calls == []


def test_zhiliao_pure_helpers():
    assert zhiliao._clean_title("东莞<font color='red'>生态</font>环境") == "东莞生态环境"
    assert zhiliao._notice_type(1) == NoticeType.TENDER
    assert zhiliao._notice_type(2) == NoticeType.WINNING_BID
    assert zhiliao._notice_type(None) == NoticeType.OTHER
    yesterday = date.today() - timedelta(days=1)
    assert zhiliao._date_preset(yesterday) == "yesterday"
    assert zhiliao._date_preset(date.today() - timedelta(days=400)) == "aYear"
    assert zhiliao._date_preset(None) == ""

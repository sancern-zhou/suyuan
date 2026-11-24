"""生态环境部 168 城月度排名抓取器单元测试（不访问网络/数据库/视觉模型）。"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.fetchers.mee_rank168_monthly import (
    Article,
    MeeRank168MonthlyFetcher,
    build_db_rows,
    merge_slices,
    parse_list_articles,
    parse_vision_rows,
    pick_attachment_image,
    slice_image,
    validate_rows,
)


def _article(month: int = 9, has_cum: bool = True) -> Article:
    return Article(year=2026, month=month, has_cum=has_cum,
                   url=f"https://www.mee.gov.cn/ywdt/xwfb/202610/t20261026_1184641.shtml")


def _rows(count: int = 168) -> list[dict]:
    return [
        {
            "seq": i,
            "city": f"城市{i:03d}市",
            "month_ci": round(8.0 - i * 0.01, 2),
            "month_pm25": round(40.0 - i * 0.1, 1),
            "cum_ci": round(7.5 - i * 0.01, 2),
            "cum_pm25": round(38.0 - i * 0.1, 1),
        }
        for i in range(1, count + 1)
    ]


def test_parse_list_articles_extracts_matching_titles():
    html = """
    <a href="../../../ywdt/xwfb/202610/t20261026_1184641.shtml">生态环境部公布2026年9月和1—9月全国环境空气质量状况</a>
    <a href="../../../ywdt/xwfb/202609/t20260921_1168954.shtml">生态环境部公布2026年8月全国环境空气质量状况</a>
    <a href="/other/x.shtml">生态环境部公布2026年第三季度全国地表水环境质量状况</a>
    """
    articles = parse_list_articles(html)
    assert [(a.year, a.month, a.has_cum) for a in articles] == [
        (2026, 9, True), (2026, 8, False),
    ]
    assert articles[0].url == "https://www.mee.gov.cn/ywdt/xwfb/202610/t20261026_1184641.shtml"
    assert articles[0].data_month == date(2026, 9, 1)


def test_pick_attachment_image_takes_last_w020_image():
    html = (
        '<img src="./W020261026609197864842.jpg"/>'
        '<img src="W020261026609197994324.jpg"/>'
        '<img src="./W020261026609198204421.jpg"/>'
    )
    url = pick_attachment_image(html, _article().url)
    assert url == "https://www.mee.gov.cn/ywdt/xwfb/202610/W020261026609198204421.jpg"


def test_pick_attachment_image_raises_without_image():
    with pytest.raises(ValueError):
        pick_attachment_image("<div>无图</div>", _article().url)


def test_parse_vision_rows_accepts_fenced_and_plain_json():
    rows = _rows(2)
    assert parse_vision_rows(json.dumps(rows, ensure_ascii=False)) == rows
    fenced = f"识别结果：\n```json\n{json.dumps(rows, ensure_ascii=False)}\n```"
    assert parse_vision_rows(fenced) == rows


def test_merge_slices_dedupes_by_seq():
    a = _rows(3)
    b = [_rows(3)[2], {"seq": 4, "city": "城市004市", "month_ci": 1, "month_pm25": 1,
                      "cum_ci": 1, "cum_pm25": 1}]
    merged = merge_slices([a, b])
    assert [r["seq"] for r in merged] == [1, 2, 3, 4]


def test_validate_rows_passes_for_full_valid_set():
    validate_rows(_rows())


@pytest.mark.parametrize("mutate,msg", [
    (lambda r: r[:-1], "行数"),
    (lambda r: [{**r[0], "seq": 99}] + r[1:], "序号"),
    (lambda r: [{**r[0], "city": "城市001市"}, *[{**x, "city": "城市001市"} for x in r[1:]]], "重复"),
    (lambda r: [{**r[0], "month_ci": 99.0}] + r[1:], "范围"),
    (lambda r: [{**r[0], "month_pm25": None}] + r[1:], "范围"),
])
def test_validate_rows_rejects_bad_data(mutate, msg):
    with pytest.raises(ValueError, match=msg):
        validate_rows(mutate(_rows()))


def test_build_db_rows_month_and_cum_ranks():
    article = _article(month=9)
    rows = _rows(3)
    db_rows = build_db_rows(article, rows)
    assert len(db_rows) == 6
    month_rows = [r for r in db_rows if r["PeriodType"] == "month"]
    cum_rows = [r for r in db_rows if r["PeriodType"] == "cum"]
    # 附表序号=当月综合指数排名（降序）
    assert [r["CompositeIndexRank"] for r in month_rows] == [1, 2, 3]
    assert [r["Pm25Rank"] for r in month_rows] == [1, 2, 3]
    assert [r["CompositeIndexRank"] for r in cum_rows] == [1, 2, 3]
    assert all(r["PeriodEnd"] is None for r in month_rows)
    assert all(r["PeriodEnd"] == date(2026, 9, 30) for r in cum_rows)
    assert month_rows[0]["PeriodLabel"] == "9月"
    assert cum_rows[0]["PeriodLabel"] == "1-9月"
    assert month_rows[0]["SourceFile"].startswith("mee.gov.cn:")


def test_build_db_rows_pm25_ties_share_rank():
    article = _article()
    rows = _rows(3)
    rows[1]["month_pm25"] = rows[0]["month_pm25"]  # 前两名并列
    db_rows = build_db_rows(article, rows)
    month_rows = [r for r in db_rows if r["PeriodType"] == "month"]
    assert [r["Pm25Rank"] for r in month_rows] == [1, 1, 3]


def test_slice_image_produces_requested_count():
    from PIL import Image
    import io
    img = Image.new("RGB", (100, 1680), "white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    slices = slice_image(buf.getvalue(), count=6)
    assert len(slices) == 6
    for chunk in slices:
        im = Image.open(io.BytesIO(chunk))
        assert im.width == 100
        assert 200 <= im.height <= 400


def test_fetch_and_store_skips_existing_months(tmp_path: Path, monkeypatch):
    fetcher = MeeRank168MonthlyFetcher(
        archive_dir=tmp_path,
        storage=AsyncMock(),
        vision_func=AsyncMock(),
    )
    fetcher.storage.existing_months = AsyncMock(return_value={"2026-09", "2026-08"})
    fetcher.storage.save = AsyncMock()

    list_html = (
        '<a href="../../../ywdt/xwfb/202610/t20261026_1184641.shtml">'
        "生态环境部公布2026年9月和1—9月全国环境空气质量状况</a>"
        '<a href="../../../ywdt/xwfb/202609/t20260921_1168954.shtml">'
        "生态环境部公布2026年8月全国环境空气质量状况</a>"
    )

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(
        "app.fetchers.mee_rank168_monthly.httpx.AsyncClient", _FakeClient)
    monkeypatch.setattr(
        MeeRank168MonthlyFetcher, "_fetch_bytes",
        AsyncMock(return_value=list_html.encode("utf-8")))

    result = asyncio.run(fetcher.fetch_and_store())
    assert result == {"pending": 0, "processed": [], "failed": {}}
    fetcher.storage.save.assert_not_called()

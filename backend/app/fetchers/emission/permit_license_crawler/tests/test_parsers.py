from datetime import date
from pathlib import Path

from app.fetchers.emission.permit_license_crawler.detail_parser import (
    classify_current_status,
    parse_detail_page,
)
from app.fetchers.emission.permit_license_crawler.document_downloader import (
    parse_copy_viewer,
)
from app.fetchers.emission.permit_license_crawler.list_parser import parse_list_page


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_list_page_extracts_xuchang_record_and_pagination():
    page = parse_list_page(_fixture("list_page.html"))

    assert page.page_no == 1
    assert page.total_pages == 134
    assert len(page.records) == 1
    record = page.records[0]
    assert record.source_data_id == "3d40fcdee52e4a5088216a362437d848"
    assert record.province_name == "河南省"
    assert record.city_name == "许昌市"
    assert record.permit_number == "91411081MA3XFBNQ3C001U"
    assert record.valid_from == date(2026, 7, 14)
    assert record.valid_to == date(2031, 7, 13)
    assert record.detail_url.endswith("dataid=3d40fcdee52e4a5088216a362437d848")


def test_parse_detail_preserves_blank_slash_and_version_history():
    detail = parse_detail_page(_fixture("detail_page.html"))

    assert detail.production_site_address == "禹州市花石镇徐庄村"
    assert detail.pollution["main_pollutant_categories"] == ""
    assert detail.pollution["air_pollutant_types"] == "颗粒物,非甲烷总烃"
    assert detail.pollution["water_emission_standard"] == ""
    assert detail.pollution["emission_rights_info"] == "/"
    assert [version.business_type for version in detail.versions] == [
        "申领",
        "注销",
        "重新申请",
    ]
    assert detail.original_url.endswith("dataid=3d40fcdee52e4a5088216a362437d848")
    assert "showImage.action" in detail.copy_url


def test_reapplication_after_cancellation_is_currently_valid():
    detail = parse_detail_page(_fixture("detail_page.html"))

    status, latest_business_type = classify_current_status(
        detail.versions,
        as_of=date(2026, 7, 30),
    )

    assert status == "valid"
    assert latest_business_type == "重新申请"


def test_copy_viewer_expands_page_urls_in_numeric_order():
    viewer = parse_copy_viewer(_fixture("copy_viewer.html"))

    assert viewer.page_count == 37
    assert viewer.page_urls[0].endswith("datafileid=16f37057c63b4025a44f70ca4da959f0_1&fileType=pdffile&dataid=f4779cc08daa49f2aa8ae64c60a354e7")
    assert viewer.page_urls[-1].endswith("datafileid=16f37057c63b4025a44f70ca4da959f0_37&fileType=pdffile&dataid=f4779cc08daa49f2aa8ae64c60a354e7")

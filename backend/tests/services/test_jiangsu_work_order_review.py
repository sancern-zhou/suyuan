"""故障工单审核证据包服务的拆分存储与状态流转测试。"""
import pytest

from app.services.jiangsu_work_order_review import (
    attach_judgment,
    get_order,
    get_order_source,
    list_orders,
    record_operation,
    save_evidence,
)


@pytest.fixture()
def isolated_registry(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "data_registry_dir", str(tmp_path))
    return tmp_path


def _sample_package(code="FA260914178938611578927"):
    return {
        "working_order_code": code,
        "title": "站点PM10偏高",
        "site_name": "阜宁滨湖高级中学",
        "site_id": "3077A",
        "pollutant": "PM10",
        "window": {"start_time": "2026-09-13 19:41:00", "end_time": "2026-09-16 19:41:00"},
        "sources": {
            "station_hour": {
                "status": "success", "record_count": 2,
                "data": {"points": [{"time": "2026-09-13 20:00:00", "value": 23}]},
            },
            "weather": {
                "status": "success", "record_count": 1,
                "data": {"rows": [{"timePoint": "2026-09-13 20:00:00", "windSpeed": 2.1}]},
            },
        },
    }


def test_save_evidence_splits_index_and_sources(isolated_registry):
    entry = save_evidence(_sample_package())

    assert entry["status"] == "待审核"
    assert set(entry["source_files"]) == {"station_hour", "weather"}
    # index 不含来源明细，分文件单独落盘
    doc = get_order("FA260914178938611578927")
    assert "data" not in doc["index"]["sources"]["station_hour"]
    source = get_order_source("FA260914178938611578927", "station_hour")
    assert source["data"]["points"][0]["value"] == 23


def test_list_orders_filters_by_keyword_and_status(isolated_registry):
    save_evidence(_sample_package())

    payload = list_orders(keyword="阜宁")
    assert payload["total"] == 1
    payload = list_orders(keyword="不存在的站点")
    assert payload["total"] == 0
    payload = list_orders(status="待审核")
    assert payload["total"] == 1
    payload = list_orders(status="已归档")
    assert payload["total"] == 0


def test_attach_judgment_updates_status(isolated_registry):
    save_evidence(_sample_package())

    entry = attach_judgment("FA260914178938611578927", {
        "review_id": "review_abc", "version": 1, "subject_id": "FA260914178938611578927",
        "updated_at": "2026-09-18T10:00:00",
        "submission": {"decision": "pass", "comment": "通过，数据保留",
                       "data_impact": [{"pollutant": "PM10", "decision": "keep"}]},
    })
    assert entry["status"] == "待归档"
    assert entry["review_id"] == "review_abc"

    doc = get_order("FA260914178938611578927")
    assert doc["index"]["judgment"]["comment"] == "通过，数据保留"


def test_record_operation_feedback_keeps_status(isolated_registry):
    save_evidence(_sample_package())
    record_operation("FA260914178938611578927", "feedback", "建议复核采样流量", {"username": "ops"})

    doc = get_order("FA260914178938611578927")
    assert doc["entry"]["status"] == "待审核"
    assert doc["index"]["operations"][0]["label"] == "反馈"
    assert doc["index"]["operations"][0]["comment"] == "建议复核采样流量"


def test_record_operation_archive_without_review(isolated_registry):
    save_evidence(_sample_package())
    record_operation("FA260914178938611578927", "archive", "人工确认", {"username": "ops"})

    doc = get_order("FA260914178938611578927")
    assert doc["entry"]["status"] == "已归档"


def test_save_evidence_preserves_human_state(isolated_registry):
    save_evidence(_sample_package())
    record_operation("FA260914178938611578927", "archive", "人工确认", {"username": "ops"})

    # 重新采集证据不回退人工状态
    entry = save_evidence(_sample_package())
    assert entry["status"] == "已归档"
    doc = get_order("FA260914178938611578927")
    assert doc["index"]["operations"][0]["label"] == "归档"


def test_evidence_resources_declared_for_session(isolated_registry):
    from pathlib import Path

    from app.tools.jiangsu.fault_diagnosis import JiangsuReviewEvidenceTool

    folder = isolated_registry / "jiangsu_work_order_reviews" / "orders" / "abc"
    folder.mkdir(parents=True)
    index_path = folder / "index.json"
    index_path.write_text("{}", encoding="utf-8")
    entry = {"working_order_code": "FA1", "status": "待审核", "index_path": str(index_path),
             "source_files": {"station_hour": str(index_path)},
             "source_counts": {"station_hour": 3}}

    resources = JiangsuReviewEvidenceTool._evidence_resources(entry)

    assert resources[0]["kind"] == "data"
    assert resources[0]["group_key"] == "review_evidence:FA1"
    assert resources[0]["tool_name"] == "jiangsu_fetch_review_evidence"
    assert resources[1]["parent_key"] == "primary:data"
    assert resources[1]["relation"] == "attachment"
    # 发布管道按进程 CWD 解析相对路径会指向错误位置，声明必须携带绝对路径
    for resource in resources:
        assert Path(resource["locator"]["path"]).is_absolute()

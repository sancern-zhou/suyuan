"""江苏数据审核复核事件抓取器与结论查询接口测试。"""

import asyncio
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from app.api import jiangsu_data_audit_routes as routes_module
from app.fetchers import jiangsu_data_audit_review_event as module
from app.fetchers.jiangsu_data_audit_review_event import (
    EVENT_TYPE,
    JiangsuDataAuditReviewEventFetcher,
    _conflicts_with_platform,
    _review_id,
    _state_code_text,
    _summarize_logs,
)
from app.tools.jiangsu import external_audit as client_module
from app.tools.jiangsu.external_audit import JiangsuExternalAuditClient

NOW = datetime.fromisoformat("2026-09-15T07:30:00+08:00")
TODAY = date(2026, 9, 15)
YESTERDAY = date(2026, 9, 14)


class FakeClient:
    def __init__(self, status_rows=None, evidence_pages=None, audit_logs=None):
        self.status_rows = status_rows or []
        self.evidence_pages = dict(evidence_pages or {})
        self.audit_logs = audit_logs or {}
        self.status_calls = []
        self.evidence_calls = []
        self.log_calls = []

    async def get_station_audit_status(self, start_date, end_date, station_codes=None):
        self.status_calls.append((str(start_date), str(end_date), station_codes))
        return self.status_rows

    async def fetch_evidence_records(
        self, start_date, end_date, tab_type, *, station_codes=None, max_records=None, page_size=20,
    ):
        self.evidence_calls.append((str(start_date), str(end_date), tab_type, station_codes))
        records = self.evidence_pages.get(tab_type) or []
        bounded = records[:max_records] if max_records is not None else records
        return {
            "total_count": len(records),
            "records": bounded,
            "truncated": len(records) > len(bounded),
            "pages": 1,
        }

    async def get_audit_logs(self, start_date, end_date, station_codes=None):
        self.log_calls.append((str(start_date), str(end_date), station_codes))
        return self.audit_logs.get(tuple(station_codes or [])) or []


def _status_row(code, day, state="DirectAudit", name=None, city="南京市"):
    return {
        "stationCode": code,
        "stationName": name or code,
        "cityName": city,
        "cityCode": "",
        "districtName": "",
        "districtCode": "",
        "uniqueCode": f"U-{code}",
        "dayTime": day.isoformat(),
        "stateCode": state,
        "stateName": "已直审" if state == "DirectAudit" else state,
    }


def _evidence_record(tab, code="3001A", pollutant="100"):
    return {
        "tabType": tab,
        "stationCode": code,
        "stationName": "江宁九龙湖",
        "timePoint": "2026-09-14T02:00:00",
        "pollutantCode": pollutant,
        "pollutantName": "SO2",
        "value": "8",
        "auditBeforeValue": "8",
        "auditAfterValue": "8(RM)",
        "auditBeforeMark": "",
        "auditAfterMark": "RM",
        "matchedRules": [],
        "evidence": {
            "stationInfo": {"stationCode": code},
            "videoAlarms": [],
            "monitoringData": {"hourlyRecords": [{"timePoint": "2026-09-14T02:00:00", "value": 8}]},
            "meteorologicalData": [],
        },
    }


@pytest.fixture
def no_active_review(monkeypatch):
    monkeypatch.setattr(module, "has_active_review", lambda task_id, subject: False)


async def test_fetcher_syncs_completed_station_days_and_publishes_events(
    tmp_path, monkeypatch, no_active_review,
):
    client = FakeClient(
        status_rows=[
            _status_row("3001A", YESTERDAY, name="江宁九龙湖"),
            _status_row("3002A", YESTERDAY, state="WaitAudit", name="江宁大学城"),
            _status_row("3003A", TODAY, state="Reviewed", name="江阴虹桥", city="无锡市"),
        ],
        evidence_pages={
            "initialReview": [_evidence_record("initialReview")],
            "constant": [],
            "outlier": [_evidence_record("outlier", pollutant="105")],
        },
    )
    events = []

    async def publish(event):
        events.append(event)

    fetcher = JiangsuDataAuditReviewEventFetcher(
        registry_root=tmp_path, event_publisher=publish, clock=lambda: NOW, client=client,
    )

    result = await fetcher.fetch_and_store()

    assert result["published_events"] == 2
    assert result["skipped_processed"] == 0
    # 昨日条目无人工日志 + 今日条目未到回捞窗口
    assert result["feedback_waiting_logs"] == 2
    assert len(events) == 2
    first = events[0]
    assert first.event_type == EVENT_TYPE
    assert first.attributes["station_code"] == "3001A"
    assert first.attributes["audit_day"] == "2026-09-14"
    assert first.attributes["audit_subject_id"] == "3001A:2026-09-14"
    assert first.payload["subject_id"] == "3001A:2026-09-14"
    assert first.payload["tab_record_counts"] == {"initialReview": 1, "constant": 0, "outlier": 1}

    state = json.loads(fetcher.state_path.read_text(encoding="utf-8"))
    assert set(state["dispatched"]) == {"3001A:2026-09-14", "3003A:2026-09-15"}
    entry = state["dispatched"]["3001A:2026-09-14"]
    assert entry["feedback"]["status"] == "waiting_logs"
    assert entry["event_dir"].startswith(str(tmp_path))

    pack_path = Path(first.payload["evidence_pack_path"])
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    assert pack["schema_version"] == "jiangsu_data_audit_review/v1"
    assert pack["tabs"]["initialReview"]["records"][0]["auditAfterValue"] == "8(RM)"
    assert pack["tabs"]["constant"]["fetched_count"] == 0
    event_file = Path(entry["event_dir"]) / "event.json"
    assert event_file.exists()

    # 再次运行：状态去重，不重复派发
    rerun = await fetcher.fetch_and_store()
    assert rerun["published_events"] == 0
    assert rerun["skipped_processed"] == 2


def _pending_review(subject="3001A:2026-09-14", decision="approve", version=1, data_impact=None):
    return {
        "review_id": _review_id(subject),
        "task_id": module.REVIEW_TASK_ID,
        "subject_id": subject,
        "status": "pending_review",
        "version": version,
        "decision": decision,
        "summary": "summary",
        "comment": "comment",
        "data_impact": data_impact or [],
        "human_decision": None,
        "history": [],
    }


async def test_feedback_confirms_consistent_conclusion(tmp_path, monkeypatch, no_active_review):
    client = FakeClient(
        audit_logs={("3001A",): [
            {"auditType": "初审", "operateType": "Pass", "operator": "张三",
             "operateTime": "2026-09-15 09:00:00", "timePoint": "2026-09-14T02:00:00"},
        ]},
    )
    decided = []

    def fake_decide(review_id, decision, actor):
        decided.append((review_id, decision, actor))
        record = _pending_review(decision=decision["decision"])
        record["version"] = decision["version"] + 1
        record["human_decision"] = {**decision, "actor": actor}
        record["human_feedback"] = {"status": "pending"}
        return record

    monkeypatch.setattr(module, "load_review", lambda rid: _pending_review())
    monkeypatch.setattr(module, "decide_review", fake_decide)

    fetcher = JiangsuDataAuditReviewEventFetcher(
        registry_root=tmp_path, clock=lambda: NOW, client=client,
    )
    fetcher._write_json(fetcher.state_path, {
        "dispatched": {
            "3001A:2026-09-14": {
                "station_code": "3001A", "station_name": "江宁九龙湖", "audit_day": "2026-09-14",
                "event_dir": str(tmp_path / "ev"),
                "feedback": {"status": "waiting_logs", "rounds": 0, "decided_version": None},
            },
        },
    })

    result = await fetcher.fetch_and_store()

    assert result["published_events"] == 0
    assert result["feedback_confirmed"] == 1
    review_id, decision, actor = decided[0]
    assert decision["action"] == "confirm"
    assert decision["decision"] == "approve"  # 人工未修改数据
    assert decision["intervals_confirmed"] is True
    assert actor["username"] == "jiangsu-audit-platform"
    state = json.loads(fetcher.state_path.read_text(encoding="utf-8"))
    assert state["dispatched"]["3001A:2026-09-14"]["feedback"]["status"] == "done"


async def test_feedback_conflict_rejects_and_dispatches_rerun(tmp_path, monkeypatch, no_active_review):
    client = FakeClient(
        audit_logs={("3001A",): [
            {"auditType": "初审", "operateType": "AddMark", "operator": "李四",
             "operateTime": "2026-09-15 10:00:00", "timePoint": "2026-09-14T02:00:00",
             "pollutantName": "SO2", "beforeValue": 8, "afterValue": 8, "afterMark": "RM"},
        ]},
    )
    decided = []

    def fake_decide(review_id, decision, actor):
        decided.append(dict(decision))
        record = _pending_review()
        record["version"] = decision["version"] + 1
        record["status"] = "rejected" if decision["action"] == "reject" else "archived"
        record["human_decision"] = {**decision, "actor": actor}
        return record

    monkeypatch.setattr(module, "load_review", lambda rid: _pending_review(decision="approve"))
    monkeypatch.setattr(module, "decide_review", fake_decide)

    events = []

    async def publish(event):
        events.append(event)

    event_dir = tmp_path / "ev"
    fetcher = JiangsuDataAuditReviewEventFetcher(
        registry_root=tmp_path, event_publisher=publish, clock=lambda: NOW, client=client,
    )
    original_event = {
        "event_id": "da-audit-abc",
        "event_type": EVENT_TYPE,
        "occurred_at": NOW.isoformat(),
        "attributes": {"station_code": "3001A", "audit_subject_id": "3001A:2026-09-14"},
        "payload": {
            "station": {"station_code": "3001A"},
            "audit_day": "2026-09-14",
            "subject_id": "3001A:2026-09-14",
            "evidence_pack_path": "agent://pack.json",
        },
    }
    fetcher._write_json(event_dir / "event.json", original_event)
    fetcher._write_json(fetcher.state_path, {
        "dispatched": {
            "3001A:2026-09-14": {
                "station_code": "3001A", "station_name": "江宁九龙湖", "audit_day": "2026-09-14",
                "event_dir": str(event_dir),
                "feedback": {"status": "waiting_logs", "rounds": 0, "decided_version": None},
            },
        },
    })

    result = await fetcher.fetch_and_store()

    assert decided[0]["action"] == "reject"
    assert decided[0]["decision"] == "reject"
    assert result["feedback_rerun_dispatched"] == 1
    assert len(events) == 1
    rerun_event = events[0]
    assert rerun_event.event_id == "da-audit-abc-r1"
    context = rerun_event.payload["continuity_context"]
    assert context["reason"] == "platform_audit_feedback"
    assert context["platform_audit_logs"]["has_data_modification"] is True
    assert context["platform_audit_logs"]["modification_samples"][0]["after_mark"] == "RM"
    assert context["previous_submission"]["decision"] == "approve"
    assert (event_dir / "platform_audit_logs_r1.json").exists()
    state = json.loads(fetcher.state_path.read_text(encoding="utf-8"))
    feedback = state["dispatched"]["3001A:2026-09-14"]["feedback"]
    assert feedback["status"] == "rerun_dispatched"
    assert feedback["rounds"] == 1


async def test_feedback_auto_confirms_rerun_conclusion(tmp_path, monkeypatch, no_active_review):
    client = FakeClient(audit_logs={("3001A",): [
        {"auditType": "初审", "operateType": "AddMark", "operator": "李四",
         "operateTime": "2026-09-15 10:00:00"},
    ]})
    decided = []

    def fake_decide(review_id, decision, actor):
        decided.append(dict(decision))
        return _pending_review(version=decision["version"] + 1)

    review = _pending_review(decision="reject", version=3)
    monkeypatch.setattr(module, "load_review", lambda rid: review)
    monkeypatch.setattr(module, "decide_review", fake_decide)

    fetcher = JiangsuDataAuditReviewEventFetcher(
        registry_root=tmp_path, clock=lambda: NOW, client=client,
    )
    fetcher._write_json(fetcher.state_path, {
        "dispatched": {
            "3001A:2026-09-14": {
                "station_code": "3001A", "station_name": "江宁九龙湖", "audit_day": "2026-09-14",
                "event_dir": str(tmp_path / "ev"),
                "feedback": {"status": "rerun_dispatched", "rounds": 1, "decided_version": 2},
            },
        },
    })

    result = await fetcher.fetch_and_store()

    assert result["feedback_confirmed"] == 1
    assert decided[0]["action"] == "confirm"
    state = json.loads(fetcher.state_path.read_text(encoding="utf-8"))
    assert state["dispatched"]["3001A:2026-09-14"]["feedback"]["status"] == "done"


async def test_feedback_keeps_waiting_without_logs(tmp_path, monkeypatch, no_active_review):
    client = FakeClient(audit_logs={})
    monkeypatch.setattr(module, "load_review", lambda rid: None)
    fetcher = JiangsuDataAuditReviewEventFetcher(
        registry_root=tmp_path, clock=lambda: NOW, client=client,
    )
    fetcher._write_json(fetcher.state_path, {
        "dispatched": {
            "3001A:2026-09-14": {
                "station_code": "3001A", "station_name": "江宁九龙湖", "audit_day": "2026-09-14",
                "event_dir": str(tmp_path / "ev"),
                "feedback": {"status": "waiting_logs", "rounds": 0, "decided_version": None},
            },
        },
    })

    result = await fetcher.fetch_and_store()

    assert result["feedback_waiting_logs"] == 1
    assert result["feedback_confirmed"] == 0
    state = json.loads(fetcher.state_path.read_text(encoding="utf-8"))
    assert state["dispatched"]["3001A:2026-09-14"]["feedback"]["status"] == "waiting_logs"


def test_state_code_text_handles_enum_int_and_text():
    assert _state_code_text(0) == "WaitAudit"
    assert _state_code_text(3) == "Reviewed"
    assert _state_code_text("WaitAudit") == "WaitAudit"
    assert _state_code_text("") == ""


def test_summarize_logs_and_conflict_rules():
    logs = [
        {"auditType": "初审", "operateType": "AddMark", "operator": "张三",
         "timePoint": "2026-09-14T02:00:00", "pollutantName": "SO2",
         "beforeValue": 8, "afterValue": 8, "afterMark": "RM", "operateTime": "2026-09-15 09:00:00"},
        {"auditType": "复核", "operateType": 6, "operator": "李四", "operateTime": "2026-09-15 10:00:00"},
    ]
    summary = _summarize_logs(logs)
    assert summary["log_count"] == 2
    assert summary["audit_type_counts"] == {"初审": 1, "复核": 1}
    assert summary["has_data_modification"] is True
    assert summary["modification_samples"][0]["after_mark"] == "RM"

    approve_review = {"decision": "approve", "data_impact": []}
    assert _conflicts_with_platform(approve_review, summary) is True
    assert _conflicts_with_platform({"decision": "reject", "data_impact": []}, summary) is False
    no_modification = _summarize_logs([logs[1]])
    assert _conflicts_with_platform(approve_review, no_modification) is False
    assert _conflicts_with_platform({"decision": "needs_evidence", "data_impact": []}, no_modification) is True


def test_review_id_matches_task_review_deterministic_hash():
    import hashlib

    subject = "3001A:2026-09-14"
    expected = "review_" + hashlib.sha256(
        json.dumps([module.REVIEW_TASK_ID, subject], ensure_ascii=False).encode()
    ).hexdigest()[:32]
    assert _review_id(subject) == expected


# ------------------------------------------------------------------- client


class FakeAuthApi:
    base_url = "http://example.test/api/airprovinceproduct"
    sys_code = "SunAirProvince"
    timeout_seconds = 5

    async def _get_token(self):
        return "token"


def test_client_station_status_tolerates_list_and_builds_params(monkeypatch):
    client = JiangsuExternalAuditClient(api=FakeAuthApi())
    captured = {}

    async def fake_request(*, method, path, params=None, json_body=None):
        captured.update(method=method, path=path, params=params, json_body=json_body)
        return [{"stationCode": "3001A", "dayTime": "2026-09-14T00:00:00", "stateCode": "Reviewed"}]

    monkeypatch.setattr(client, "_request_json", fake_request)
    rows = asyncio.run(client.get_station_audit_status(YESTERDAY, TODAY, ["3001A", ""]))
    assert rows[0]["stateCode"] == "Reviewed"
    assert captured["method"] == "GET"
    assert captured["path"] == client_module.STATION_AUDIT_STATUS_PATH
    assert ("StationCode", "3001A") in captured["params"]
    assert ("StartTime", "2026-09-14") in captured["params"]

    async def fake_bad(*, method, path, params=None, json_body=None):
        return {"unexpected": True}

    monkeypatch.setattr(client, "_request_json", fake_bad)
    with pytest.raises(ValueError):
        asyncio.run(client.get_station_audit_status(YESTERDAY, TODAY))


def test_client_evidence_pagination_and_body(monkeypatch):
    client = JiangsuExternalAuditClient(api=FakeAuthApi())
    pages = [
        {"totalCount": 3, "items": [{"id": 1}, {"id": 2}]},
        {"totalCount": 3, "items": [{"id": 3}]},
    ]
    bodies = []

    async def fake_request(*, method, path, params=None, json_body=None):
        assert method == "POST"
        assert path == client_module.EXTERNAL_EVIDENCE_PATH
        bodies.append(json_body)
        return pages[len(bodies) - 1]

    monkeypatch.setattr(client, "_request_json", fake_request)
    result = asyncio.run(
        client.fetch_evidence_records("2026-09-14", "2026-09-14", "outlier",
                                      station_codes=["3001A"], max_records=50, page_size=2),
    )
    assert [item["id"] for item in result["records"]] == [1, 2, 3]
    assert result["total_count"] == 3
    assert result["truncated"] is False
    assert bodies[0]["tabType"] == "outlier"
    assert bodies[0]["stationCodes"] == ["3001A"]
    assert bodies[0]["maxResultCount"] == 2
    assert bodies[1]["skipCount"] == 2

    bodies.clear()

    truncated = asyncio.run(
        client.fetch_evidence_records("2026-09-14", "2026-09-14", "outlier",
                                      station_codes=["3001A"], max_records=2, page_size=2),
    )
    assert truncated["truncated"] is True
    assert len(truncated["records"]) == 2


def test_client_rejects_bad_tab_type():
    client = JiangsuExternalAuditClient(api=FakeAuthApi())
    with pytest.raises(ValueError):
        asyncio.run(client.get_evidence_page(YESTERDAY, TODAY, "zeroNegative"))


# -------------------------------------------------------------------- routes


def test_routes_list_filters_by_station_and_day(tmp_path, monkeypatch):
    records = [
        {**_pending_review("3001A:2026-09-14", decision="approve"), "status": "archived",
         "title": "江宁九龙湖 2026-09-14 数据审核",
         "sections": [{"title": "基础信息", "fields": [
             {"key": "station_name", "label": "站点名称", "value": "江宁九龙湖"},
             {"key": "city_name", "label": "城市", "value": "南京市"},
         ]}]},
        _pending_review("3002A:2026-09-15", decision="reject"),
    ]
    monkeypatch.setattr(routes_module, "list_reviews", lambda **kwargs: records)

    result = asyncio.run(routes_module.list_data_audit_conclusions(
        station_code="3001A", city_name=None, start_date="2026-09-14", end_date="2026-09-14",
        decision=None, status=None, limit=50, offset=0, user=None,
    ))
    assert result["status"] == "success"
    items = result["data"]["items"]
    assert result["data"]["total"] == 1
    assert items[0]["station_code"] == "3001A"
    assert items[0]["audit_day"] == "2026-09-14"
    assert items[0]["station_name"] == "江宁九龙湖"
    assert items[0]["city_name"] == "南京市"
    assert items[0]["status"] == "archived"


def test_routes_detail_returns_404_for_other_task(tmp_path, monkeypatch):
    other = {**_pending_review(), "task_id": "jiangsu_fault_work_order_review"}
    monkeypatch.setattr(routes_module, "load_review", lambda rid: other)

    with pytest.raises(Exception) as excinfo:
        asyncio.run(routes_module.get_data_audit_conclusion("review_x", user=None))
    assert getattr(excinfo.value, "status_code", None) == 404

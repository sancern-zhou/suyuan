"""故障工单审核人工退回 → 增量复审队列与派发测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import jiangsu_fault_work_order_review_rerun as service
from app.services import task_review as task_review_service


@pytest.fixture(autouse=True)
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "get_data_registry", lambda: tmp_path)
    monkeypatch.setattr(task_review_service, "get_data_registry", lambda: tmp_path)
    # 提交校验要求证据文件真实存在；是否写入 event.json 由各用例自行控制。
    evidence_dir = tmp_path / "work_order_review_events" / "2026" / "09" / "02" / "jsworev_event_1"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "review_evidence_pack.json").write_text("{}", encoding="utf-8")


def review_payload(tmp_path: Path, **changes):
    evidence_path = (
        tmp_path / "work_order_review_events" / "2026" / "09" / "02"
        / "jsworev_event_1" / "review_evidence_pack.json"
    )
    return dict(
        subject_id="FA260902001",
        event_id="jsworev_event_1",
        category="工单审核",
        title="江宁九龙湖 工单审核",
        summary="建议通过；数据保留",
        decision="approve",
        comment="事实与逻辑一致性核验通过",
        checks=[dict(name="事实一致性", status="pass", basis="已核实")],
        data_impact=[],
        sections=[
            {"title": "工单信息", "fields": [
                {"key": "work_order_no", "label": "工单号", "value": "FA260902001"},
                {"key": "sop_id", "label": "审核 SOP", "value": "SOP-01"},
            ]},
        ],
        evidence=[{"label": "证据包", "path": str(evidence_path)}],
    ) | changes


def submit(tmp_path: Path, execution="exec-1"):
    return task_review_service.submit_review(
        review_payload(tmp_path),
        dict(task_id=service.REVIEW_TASK_ID, execution_id=execution, task_name="江苏故障工单审核"),
    )


def reject(record, comment="剔除区间起止缺失，请补充边界来源"):
    return task_review_service.decide_review(
        record["review_id"],
        dict(version=record["version"], action="reject", decision="reject",
             comment=comment, data_impact=[]),
        {"user_id": "u1", "username": "reviewer"},
    )


def write_event_file(tmp_path: Path, event_id: str, work_order_code: str) -> Path:
    event_dir = tmp_path / "work_order_review_events" / "2026" / "09" / "02" / event_id
    event_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_id": event_id,
        "event_type": "jiangsu.fault_work_order.review_requested",
        "occurred_at": "2026-09-02T08:30:00+08:00",
        "attributes": {"work_order_code": work_order_code, "sop_id": "SOP-01"},
        "payload": {
            "work_order_code": work_order_code,
            "evidence_pack_path": f"{event_dir / 'review_evidence_pack.json'}",
        },
    }
    (event_dir / "event.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (event_dir / "review_evidence_pack.json").write_text("{}", encoding="utf-8")
    return event_dir


def test_reject_queues_pending_rerun_entry(tmp_path):
    write_event_file(tmp_path, "jsworev_event_1", "FA260902001")
    record = submit(tmp_path)
    reject(record, comment="数据影响缺少剔除边界，请按 SOP-01 M5 修正")

    entries = service.pending_entries(tmp_path / service.QUEUE_DIR_NAME)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["subject_id"] == "FA260902001"
    assert entry["rerun_round"] == 2
    continuity = entry["continuity"]
    assert continuity["reason"] == "review_reject"
    assert continuity["human_decision"]["comment"].startswith("数据影响缺少剔除边界")
    assert continuity["previous_submission"]["sections_key_fields"]["work_order_no"] == "FA260902001"
    assert "权威修正基准" in continuity["instruction"]


def test_reject_without_comment_skips_queue(tmp_path):
    record = submit(tmp_path)
    # API 层已强制退回意见非空；此处直调钩子验证服务层防御。
    entry = service.queue_fault_work_order_review_rerun(
        record, dict(action="reject", decision="reject", comment="   "), {"username": "reviewer"},
    )
    assert entry is None
    assert service.pending_entries(tmp_path / service.QUEUE_DIR_NAME) == []


def test_other_tasks_do_not_queue_rerun(tmp_path):
    record = task_review_service.submit_review(
        review_payload(tmp_path),
        dict(task_id="other_task", execution_id="exec-1"),
    )
    reject(record)
    assert service.pending_entries(tmp_path / service.QUEUE_DIR_NAME) == []


def test_rerun_round_limit_blocks_third_rejection(tmp_path, monkeypatch):
    write_event_file(tmp_path, "jsworev_event_1", "FA260902001")
    monkeypatch.setattr(service, "MAX_RERUN_ROUNDS", 2)

    record = submit(tmp_path, "exec-1")
    reject(record)
    record = submit(tmp_path, "exec-2")
    assert record["status"] == "pending_review"
    assert len(record["history"]) == 1
    reject(record)
    # 模拟 worker 已消费第二次退回的队列（产生第三轮提交）。
    pending_dir = tmp_path / service.QUEUE_DIR_NAME / "pending"
    for path in pending_dir.glob("*.json"):
        path.unlink()
    # 第三轮提交被退回时已达到重审上限，不再排队。
    record = submit(tmp_path, "exec-3")
    reject(record)
    assert service.pending_entries(tmp_path / service.QUEUE_DIR_NAME) == []


def test_locate_event_payload_prefers_evidence_dir_then_fallback(tmp_path):
    write_event_file(tmp_path, "jsworev_event_1", "FA260902001")
    write_event_file(tmp_path, "jsworev_event_older", "FA260902001")

    record = submit(tmp_path)
    reject(record)
    entry = service.pending_entries(tmp_path / service.QUEUE_DIR_NAME)[0]
    entry.pop("_path")

    # evidence 路径回溯：直接定位上一轮引用的事件目录。
    payload = service.locate_event_payload(entry, root=tmp_path)
    assert payload is not None
    assert payload["event_id"] == "jsworev_event_1"

    # evidence 不可用时按 event_id 精确匹配。
    entry["continuity"]["previous_submission"]["evidence_paths"] = []
    payload = service.locate_event_payload(entry, root=tmp_path)
    assert payload["event_id"] == "jsworev_event_1"

    # event_id 也缺失时按工单号匹配最新事件。
    entry["event_id"] = None
    payload = service.locate_event_payload(entry, root=tmp_path)
    assert payload["attributes"]["work_order_code"] == "FA260902001"


def test_build_rerun_event_injects_continuity(tmp_path):
    write_event_file(tmp_path, "jsworev_event_1", "FA260902001")
    record = submit(tmp_path)
    reject(record)
    entry = service.pending_entries(tmp_path / service.QUEUE_DIR_NAME)[0]
    entry.pop("_path")

    event = service.build_rerun_event(entry, service.locate_event_payload(entry, root=tmp_path))
    assert event.attributes["work_order_code"] == "FA260902001"
    assert event.attributes["continuity_mode"] == "review_reject"
    assert event.payload["continuity_context"]["human_decision"]["comment"]
    assert event.payload["evidence_pack_path"].endswith("review_evidence_pack.json")


class FakeDispatch:
    def __init__(self, accepted=None, execution_ids=None):
        self.accepted_task_ids = accepted or []
        self.matched_task_ids = list(self.accepted_task_ids)
        self.execution_ids = execution_ids or []


class FakeTaskService:
    def __init__(self, dispatch=None, error=None):
        self.calls = []
        self._dispatch = dispatch or FakeDispatch(accepted=["jiangsu_fault_work_order_review"])
        self._error = error

    async def publish_event(self, event, **kwargs):
        self.calls.append((event, kwargs))
        if self._error:
            raise self._error
        return self._dispatch


@pytest.mark.asyncio
async def test_publish_pending_reruns_dispatches_with_force_retry(tmp_path, monkeypatch):
    write_event_file(tmp_path, "jsworev_event_1", "FA260902001")
    scheduled = FakeTaskService()
    monkeypatch.setattr(
        "app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled,
    )
    record = submit(tmp_path)
    reject(record, comment="请补充剔除边界")

    stats = await service.publish_pending_reruns()
    assert stats == {"pending": 1, "dispatched": 1, "skipped": 0, "failed": 0}
    event, kwargs = scheduled.calls[0]
    assert kwargs.get("force_retry") is True
    assert event.payload["continuity_context"]["reason"] == "review_reject"
    assert service.pending_entries(tmp_path / service.QUEUE_DIR_NAME) == []
    done = tmp_path / service.QUEUE_DIR_NAME / "done" / f"{record['review_id']}.json"
    assert json.loads(done.read_text(encoding="utf-8"))["result"] == "dispatched"


@pytest.mark.asyncio
async def test_publish_skips_when_active_review_exists(tmp_path, monkeypatch):
    write_event_file(tmp_path, "jsworev_event_1", "FA260902001")
    scheduled = FakeTaskService()
    monkeypatch.setattr(
        "app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled,
    )
    record = submit(tmp_path)
    reject(record)
    # 模拟 fetcher 已为同一工单发起新审核（pending_review）。
    task_review_service.submit_review(review_payload(tmp_path), dict(
        task_id=service.REVIEW_TASK_ID, execution_id="exec-new", task_name="江苏故障工单审核"))

    stats = await service.publish_pending_reruns()
    assert stats["skipped"] == 1 and stats["dispatched"] == 0
    assert scheduled.calls == []
    done = tmp_path / service.QUEUE_DIR_NAME / "done" / f"{record['review_id']}.json"
    assert json.loads(done.read_text(encoding="utf-8"))["result"] == "skipped_active_review"


@pytest.mark.asyncio
async def test_publish_missing_event_moves_to_failed(tmp_path, monkeypatch):
    scheduled = FakeTaskService()
    monkeypatch.setattr(
        "app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled,
    )
    record = submit(tmp_path)
    reject(record)

    stats = await service.publish_pending_reruns()
    assert stats["failed"] == 1
    failed = tmp_path / service.QUEUE_DIR_NAME / "failed" / f"{record['review_id']}.json"
    assert json.loads(failed.read_text(encoding="utf-8"))["error"] == "original_event_payload_not_found"


@pytest.mark.asyncio
async def test_publish_retries_then_fails_after_attempts(tmp_path, monkeypatch):
    write_event_file(tmp_path, "jsworev_event_1", "FA260902001")
    scheduled = FakeTaskService(error=RuntimeError("boom"))
    monkeypatch.setattr(
        "app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled,
    )
    record = submit(tmp_path)
    reject(record)

    await service.publish_pending_reruns()
    entry_path = tmp_path / service.QUEUE_DIR_NAME / "pending" / f"{record['review_id']}.json"
    assert json.loads(entry_path.read_text(encoding="utf-8"))["attempts"] == 1

    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["attempts"] = entry["max_attempts"] - 1
    entry_path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")

    stats = await service.publish_pending_reruns()
    assert stats["failed"] == 1
    assert not entry_path.exists()
    failed = tmp_path / service.QUEUE_DIR_NAME / "failed" / f"{record['review_id']}.json"
    assert json.loads(failed.read_text(encoding="utf-8"))["error"] == "boom"


@pytest.mark.asyncio
async def test_rerun_fetcher_publishes_queue(tmp_path, monkeypatch):
    from app.fetchers.jiangsu_fault_work_order_review_rerun import (
        JiangsuFaultWorkOrderReviewRerunFetcher,
    )

    write_event_file(tmp_path, "jsworev_event_1", "FA260902001")
    scheduled = FakeTaskService()
    monkeypatch.setattr(
        "app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled,
    )
    record = submit(tmp_path)
    reject(record)

    stats = await JiangsuFaultWorkOrderReviewRerunFetcher().fetch_and_store()
    assert stats["dispatched"] == 1
    assert scheduled.calls[0][0].attributes["continuity_mode"] == "review_reject"


def test_decide_review_reject_triggers_rerun_hook(tmp_path, monkeypatch):
    write_event_file(tmp_path, "jsworev_event_1", "FA260902001")
    called = {}
    monkeypatch.setattr(
        service, "queue_fault_work_order_review_rerun",
        lambda record, decision, actor: called.update(review_id=record["review_id"]) or {"ok": True},
    )
    record = submit(tmp_path)
    reject(record)
    assert called.get("review_id") == record["review_id"]

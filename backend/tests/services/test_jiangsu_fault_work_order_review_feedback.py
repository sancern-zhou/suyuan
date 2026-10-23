"""故障工单审核人工决策 → 对话反馈记录与一致性确认队列测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import jiangsu_fault_work_order_review_feedback as service
from app.services import task_review as task_review_service


@pytest.fixture(autouse=True)
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "get_data_registry", lambda: tmp_path)
    monkeypatch.setattr(task_review_service, "get_data_registry", lambda: tmp_path)
    # 写执行会话需要真实 DB；反馈记录与会话追加在各自用例里单独验证。
    monkeypatch.setattr(task_review_service, "_append_review_session_record",
                        lambda record, decision, actor: "scheduled_task_session_1")


def review_payload(tmp_path: Path, **changes):
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
    ) | changes


def submit(tmp_path: Path, execution="exec-1", **changes):
    return task_review_service.submit_review(
        review_payload(tmp_path, **changes),
        dict(task_id=service.REVIEW_TASK_ID, execution_id=execution, task_name="江苏故障工单审核"),
    )


def decide(record, action, comment="剔除区间起止缺失，请补充边界来源", ai_decision=None):
    payload = dict(version=record["version"], action=action,
                   decision="reject" if action == "reject" else "approve",
                   comment=comment, data_impact=[])
    if ai_decision:
        payload["decision"] = ai_decision
    return task_review_service.decide_review(
        record["review_id"], payload, {"user_id": "u1", "username": "reviewer"},
    )


def test_consistent_confirm_skips_queue(tmp_path):
    record = submit(tmp_path)
    decide(record, "confirm", comment="人工已核验")
    assert service.pending_entries(tmp_path / service.QUEUE_DIR_NAME) == []


def test_reject_queues_feedback_entry_with_session(tmp_path):
    record = submit(tmp_path)
    decided = decide(record, "reject", comment="数据影响缺少剔除边界，请按 SOP-01 M5 修正")

    entries = service.pending_entries(tmp_path / service.QUEUE_DIR_NAME)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["subject_id"] == "FA260902001"
    assert entry["session_id"] == "scheduled_task_session_1"
    human = entry["human_decision"]
    assert human["action"] == "reject" and human["decision"] == "reject"
    assert human["comment"].startswith("数据影响缺少剔除边界")
    assert entry["previous_submission"]["sections_key_fields"]["work_order_no"] == "FA260902001"
    assert decided["human_feedback"]["status"] == "pending"


def test_confirm_with_divergent_ai_decision_queues_feedback(tmp_path):
    record = submit(tmp_path, decision="needs_evidence")
    decide(record, "confirm", comment="AI 漏看附件，附件已齐全")

    entries = service.pending_entries(tmp_path / service.QUEUE_DIR_NAME)
    assert len(entries) == 1
    assert service.is_decision_consistent("confirm", "needs_evidence") is False
    assert service.is_decision_consistent("confirm", "approve") is True


def test_other_tasks_do_not_queue_feedback(tmp_path):
    record = task_review_service.submit_review(
        review_payload(tmp_path),
        dict(task_id="other_task", execution_id="exec-1"),
    )
    decide(record, "reject")
    assert service.pending_entries(tmp_path / service.QUEUE_DIR_NAME) == []


@pytest.mark.asyncio
async def test_consume_writes_consistency_statement_into_session(tmp_path, monkeypatch):
    record = submit(tmp_path)
    decide(record, "reject", comment="证据不足，请补充")

    captured = {}

    async def fake_statement(entry):
        captured["entry"] = entry
        return {"consistent": False, "statement": "AI 原结论建议通过，人工审核发现剔除区间缺失，判定退回。"}

    async def fake_append(session_id, content, entry):
        captured["session_id"] = session_id
        captured["content"] = content
        return True

    monkeypatch.setattr(service, "build_consistency_statement", fake_statement)
    monkeypatch.setattr(service, "append_session_assistant_message", fake_append)

    stats = await service.consume_pending_feedback()
    assert stats == {"pending": 1, "done": 1, "failed": 0}
    assert captured["session_id"] == "scheduled_task_session_1"
    assert "【审核一致性确认】" in captured["content"]
    assert "退回工单" in captured["content"]
    assert service.pending_entries(tmp_path / service.QUEUE_DIR_NAME) == []
    done = tmp_path / service.QUEUE_DIR_NAME / "done" / f"{record['review_id']}.json"
    assert json.loads(done.read_text(encoding="utf-8"))["consistent"] is False


@pytest.mark.asyncio
async def test_consume_retries_then_fails_without_session(tmp_path):
    record = submit(tmp_path)
    decide(record, "reject")
    entry_path = tmp_path / service.QUEUE_DIR_NAME / "pending" / f"{record['review_id']}.json"
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["session_id"] = None
    entry["execution_id"] = None
    entry_path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")

    stats = await service.consume_pending_feedback()
    assert stats["failed"] == 1
    failed = tmp_path / service.QUEUE_DIR_NAME / "failed" / f"{record['review_id']}.json"
    assert json.loads(failed.read_text(encoding="utf-8"))["error"] == "original_session_not_found"


@pytest.mark.asyncio
async def test_consume_llm_failure_retries_then_fails(tmp_path, monkeypatch):
    record = submit(tmp_path)
    decide(record, "reject")

    async def boom(entry):
        raise RuntimeError("llm down")

    monkeypatch.setattr(service, "build_consistency_statement", boom)
    stats = await service.consume_pending_feedback()
    assert stats["failed"] == 0
    entry_path = tmp_path / service.QUEUE_DIR_NAME / "pending" / f"{record['review_id']}.json"
    assert json.loads(entry_path.read_text(encoding="utf-8"))["attempts"] == 1

    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["attempts"] = entry["max_attempts"] - 1
    entry_path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    stats = await service.consume_pending_feedback()
    assert stats["failed"] == 1
    assert not entry_path.exists()


@pytest.mark.asyncio
async def test_feedback_fetcher_consumes_queue(tmp_path, monkeypatch):
    from app.fetchers.jiangsu_fault_work_order_review_feedback import (
        JiangsuFaultWorkOrderReviewFeedbackFetcher,
    )

    record = submit(tmp_path)
    decide(record, "reject")

    async def fake_statement(entry):
        return {"consistent": False, "statement": "人工退回依据成立。"}

    async def fake_append(session_id, content, entry):
        return True

    monkeypatch.setattr(service, "build_consistency_statement", fake_statement)
    monkeypatch.setattr(service, "append_session_assistant_message", fake_append)
    stats = await JiangsuFaultWorkOrderReviewFeedbackFetcher().fetch_and_store()
    assert stats["done"] == 1


def test_decide_review_reject_triggers_feedback_hook(tmp_path, monkeypatch):
    called = {}
    monkeypatch.setattr(
        service, "queue_work_order_review_feedback",
        lambda record, decision, actor, session_id=None:
            called.update(review_id=record["review_id"], action=decision["action"]) or {"ok": True},
    )
    record = submit(tmp_path)
    decide(record, "reject")
    assert called.get("review_id") == record["review_id"]
    assert called.get("action") == "reject"

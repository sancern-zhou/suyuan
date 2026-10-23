"""江苏运维平台工单写回（platform_workflow）单元测试：全部走假 API，不打真实平台。"""
from __future__ import annotations

import json

import httpx
import pytest

from app.tools.jiangsu import platform_workflow as module


class _FakeApi:
    def __init__(self, *, fail_on_save: bool = False) -> None:
        self.fail_on_save = fail_on_save
        self.gets: list[tuple[str, list[tuple[str, str]]]] = []
        self.posts: list[tuple[str, dict]] = []

    async def get(self, path, params):
        self.gets.append((path, list(params)))
        if path == module._LIST_PATH:
            return {"result": {"items": [
                {"id": 71746, "workingOrderCode": "FA2601", "uniqueCode": "320382004"},
            ]}}
        return {"result": [_detail()]}

    async def post(self, path, payload):
        self.posts.append((path, payload))
        if path == module._SAVE_ORDER_PATH and self.fail_on_save:
            raise httpx.HTTPStatusError("boom", request=httpx.Request("POST", "http://x"),
                                        response=httpx.Response(500))
        return {"success": True, "message": "ok"}


def _detail(*, order_status: str = "Doing", workflow_status: str = "ToAssign") -> dict:
    return {
        "wo": {
            "id": 71746,
            "workingOrderCode": "FA2601",
            "orderStatus": order_status,
            "workFlowStatus": workflow_status,
            "currentPoint": "6869a2ef-545b-4175-a3f1-ce340a016914",
            "workFlowId": "5a77ebc1-9b99-41b6-9beb-1cb2ee76ecd0",
        },
        "details": [],
        "workFlowInfo": {"stepList": [
            {"guid": "6869a2ef-545b-4175-a3f1-ce340a016914", "taskName": "省中心审核",
             "formCode": "FaultApprove", "taskPreviousId": "4987679e-2f44-4291-bb7a-9e7041024136",
             "taskNextId": None, "roleId": "136", "rank": 4, "status": True},
        ]},
    }


@pytest.fixture()
def enabled(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "jiangsu_platform_writeback_enabled", True)
    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_registry(monkeypatch))
    return settings


def tmp_registry(monkeypatch):
    import tempfile
    from pathlib import Path

    registry = Path(tempfile.mkdtemp(prefix="pfw-test-"))
    monkeypatch.setattr(module, "get_data_registry", lambda: registry)
    return registry


def test_submit_review_decision_disabled_without_flag(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "jiangsu_platform_writeback_enabled", False)
    fake = _FakeApi()
    monkeypatch.setattr(module, "_JiangsuAuthenticatedApi", lambda source: fake)
    import asyncio

    outcome = asyncio.run(module.submit_review_decision(
        "FA2601", action="confirm", approved=True, comment="同意归档"))
    assert outcome["status"] == "disabled"
    assert fake.posts == []


def test_approve_claims_then_closes_order(enabled, monkeypatch):
    fake = _FakeApi()
    monkeypatch.setattr(module, "_JiangsuAuthenticatedApi", lambda source: fake)
    import asyncio

    outcome = asyncio.run(module.submit_review_decision(
        "FA2601", action="confirm", approved=True, comment="审核通过"))
    assert outcome["status"] == "synced"
    assert [path for path, _ in fake.posts] == [module._SAVE_ORDER_PATH]
    assert fake.gets[-1] == (module._RECEIVE_PATH, [("Id", "71746")])
    _, save_payload = fake.posts[0]
    assert save_payload["formCode"] == "FaultApprove"
    assert save_payload["roleId"] == "136"
    assert save_payload["taskNextId"] is None
    assert save_payload["orderDetailDto"]["workingOrderCode"] == "FA2601"
    assert save_payload["orderDetailDto"]["processStatus"] is True
    assert save_payload["orderDetailDto"]["isSubmit"] is True
    assert save_payload["orderDetailDto"]["submitRemark"] == "审核通过"


def test_reject_skips_claim_when_already_doing(enabled, monkeypatch):
    detail = _detail(workflow_status="Doing")
    fake = _FakeApi()
    monkeypatch.setattr(module, "_JiangsuAuthenticatedApi", lambda source: fake)

    original_get = fake.get

    async def get_with_detail(path, params):
        fake.gets.append((path, list(params)))
        if path == module._LIST_PATH:
            return {"result": {"items": [
                {"id": 71746, "workingOrderCode": "FA2601", "uniqueCode": "320382004"},
            ]}}
        return {"result": [detail]}

    fake.get = get_with_detail
    import asyncio

    outcome = asyncio.run(module.submit_review_decision(
        "FA2601", action="reject", approved=False, comment="处置记录不完整"))
    assert outcome["status"] == "synced"
    assert [path for path, _ in fake.posts] == [module._SAVE_ORDER_PATH]
    _, save_payload = fake.posts[0]
    assert save_payload["orderDetailDto"]["processStatus"] is False
    assert save_payload["orderDetailDto"]["submitRemark"] == "处置记录不完整"
    assert save_payload["taskPreviousId"] == "4987679e-2f44-4291-bb7a-9e7041024136"


def test_closed_order_is_skipped(enabled, monkeypatch):
    detail = _detail(order_status="Finish")
    fake = _FakeApi()
    monkeypatch.setattr(module, "_JiangsuAuthenticatedApi", lambda source: fake)

    async def get_with_detail(path, params):
        fake.gets.append((path, list(params)))
        if path == module._LIST_PATH:
            return {"result": {"items": [
                {"id": 71746, "workingOrderCode": "FA2601", "uniqueCode": "320382004"},
            ]}}
        return {"result": [detail]}

    fake.get = get_with_detail
    import asyncio

    outcome = asyncio.run(module.submit_review_decision(
        "FA2601", action="confirm", approved=True, comment="确认"))
    assert outcome["status"] == "skipped"
    assert fake.posts == []


def test_platform_failure_returns_failed_without_raising(enabled, monkeypatch):
    fake = _FakeApi(fail_on_save=True)
    monkeypatch.setattr(module, "_JiangsuAuthenticatedApi", lambda source: fake)
    import asyncio

    outcome = asyncio.run(module.submit_review_decision(
        "FA2601", action="confirm", approved=True, comment="通过"))
    assert outcome["status"] == "failed"
    assert "平台写回失败" in outcome["detail"]


def test_missing_order_reports_failed(enabled, monkeypatch):
    fake = _FakeApi()

    async def get_empty(path, params):
        fake.gets.append((path, list(params)))
        if path == module._LIST_PATH:
            return {"result": {"items": []}}
        return {"result": []}

    fake.get = get_empty
    monkeypatch.setattr(module, "_JiangsuAuthenticatedApi", lambda source: fake)
    import asyncio

    outcome = asyncio.run(module.submit_review_decision(
        "FA9999", action="confirm", approved=True, comment="通过"))
    assert outcome["status"] == "failed"
    assert "FA9999" in outcome["detail"]


def test_platform_sync_operation_mapping():
    assert module.platform_sync_result_operation({"status": "disabled"}) is None
    operation = module.platform_sync_result_operation({
        "status": "synced", "action": "confirm", "work_order_code": "FA2601",
        "detail": "省中心审核节点通过", "at": "2026-10-23T10:00:00+08:00",
    })
    assert operation["action"] == "platform_sync"
    assert operation["source"] == "task_review_decision"
    assert operation["platform"]["sync_status"] == "synced"
    assert operation["platform"]["work_order_code"] == "FA2601"


def test_audit_log_records_every_attempt(enabled):
    registry = module.get_data_registry()
    audit_file = registry / "work_order_platform_sync.jsonl"
    assert not audit_file.exists() or audit_file.read_text(encoding="utf-8") == ""
    import asyncio
    from app.tools.jiangsu.platform_workflow import _audit_event

    _audit_event({"status": "synced", "work_order_code": "FA2601"})
    lines = [json.loads(line) for line in
             audit_file.read_text(encoding="utf-8").splitlines() if line]
    assert lines and lines[-1]["work_order_code"] == "FA2601"

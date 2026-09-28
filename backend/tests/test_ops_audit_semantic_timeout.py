import asyncio
import json
import time

import pytest
import httpx

from app.services.ops_audit.semantic import reviewer
from app.services.llm_service import LLMService
from config.settings import settings


def test_semantic_batch_timeout_returns_partial_results(monkeypatch):
    def slow_no_device_batch(*args, **kwargs):
        raise TimeoutError("single model batch timed out")

    def fast_pm_tape_batch(tasks, audit_records, dataset_orders, details_by_code, rf_forms_by_code):
        task = tasks[0]
        code = str(task["working_order_code"])
        return {
            code: reviewer._build_semantic_task_result(
                task,
                audit_records.get(code, {}),
                dataset_orders.get(code, {}),
                "cleared",
                "fast batch completed",
                0.8,
                {
                    "is_complete": True,
                    "has_cause": True,
                    "has_action": True,
                    "has_result": True,
                    "problem_description": "",
                    "confidence": 0.8,
                    "remark": "ok",
                },
                [],
                "ok",
            )
        }

    monkeypatch.setattr(reviewer, "_review_no_device_tasks_batch", slow_no_device_batch)
    monkeypatch.setattr(reviewer, "_review_pm_tape_usage_tasks_batch", fast_pm_tape_batch)

    audit = {
        "records": [
            _record_with_issue("WO-SLOW", "RF_NO_DEVICE_WITHOUT_REMARK"),
            _record_with_issue("WO-FAST", "RF_PM_TAPE_USAGE_INVALID"),
        ]
    }
    start = time.monotonic()

    results = reviewer.build_semantic_review_results(audit, {"orders": [], "details": [], "rf_forms": {}})

    elapsed = time.monotonic() - start
    by_code = {result["working_order_code"]: result for result in results["results"]}
    assert elapsed < 1
    assert by_code["WO-FAST"]["review_status"] == "completed"
    assert by_code["WO-SLOW"]["review_status"] == "timeout"
    assert by_code["WO-SLOW"]["judgment"] == "needs_followup"


def test_queued_batches_each_get_their_own_call_timeout(monkeypatch):
    monkeypatch.setattr(reviewer, "SEMANTIC_BATCH_MAX_ITEMS", 1)
    monkeypatch.setattr(reviewer, "SEMANTIC_LLM_CALL_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(reviewer.llm_service, "base_url", "test")
    monkeypatch.setattr(reviewer.llm_service, "model", "test")

    class FakeService:
        def __init__(self, *, request_timeout_seconds):
            assert request_timeout_seconds == 0.2

        async def call_llm_with_json_response(self, **kwargs):
            await asyncio.sleep(0.08)
            return {"ok": True}

    def review_batch(tasks, *args):
        result = reviewer._call_semantic_llm_json("test", "evidence")
        assert result == {"ok": True}
        return {task["working_order_code"]: {"working_order_code": task["working_order_code"], "judgment": "cleared"} for task in tasks}

    monkeypatch.setattr(reviewer, "LLMService", FakeService)
    monkeypatch.setattr(reviewer, "_review_no_device_tasks_batch", review_batch)
    audit = {"records": [_record_with_issue(f"WO-{i}", "RF_NO_DEVICE_WITHOUT_REMARK") for i in range(16)]}
    start = time.monotonic()
    result = reviewer.build_semantic_review_results(audit)
    assert time.monotonic() - start > 0.2
    assert len(result["results"]) == 16
    assert all(item["judgment"] == "cleared" for item in result["results"])


def test_single_call_timeout_cancels_request(monkeypatch):
    cancelled = []
    monkeypatch.setattr(reviewer, "SEMANTIC_LLM_CALL_TIMEOUT_SECONDS", 0.02)

    class SlowService:
        def __init__(self, *, request_timeout_seconds):
            assert request_timeout_seconds == 0.02

        async def call_llm_with_json_response(self, **kwargs):
            try:
                await asyncio.sleep(1)
            finally:
                cancelled.append(True)

    monkeypatch.setattr(reviewer, "LLMService", SlowService)
    with pytest.raises(TimeoutError):
        reviewer._run_async_llm_json("test")
    assert cancelled == [True]


def test_split_request_continues_after_one_batch_times_out(monkeypatch):
    monkeypatch.setattr(reviewer, "SEMANTIC_BATCH_MAX_ITEMS", 1)
    monkeypatch.setattr(reviewer.llm_service, "base_url", "test")
    monkeypatch.setattr(reviewer.llm_service, "model", "test")
    seen = []

    def call(prompt):
        item = json.loads(json.loads(prompt.split("\n\n", 1)[1])["text"])["items"][0]
        seen.append(item)
        if item == 2:
            raise TimeoutError("test")
        return {"results": [{"id": item}]}

    monkeypatch.setattr(reviewer, "_run_async_llm_json", call)
    result = reviewer._call_semantic_llm_json("test", json.dumps({"items": [1, 2, 3]}))
    assert seen == [1, 2, 3]
    assert result == {"results": [{"id": 1}, {"id": 3}]}


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["json", "chat"])
async def test_transport_timeout_override_is_local_to_audit_service(monkeypatch, api):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_mode", "chat_completions")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(settings, "deepseek_base_url", "https://test.invalid/v1")
    monkeypatch.setattr(settings, "llm_request_timeout_seconds", 180)
    captured = []
    client_class = httpx.AsyncClient

    def client(**kwargs):
        captured.append(kwargs["timeout"])
        return client_class(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]},
        )))

    monkeypatch.setattr(httpx, "AsyncClient", client)
    for service in (LLMService(), LLMService(request_timeout_seconds=240)):
        if api == "json":
            assert await service._call_llm_with_json_response_once("test", max_retries=1) == {"ok": True}
        else:
            await service._chat_completions_create(messages=[], tools=None, max_tokens=None, temperature=0, system=None)
    assert captured == [180, 240]
    assert settings.llm_request_timeout_seconds == 180


def _record_with_issue(code: str, rule_id: str) -> dict:
    issue = {
        "rule_id": rule_id,
        "severity": "中",
        "category": "规范性问题",
        "assessment": "candidate_issue",
        "field": f"rf.{rule_id}",
        "message": rule_id,
        "evidence": "{}",
    }
    return {
        "working_order_code": code,
        "station_id": "1",
        "order_type": "Check",
        "maintenance_type": "Week",
        "finish_time": "2026-05-27 10:00:00",
        "audit_level": "待确认问题",
        "attachment_count": 0,
        "workflow_steps": [],
        "rf_tables": [],
        "issues": [issue],
        "scoring_issues": [issue],
    }

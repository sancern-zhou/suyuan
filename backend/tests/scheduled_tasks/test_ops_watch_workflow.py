import pytest

from app.scheduled_tasks.models import ScheduledTask
from app.scheduled_tasks.models.execution import ExecutionStatus, TaskExecution
from app.scheduled_tasks.workflow_tasks import execute_workflow_task, registered_workflows
from app.tools.jiangsu.ops_watch_notification import run_ops_watch_workflow


def _workflow_data(conclusion="昨日全网巡检覆盖100个站点，其中2个站点存在异常，涉及1个城市。"):
    return {
        "period": "day",
        "period_label": "昨日",
        "station_count": 100,
        "alarm_station_count": 2,
        "alarm_city_count": 1,
        "city_statistics": [{"city": "南京市", "count": 2}],
        "category_statistics": [{"category": "动环", "count": 2}],
        "issues": [
            {"station_name": "站点甲", "station_code": "C001", "city": "南京市", "category": "动环", "raw": {"x": 1}},
            {"station_name": "站点乙", "station_code": "C002", "city": "南京市", "category": "动环", "raw": {"x": 2}},
        ],
        "conclusion": conclusion,
    }


def _task() -> ScheduledTask:
    return ScheduledTask(
        task_id="jiangsu_network_inspection_watch",
        name="江苏全网巡检值守",
        description="每日汇总站房巡检异常",
        execution_mode="workflow",
        workflow_name="jiangsu_network_inspection_workflow",
        workflow_args={"period": "day"},
        schedule_type="daily_8am",
        prompt="根据巡检统计证据生成 200-300 字当日值守短结论。",
    )


def _execution() -> TaskExecution:
    return TaskExecution(
        execution_id="exec_1",
        task_id="jiangsu_network_inspection_watch",
        task_name="江苏全网巡检值守",
        status=ExecutionStatus.RUNNING,
        total_steps=1,
    )


def _patch_workflow(monkeypatch, data):
    class FakeWorkflow:
        async def execute(self, **kwargs):
            assert kwargs == {"period": "day"}
            return {"success": True, "data": data, "summary": data["conclusion"]}

    monkeypatch.setattr(
        "app.tools.workflow.jiangsu_network_inspection_workflow.JiangsuNetworkInspectionWorkflow",
        FakeWorkflow,
    )


def _patch_llm(monkeypatch, text, calls=None):
    from app.services.llm_service import llm_service

    async def fake_chat(messages, system=None, max_tokens=None, **kwargs):
        if calls is not None:
            calls.append({"system": system, "user": messages[0]["content"]})
        return {"content": [{"type": "text", "text": text}]}

    monkeypatch.setattr(llm_service, "chat_anthropic", fake_chat)


def _patch_review(monkeypatch, submissions=None):
    def fake_submit(payload, source):
        if submissions is not None:
            submissions.append({"payload": payload, "source": source})
        return {"review_id": "review_1"}

    monkeypatch.setattr(
        "app.tools.jiangsu.ops_watch_notification.submit_review",
        fake_submit,
    )


@pytest.mark.asyncio
async def test_llm_conclusion_reaches_review_payload(monkeypatch):
    data = _workflow_data()
    calls, submissions = [], []
    _patch_workflow(monkeypatch, data)
    _patch_llm(
        monkeypatch,
        "昨日全网巡检覆盖100个站点，其中2个站点存在异常，涉及1个城市，异常集中在南京市，"
        "以动环异常为主，建议优先核查异常数量较多的站点并人工确认现场情况。" * 2,
        calls,
    )
    _patch_review(monkeypatch, submissions)

    result = await run_ops_watch_workflow(task=_task(), execution=_execution(), event=None)

    assert result["tool_call_details"]["conclusion_source"] == "llm"
    assert submissions[0]["payload"]["summary"] == result["final_message"]
    assert submissions[0]["payload"]["category"] == "运维值守"
    assert submissions[0]["payload"]["decision"] == "needs_action"
    assert submissions[0]["source"]["task_id"] == "jiangsu_network_inspection_watch"
    assert result["data_ids"] == ["review_1"]
    # 原始站点行不进入 LLM 提示词，压缩证据保留站点名/城市/类别。
    assert "raw" not in calls[0]["user"]
    assert "站点甲" in calls[0]["user"]


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_template_conclusion(monkeypatch):
    from app.services.llm_service import llm_service

    _patch_workflow(monkeypatch, _workflow_data())
    _patch_review(monkeypatch, submissions := [])

    async def broken_chat(*args, **kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(llm_service, "chat_anthropic", broken_chat)
    result = await run_ops_watch_workflow(task=_task(), execution=_execution(), event=None)

    assert result["tool_call_details"]["conclusion_source"] == "template"
    assert result["final_message"] == _workflow_data()["conclusion"]
    assert submissions[0]["payload"]["summary"] == _workflow_data()["conclusion"]


@pytest.mark.asyncio
async def test_short_llm_output_falls_back(monkeypatch):
    _patch_workflow(monkeypatch, _workflow_data())
    _patch_llm(monkeypatch, "太短")
    _patch_review(monkeypatch, submissions := [])

    result = await run_ops_watch_workflow(task=_task(), execution=_execution(), event=None)

    assert result["tool_call_details"]["conclusion_source"] == "template"
    assert "问题清单" in submissions[0]["payload"]["comment"]


@pytest.mark.asyncio
async def test_workflow_failure_raises(monkeypatch):
    class FakeWorkflow:
        async def execute(self, **kwargs):
            return {"success": False, "summary": "接口失败"}

    monkeypatch.setattr(
        "app.tools.workflow.jiangsu_network_inspection_workflow.JiangsuNetworkInspectionWorkflow",
        FakeWorkflow,
    )
    with pytest.raises(RuntimeError):
        await run_ops_watch_workflow(task=_task(), execution=_execution(), event=None)


@pytest.mark.asyncio
async def test_registry_dispatches_and_injects_history(monkeypatch):
    seen = {}

    async def handler(task, execution, event, history_section=None):
        seen["history"] = history_section
        return {"summary": "ok", "final_message": "ok", "data_ids": [], "tool_call_details": {}}

    from app.scheduled_tasks import workflow_tasks

    monkeypatch.setitem(workflow_tasks._WORKFLOW_HANDLERS, "demo_workflow", handler)
    task = _task()
    task.workflow_name = "demo_workflow"
    result = await execute_workflow_task(task, _execution(), event=None, history_section="记忆")
    assert result["summary"] == "ok"
    assert seen["history"] == "记忆"
    assert "jiangsu_network_inspection_workflow" in registered_workflows()


@pytest.mark.asyncio
async def test_unregistered_workflow_rejected():
    task = _task()
    task.workflow_name = "missing_workflow"
    with pytest.raises(RuntimeError, match="未注册的 workflow"):
        await execute_workflow_task(task, _execution())

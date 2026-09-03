import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.tool_adapter import get_tool_schemas
from app.agent.runtime.agent_runtime import AgentRuntime
from app.scheduled_tasks.history_retrieval import search_history_cases
from app.scheduled_tasks.storage.task_case_storage import TaskCaseStorage
from app.tools.scheduled_tasks.search_scheduled_task_history import (
    SearchScheduledTaskHistoryTool,
)


def _schema_names(schemas):
    return {
        schema.get("name") or schema.get("function", {}).get("name")
        for schema in schemas
    }


def test_search_history_cases_scores_structured_fields(tmp_path):
    storage = TaskCaseStorage("task_history_search", base_dir=tmp_path)
    storage.append_case(
        {
            "execution_id": "exec_old",
            "status": "succeeded",
            "started_at": "2026-08-30T08:00:00",
            "trigger": {"type": "schedule"},
            "distilled": {
                "case_brief": "例行日报，未发现明显异常",
                "findings": ["O3 浓度平稳"],
            },
        }
    )
    storage.append_case(
        {
            "execution_id": "exec_match",
            "status": "succeeded",
            "started_at": "2026-09-01T08:00:00",
            "trigger": {
                "type": "event",
                "context_digest": "station_exceedance_confirmed; station_name=站点A; pollutant=PM10",
            },
            "distilled": {
                "case_brief": "站点A PM10 超标，扬尘为主因",
                "findings": ["站点A PM10 超标 1.4 倍", "上风向施工扬尘贡献较高"],
            },
            "outputs": [{"kind": "report", "ref": "rpt_pm10"}],
        }
    )

    result = search_history_cases(storage, query="站点A PM10 扬尘", limit=2)

    assert result["count"] == 1
    assert result["matches"][0]["execution_id"] == "exec_match"
    assert result["matches"][0]["case_brief"] == "站点A PM10 超标，扬尘为主因"
    assert "PM10" in result["matches"][0]["matched_terms"]


@pytest.mark.asyncio
async def test_search_scheduled_task_history_requires_task_context():
    tool = SearchScheduledTaskHistoryTool()

    result = await tool.execute(query="站点A")

    assert result["success"] is False
    assert "定时任务执行上下文" in result["summary"]


@pytest.mark.asyncio
async def test_search_scheduled_task_history_uses_context_task_id(tmp_path, monkeypatch):
    storage = TaskCaseStorage("task_ctx", base_dir=tmp_path)
    storage.append_case(
        {
            "execution_id": "exec_ctx",
            "status": "succeeded",
            "started_at": "2026-09-01T08:00:00",
            "trigger": {"type": "schedule"},
            "distilled": {
                "case_brief": "臭氧日报确认午后升高",
                "findings": ["O3 午后峰值持续 3 小时"],
            },
        }
    )

    import app.tools.scheduled_tasks.search_scheduled_task_history as tool_module

    monkeypatch.setattr(
        tool_module,
        "TaskCaseStorage",
        lambda task_id: TaskCaseStorage(task_id, base_dir=tmp_path),
    )
    context = SimpleNamespace(
        scheduled_task_context={
            "task_id": "task_ctx",
            "task_name": "臭氧日报",
            "execution_id": "exec_current",
            "history_learning": {
                "enabled": True,
                "active_retrieval_enabled": True,
                "active_retrieval_max_results": 1,
            },
        }
    )

    result = await tool_module.SearchScheduledTaskHistoryTool().execute(
        context,
        query="O3 午后",
        limit=5,
    )

    assert result["success"] is True
    assert result["data"]["task_id"] == "task_ctx"
    assert result["data"]["count"] == 1
    assert result["data"]["matches"][0]["execution_id"] == "exec_ctx"


def test_scheduled_history_tool_not_in_normal_expert_schema():
    names = _schema_names(get_tool_schemas(mode="expert"))

    assert "search_scheduled_task_history" not in names


def test_extra_tool_names_expose_scheduled_history_schema_for_one_run():
    allowed = list(get_tools_by_mode("expert").keys()) + ["search_scheduled_task_history"]

    schemas = get_tool_schemas(mode="expert", allowed_tool_names=allowed)
    names = _schema_names(schemas)
    schema = next(
        schema for schema in schemas
        if (schema.get("name") or schema.get("function", {}).get("name"))
        == "search_scheduled_task_history"
    )
    description = schema.get("description") or schema.get("function", {}).get("description", "")

    assert "search_scheduled_task_history" in names
    assert "应主动调用" in description
    assert "不能替代本次事实核查" in description


def test_agent_runtime_only_appends_extra_tools_when_configured():
    runtime = object.__new__(AgentRuntime)
    runtime.executor = SimpleNamespace(tool_registry={"custom_tool": object()})
    runtime.config = SimpleNamespace(extra_tool_names=None)

    assert runtime._allowed_tool_names_for_state(SimpleNamespace(mode="expert")) is None
    assert runtime._allowed_tool_names_for_state(SimpleNamespace(mode="custom")) == ["custom_tool"]

    runtime.config = SimpleNamespace(extra_tool_names=["search_scheduled_task_history"])
    allowed = runtime._allowed_tool_names_for_state(SimpleNamespace(mode="expert"))

    assert "search_scheduled_task_history" in allowed
    assert set(get_tools_by_mode("expert").keys()).issubset(set(allowed))


def test_scheduled_history_tool_registration_is_compliant():
    from app.tools import global_tool_registry

    compliance = global_tool_registry.validate_tool_compliance("search_scheduled_task_history")
    metadata = global_tool_registry.get_tool_info("search_scheduled_task_history")["metadata"]

    assert compliance["valid"] is True
    assert compliance["errors"] == []
    assert metadata["data_type"] == "scheduled_task_history"

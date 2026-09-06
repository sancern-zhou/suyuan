"""
定时任务历史执行记忆测试
覆盖：案例库存储、确定性案例提取、执行前注入、执行后收尾（成功/降级/超时）、执行器集成
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scheduled_tasks import history_learning
from app.scheduled_tasks.executor.task_executor import ScheduledTaskExecutor
from app.scheduled_tasks.history_learning import (
    _consolidation_call,
    build_case,
    build_history_section,
    finalize_execution,
)
from app.scheduled_tasks.models.event import TaskEvent
from app.scheduled_tasks.models.execution import ExecutionStatus, TaskExecution
from app.scheduled_tasks.models.task import HistoryLearningConfig, ScheduledTask
from app.scheduled_tasks.storage import ExecutionStorage, TaskStorage
from app.scheduled_tasks.storage.task_case_storage import TaskCaseStorage


def _make_task(**overrides) -> ScheduledTask:
    kwargs = dict(
        task_id="task_history_test",
        name="站点污染分析",
        description="分析站点污染情况并生成报告",
        execution_mode="expert",
        schedule_type="daily_8am",
        enabled=True,
        prompt="分析站点污染情况，生成溯源报告",
        timeout_seconds=60,
    )
    kwargs.update(overrides)
    return ScheduledTask(**kwargs)


def _make_execution(status: ExecutionStatus = ExecutionStatus.SUCCESS) -> TaskExecution:
    return TaskExecution(
        execution_id="exec_history_test_001",
        task_id="task_history_test",
        task_name="站点污染分析",
        status=status,
        started_at=datetime(2026, 9, 1, 8, 0, 0),
        completed_at=datetime(2026, 9, 1, 8, 2, 14),
        duration_seconds=134.0,
        total_steps=1,
    )


def _make_event() -> TaskEvent:
    return TaskEvent(
        event_id="evt_001",
        event_type="station_exceedance_confirmed",
        attributes={"station_id": "1011A", "pollutant": "PM10"},
        payload={"city": "许昌市", "station_name": "站点A", "details": {"ignored": True}},
    )


def _agent_result() -> dict:
    return {
        "summary": "本次分析完成：站点A PM10 超标 1.4 倍，主要成因是扬尘",
        "data_ids": ["dataset:abc123"],
        "visuals": [{"visual_id": "vis_1", "title": "小时浓度曲线"}],
        "thoughts": ["先查数据"],
        "tool_calls": [
            {
                "tool": "create_report_package",
                "args": {},
                "success": True,
                "result": {"success": True, "data": {"report_id": "rpt_test_001"}},
            },
            {
                "tool": "query_air_quality",
                "args": {},
                "success": False,
                "result": "数据库连接超时",
            },
        ],
        "iterations": 5,
    }


class TestTaskCaseStorage:
    def test_append_and_recent_cases(self, tmp_path):
        storage = TaskCaseStorage("task_x", base_dir=tmp_path)
        assert storage.case_count() == 0
        assert storage.recent_cases(3) == []
        for index in range(3):
            storage.append_case({"execution_id": f"exec_{index}", "status": "succeeded"})
        cases = storage.recent_cases(2)
        assert [case["execution_id"] for case in cases] == ["exec_1", "exec_2"]  # 时间正序
        assert storage.case_count() == 3

    def test_prune_keeps_latest(self, tmp_path):
        storage = TaskCaseStorage("task_x", base_dir=tmp_path)
        storage.MAX_CASES = 5
        for index in range(8):
            storage.append_case({"execution_id": f"exec_{index}"})
        assert storage.case_count() == 5
        assert storage.recent_cases(1)[0]["execution_id"] == "exec_7"

    def test_memory_roundtrip_and_delete(self, tmp_path):
        storage = TaskCaseStorage("task_x", base_dir=tmp_path)
        assert storage.read_memory() == ""
        storage.write_memory("# 任务记忆：x\n## 使命与背景\n测试", {"version": 1})
        assert "使命与背景" in storage.read_memory()
        assert storage.read_meta()["version"] == 1
        assert storage.delete() is True
        assert storage.case_count() == 0


class TestBuildCase:
    def test_success_case_extraction(self):
        case = build_case(_make_execution(), _make_event(), _agent_result())
        assert case["status"] == "succeeded"
        assert case["trigger"]["type"] == "event"
        assert case["trigger"]["event_type"] == "station_exceedance_confirmed"
        assert case["trigger"]["attributes"] == {
            "station_id": "1011A",
            "station_name": "站点A",
            "city": "许昌市",
            "pollutant": "PM10",
        }
        assert "details" not in case["trigger"]["attributes"]
        kinds = {(item["kind"], item["ref"]) for item in case["outputs"]}
        assert ("report", "rpt_test_001") in kinds
        assert ("dataset", "dataset:abc123") in kinds
        assert ("visual", "vis_1") in kinds
        assert any("query_air_quality" in error for error in case["errors"])

    def test_failed_and_scheduled_trigger(self):
        execution = _make_execution(status=ExecutionStatus.TIMEOUT)
        execution.error_message = "Task timeout after 60s"
        case = build_case(execution, None, {})
        assert case["status"] == "timeout"
        assert case["trigger"] == {"type": "schedule"}
        assert case["errors"] == ["Task timeout after 60s"]
        assert "outputs" not in case


class TestBuildHistorySection:
    def test_no_history_returns_none(self, tmp_path):
        assert build_history_section(_make_task(), TaskCaseStorage("t", base_dir=tmp_path)) is None

    def test_disabled_returns_none(self, tmp_path):
        task = _make_task(history_learning=HistoryLearningConfig(enabled=False))
        storage = TaskCaseStorage(task.task_id, base_dir=tmp_path)
        storage.write_memory("# 任务记忆", {"version": 1})
        assert build_history_section(task, storage) is None

    def test_renders_memory_and_cases(self, tmp_path):
        task = _make_task()
        storage = TaskCaseStorage(task.task_id, base_dir=tmp_path)
        storage.write_memory("# 任务记忆：站点污染分析\n## 经验教训\n先查分钟数据", {"version": 1})
        storage.append_case(
            {"execution_id": "e1", "status": "succeeded", "started_at": "2026-09-01T08:00:00",
             "distilled": {"case_brief": "PM10 超标，扬尘为主因", "findings": []}}
        )
        section = build_history_section(task, storage)
        assert "## 历史执行记忆" in section
        assert "经验教训" in section
        assert "PM10 超标，扬尘为主因" in section
        assert "累计 1 次执行" in section

    def test_memory_budget_truncation(self, tmp_path):
        task = _make_task(history_learning=HistoryLearningConfig(memory_char_budget=200))
        storage = TaskCaseStorage(task.task_id, base_dir=tmp_path)
        storage.write_memory("# 任务记忆\n" + "长" * 500, {"version": 1})
        section = build_history_section(task, storage)
        assert "已截断" in section


class TestFinalizeExecution:
    def _patch_consolidation(self, monkeypatch, value=None, error=None, delay=0.0):
        async def fake_call(**kwargs):
            if delay:
                await asyncio.sleep(delay)
            if error:
                raise error
            return value

        monkeypatch.setattr(history_learning, "_consolidation_call", fake_call)

    def test_success_writes_distilled_case_and_memory(self, tmp_path, monkeypatch):
        task = _make_task()
        storage = TaskCaseStorage(task.task_id, base_dir=tmp_path)
        distilled = {"case_brief": "本次完成分析", "findings": ["PM10 超标 1.4 倍"]}
        memory_md = "# 任务记忆：站点污染分析\n## 使命与背景\n分析站点污染"
        self._patch_consolidation(monkeypatch, value=(distilled, memory_md))

        case = asyncio.run(
            finalize_execution(task, _make_execution(), _make_event(), _agent_result(), storage)
        )
        assert case["distilled"] == distilled
        assert "summary" not in case  # 蒸馏成功时不写兜底 summary
        stored = storage.recent_cases(1)[0]
        assert stored["distilled"]["case_brief"] == "本次完成分析"
        assert "使命与背景" in storage.read_memory()
        assert storage.read_meta()["last_consolidation_status"] == "success"

    def test_degraded_on_error_keeps_old_memory(self, tmp_path, monkeypatch):
        task = _make_task()
        storage = TaskCaseStorage(task.task_id, base_dir=tmp_path)
        storage.write_memory("# 旧记忆", {"version": 3})
        self._patch_consolidation(monkeypatch, error=RuntimeError("llm down"))

        case = asyncio.run(
            finalize_execution(task, _make_execution(), None, _agent_result(), storage)
        )
        assert "distilled" not in case
        assert case["summary"].startswith("本次分析完成")
        assert storage.read_memory() == "# 旧记忆"  # 记忆不被破坏性覆盖
        meta = storage.read_meta()
        assert meta["last_consolidation_status"] == "failed"
        assert meta["consolidation_failures"] == 1
        assert meta["last_consolidation_error"] == "llm down"

    def test_timeout_degrades(self, tmp_path, monkeypatch):
        task = _make_task(history_learning=HistoryLearningConfig(consolidation_timeout_seconds=1))
        storage = TaskCaseStorage(task.task_id, base_dir=tmp_path)
        self._patch_consolidation(monkeypatch, delay=1.3)

        case = asyncio.run(
            finalize_execution(task, _make_execution(), None, {}, storage)
        )
        assert "distilled" not in case
        assert storage.case_count() == 1
        assert storage.read_meta()["last_consolidation_status"] == "failed"


class TestConsolidationCall:
    def test_uses_protocol_aware_json_api(self, monkeypatch):
        calls = []
        response = {
            "case": {
                "case_brief": "完成站点分析",
                "findings": ["PM10 超标"],
                "cities": "许昌市",
                "stations": ["站点A", "站点A", " 站点B "],
                "pollutants": ["PM10"],
                "event_types": ["station_exceedance_confirmed"],
            },
            "memory": "# 任务记忆：站点污染分析\n## 使命与背景\n分析污染",
        }

        class FakeLLMService:
            temperature = None

            async def call_llm_with_json_response(self, prompt, max_retries=2):
                calls.append((prompt, max_retries, self.temperature))
                return response

        monkeypatch.setattr("app.services.llm_service.LLMService", FakeLLMService)

        result = asyncio.run(
            _consolidation_call(
                task=_make_task(),
                old_memory="",
                case=build_case(_make_execution(), None, _agent_result()),
                agent_result=_agent_result(),
                memory_budget=6000,
            )
        )

        assert result[0]["case_brief"] == "完成站点分析"
        assert result[0]["cities"] == ["许昌市"]
        assert result[0]["stations"] == ["站点A", "站点B"]
        assert result[0]["pollutants"] == ["PM10"]
        assert "event_types" not in result[0]
        assert result[1].startswith("# 任务记忆")
        assert len(calls) == 1
        assert calls[0][1:] == (1, 0.2)

    def test_event_attributes_replace_redundant_llm_dimensions(self, monkeypatch):
        response = {
            "case": {
                "case_brief": "完成站点分析",
                "findings": ["PM10 超标"],
                "cities": ["许昌市"],
                "stations": ["站点A"],
                "pollutants": ["PM10"],
            },
            "memory": "# 任务记忆：站点污染分析\n## 使命与背景\n分析污染",
        }

        class FakeLLMService:
            async def call_llm_with_json_response(self, prompt, max_retries=2):
                return response

        monkeypatch.setattr("app.services.llm_service.LLMService", FakeLLMService)
        case = build_case(_make_execution(), _make_event(), _agent_result())

        distilled, _ = asyncio.run(
            _consolidation_call(
                task=_make_task(),
                old_memory="",
                case=case,
                agent_result=_agent_result(),
                memory_budget=6000,
            )
        )

        assert distilled == {"case_brief": "完成站点分析", "findings": ["PM10 超标"]}

    def test_omits_invalid_optional_dimensions(self):
        content = {
            "case": {
                "case_brief": "完成分析",
                "findings": [],
                "cities": None,
                "stations": [],
                "pollutants": {"name": "PM10"},
                "event_types": ["", None, False],
            },
            "memory": "# 任务记忆\n## 使命与背景\n测试任务",
        }

        parsed = history_learning._parse_consolidation_response(content)

        assert parsed is not None
        assert parsed[0] == {"case_brief": "完成分析", "findings": []}

    def test_propagates_last_provider_error_after_retry(self, monkeypatch):
        attempts = 0

        class FakeLLMService:
            temperature = None

            async def call_llm_with_json_response(self, prompt, max_retries=2):
                nonlocal attempts
                attempts += 1
                raise RuntimeError("401 Unauthorized")

        monkeypatch.setattr("app.services.llm_service.LLMService", FakeLLMService)

        with pytest.raises(RuntimeError, match="401 Unauthorized"):
            asyncio.run(
                _consolidation_call(
                    task=_make_task(),
                    old_memory="",
                    case=build_case(_make_execution(), _make_event(), _agent_result()),
                    agent_result=_agent_result(),
                    memory_budget=6000,
                )
            )

        assert attempts == 2


class _StubAgent:
    async def analyze(self, prompt, session_id=None, manual_mode=None, **kwargs):
        assert "## 历史执行记忆" in prompt  # 二次执行必须注入历史
        yield {"type": "thought", "data": {"thought": "先查数据"}}
        yield {"type": "tool_call", "data": {"tool_name": "create_report_package", "input": {}}}
        yield {
            "type": "tool_result",
            "data": {"result": {"success": True, "data": {"report_id": "rpt_run_001"}}, "is_error": False},
        }
        yield {"type": "final_response", "content": "本次执行完成，结论正常"}


class _StubPersistence:
    async def persist_agent_session(self, **kwargs):
        return True

    async def publish_conversation(self, **kwargs):
        return None

    async def ensure_terminal_session(self, **kwargs):
        return None


class TestExecutorIntegration:
    def test_execute_task_finalizes_and_injects(self, tmp_path, monkeypatch):
        task = _make_task()

        async def fake_consolidation(**kwargs):
            distilled = {"case_brief": "本次完成站点分析", "findings": ["结论正常"]}
            return distilled, "# 任务记忆：站点污染分析\n## 使命与背景\n分析污染"

        monkeypatch.setattr(history_learning, "_consolidation_call", fake_consolidation)

        task_storage = TaskStorage(storage_dir=str(tmp_path))
        task_storage.create(task)
        execution_storage = ExecutionStorage(storage_dir=str(tmp_path))
        case_storage = TaskCaseStorage(task.task_id, base_dir=tmp_path / "memory")
        # 预置一段历史，验证第二次执行会注入
        case_storage.write_memory("# 任务记忆：站点污染分析\n## 当前关注\n站点A 持续超标", {"version": 1})

        executor = ScheduledTaskExecutor(
            task_storage=task_storage,
            execution_storage=execution_storage,
            agent_factory=lambda **kwargs: _StubAgent(),
            conversation_persistence=_StubPersistence(),
        )
        executor._case_storages[task.task_id] = case_storage

        execution = asyncio.run(executor.execute_task(task))

        assert execution.status == ExecutionStatus.SUCCESS
        assert "## 历史执行记忆" in execution.steps[0].agent_prompt
        assert "站点A 持续超标" in execution.steps[0].agent_prompt
        cases = case_storage.recent_cases(1)
        assert len(cases) == 1
        assert cases[0]["execution_id"] == execution.execution_id
        assert cases[0]["distilled"]["case_brief"] == "本次完成站点分析"
        assert {"kind": "report", "ref": "rpt_run_001"} in cases[0]["outputs"]
        assert "使命与背景" in case_storage.read_memory()
        assert task_storage.get(task.task_id).total_runs == 1

    def test_active_history_retrieval_is_schema_only_extra_tool(self, tmp_path, monkeypatch):
        task = _make_task(
            history_learning=HistoryLearningConfig(
                active_retrieval_enabled=True,
                active_retrieval_max_results=2,
            )
        )

        async def fake_consolidation(**kwargs):
            distilled = {"case_brief": "本次完成站点分析", "findings": ["结论正常"]}
            return distilled, "# 任务记忆：站点污染分析\n## 使命与背景\n分析污染"

        monkeypatch.setattr(history_learning, "_consolidation_call", fake_consolidation)
        calls = []

        class CaptureAgent:
            async def analyze(self, prompt, session_id=None, **kwargs):
                calls.append({"prompt": prompt, "session_id": session_id, "kwargs": kwargs})
                yield {"type": "final_response", "content": "本次执行完成"}

        task_storage = TaskStorage(storage_dir=str(tmp_path))
        task_storage.create(task)
        execution_storage = ExecutionStorage(storage_dir=str(tmp_path))
        case_storage = TaskCaseStorage(task.task_id, base_dir=tmp_path / "memory")
        case_storage.append_case(
            {
                "execution_id": "exec_previous",
                "status": "succeeded",
                "started_at": "2026-08-31T08:00:00",
                "distilled": {"case_brief": "旧案例", "findings": []},
            }
        )
        executor = ScheduledTaskExecutor(
            task_storage=task_storage,
            execution_storage=execution_storage,
            agent_factory=lambda **kwargs: CaptureAgent(),
            conversation_persistence=_StubPersistence(),
        )
        executor._case_storages[task.task_id] = case_storage

        execution = asyncio.run(executor.execute_task(task))

        assert execution.status == ExecutionStatus.SUCCESS
        assert "## 历史案例主动检索" not in calls[0]["prompt"]
        assert calls[0]["kwargs"]["extra_tool_names"] == ["search_scheduled_task_history"]
        scheduled_context = calls[0]["kwargs"]["runtime_metadata"]["scheduled_task"]
        assert scheduled_context["task_id"] == task.task_id
        assert scheduled_context["execution_id"] == execution.execution_id
        assert scheduled_context["history_learning"]["active_retrieval_enabled"] is True

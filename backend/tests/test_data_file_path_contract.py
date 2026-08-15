from pathlib import Path

import pytest

from app.agent.context.data_files import resolve_data_path, to_data_path
from app.agent.context.data_context_manager import DataContextManager
from app.agent.context.execution_context import ExecutionContext
from app.agent.memory.hybrid_manager import HybridMemoryManager
from app.agent.tool_adapter import get_tool_schemas
from app.agent.prompts.query_prompt import build_query_prompt
from app.tools.utility.read_file_tool import ReadFileTool
from app.tools.utility.execute_python_tool import ExecutePythonTool
from config.settings import settings


def test_model_facing_tool_schemas_have_no_data_identifier_protocol():
    schemas = get_tool_schemas()
    serialized = str(schemas)
    assert "data_id" not in serialized
    assert "read_data_registry" not in serialized
    assert "read_data_file" not in serialized
    by_name = {schema["name"]: schema for schema in schemas}
    assert "read_data_file" not in by_name
    assert "大量结果的处理使用 execute_python" in by_name["read_file"]["description"]
    assert "全量扫描" in by_name["execute_python"]["description"]


def test_tool_schemas_route_session_data_away_from_read_file():
    file_schema = ReadFileTool().get_function_schema()
    python_schema = ExecutePythonTool().get_function_schema()

    assert "大量结果使用 execute_python" in file_schema["description"]
    assert "大量数据文件使用 execute_python" in file_schema["parameters"]["properties"]["path"]["description"]
    assert "全量扫描" in python_schema["description"]


def test_data_tool_routing_is_in_schemas_not_query_system_prompt():
    prompt = build_query_prompt([])
    assert "read_data_file" not in prompt
    assert "execute_python" not in prompt
    assert "常规 limit" not in prompt


def test_session_path_is_absolute_and_cannot_cross_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_registry_dir", str(tmp_path))
    source = tmp_path / "sessions" / "agent_session_a" / "data" / "rows.json"
    source.parent.mkdir(parents=True)
    source.write_text("[]", encoding="utf-8")

    assert to_data_path(source) == str(source.resolve())
    assert resolve_data_path(str(source), session_id="a") == source.resolve()
    with pytest.raises(PermissionError):
        resolve_data_path(str(source), session_id="b")


def test_object_report_package_is_saved_as_a_session_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_registry_dir", str(tmp_path))
    memory = HybridMemoryManager("object_report", max_working_iterations=1)
    # HybridMemoryManager creates SessionMemory from the configured project
    # location, so align its session paths with the isolated test root.
    memory.session.session_dir = tmp_path / "sessions" / "agent_session_object_report"
    memory.session.data_dir = memory.session.session_dir / "data"
    memory.session.data_dir.mkdir(parents=True)
    context = ExecutionContext("object_report", 1, DataContextManager(memory))

    file_path = context.save_data({"kind": "report", "views": {"reporting": []}}, "report_package")

    assert Path(file_path).is_file()
    assert file_path in context.available_file_paths

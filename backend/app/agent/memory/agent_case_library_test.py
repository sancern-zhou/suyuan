import asyncio

from app.agent.memory.agent_case_library import AgentCaseLibrary
from app.tools.utility import agent_case_library_tool as tool_module


def test_agent_case_library_records_and_searches_agent_authored_cases(tmp_path, monkeypatch):
    libraries = {}

    def library_for(mode):
        return libraries.setdefault(mode, AgentCaseLibrary(mode, base_dir=tmp_path / mode))

    monkeypatch.setattr(tool_module, "AgentCaseLibrary", library_for)
    tool_module.AgentCaseLibraryTool.set_case_context("ops")
    tool = tool_module.AgentCaseLibraryTool()
    try:
        result = asyncio.run(tool.execute(
            action="record",
            scenario="ops_work_order_audit",
            title="METONE无采样管温度检查项",
            user_feedback="用户确认排除",
            lesson="同型号且表单字段不适用时不要列入正式问题清单",
            tags=["METONE", "字段不适用"],
        ))
        matches = asyncio.run(tool.execute(
            action="search",
            scenario="ops_work_order_audit",
            query="METONE",
        ))
    finally:
        tool_module.AgentCaseLibraryTool.clear_case_context()

    assert result["success"] is True
    assert matches["match_count"] == 1
    assert matches["cases"][0]["lesson"].startswith("同型号")
    assert libraries["ops"].cases_file.is_file()


def test_agent_case_library_requires_agent_context():
    tool_module.AgentCaseLibraryTool.clear_case_context()
    result = asyncio.run(tool_module.AgentCaseLibraryTool().execute(
        action="record",
        title="案例",
        lesson="经验",
    ))
    assert result == {"success": False, "error": "case_library_context_missing"}

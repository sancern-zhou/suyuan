from pathlib import Path

from app.agent.context.context_builder import SimplifiedContextBuilder
from app.agent.react_agent import ReActAgent
from app.agent.prompts.tool_registry import (
    CHART_TOOL_ORDER,
    EXPERT_TOOL_ORDER,
    get_tool_order_by_mode,
    get_tools_by_mode,
)
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.tools.social.remember_fact.tool import RememberFactTool
from app.tools.social.replace_memory.tool import ReplaceMemoryTool
from app.tools.social.remove_memory.tool import RemoveMemoryTool


def _clear_memory_tool_context():
    RememberFactTool.clear_memory_context()
    ReplaceMemoryTool.clear_memory_context()
    RemoveMemoryTool.clear_memory_context()


def test_graph_mode_exposes_existing_safe_tools_only():
    tools = get_tools_by_mode("graph")

    assert list(tools.keys()) == [
        "list_session_resources",
        "read_session_resource",
        "publish_session_file",
        "knowledge_graph_query",
        "knowledge_graph_build",
        "read_file",
        "edit_file",
        "grep",
        "list_directory",
        "search_files",
    ]
    assert "execute_python" not in tools
    assert "write_file" not in tools
    assert "bash" not in tools


def test_graph_mode_tool_order_matches_registry_order():
    assert get_tool_order_by_mode("graph") == [
        "list_session_resources",
        "read_session_resource",
        "publish_session_file",
        "knowledge_graph_query",
        "knowledge_graph_build",
        "read_file",
        "edit_file",
        "grep",
        "list_directory",
        "search_files",
    ]


def test_session_file_publication_is_available_in_expert_and_chart_modes():
    assert "publish_session_file" in get_tools_by_mode("expert")
    assert "publish_session_file" in get_tools_by_mode("chart")
    assert "publish_session_file" in CHART_TOOL_ORDER


def test_expert_mode_exposes_knowledge_retrieval_tools():
    expert_tools = get_tools_by_mode("expert")

    assert "knowledge_qa_workflow" in expert_tools
    assert "knowledge_document_reader" in expert_tools
    assert "knowledge_qa_workflow" in EXPERT_TOOL_ORDER
    assert "knowledge_document_reader" in EXPERT_TOOL_ORDER


def test_graph_prompt_routes_from_prompt_builder():
    prompt = build_react_system_prompt("graph")

    assert "知识库图谱编辑 Agent" in prompt
    assert "知识库优先" in prompt
    assert "解释/查看/总结类任务" in prompt
    assert "knowledge_graph_query" in prompt
    assert "禁止读取或修改旧 cognitive_maps" in prompt
    assert "execute_python" not in prompt
    assert "/api/cognitive-maps" not in prompt
    assert "edit_file" in prompt


def test_graph_prompt_rejects_unavailable_write_tools():
    prompt = build_react_system_prompt(
        "graph",
        available_tools=["read_file", "write_file", "edit_file", "execute_python"],
    )

    assert "execute_python" not in prompt
    assert "read_file" in prompt
    assert "write_file" not in prompt
    assert "edit_file" in prompt


def test_graph_mode_preserves_map_context_and_builds_summary():
    builder = SimplifiedContextBuilder(None, None)
    builder.current_mode = "graph"
    builder.map_context = {
        "knowledge_base_id": "kb_123",
        "selected_item": {
            "kind": "relation",
            "id": "relation_abc",
            "name": "零点漂移 -> indicates -> 零漂异常",
        },
        "visible_entity_ids": ["entity_a", "entity_b", "entity_c"],
        "visible_relation_ids": ["relation_abc"],
        "entity_count": 3,
        "relation_count": 1,
    }

    builder._apply_mode_context_policy("graph")
    summary = builder._build_graph_map_context_user_summary()

    assert builder.map_context is not None
    assert "当前知识库图谱上下文" in summary
    assert "kb_123" in summary
    assert "不读取独立 JSON 文件" in summary
    assert "relation_abc" in summary
    assert "visible_entity_ids=3" in summary


def test_runtime_metadata_is_not_exposed_in_user_conversation():
    builder = SimplifiedContextBuilder(None, None)

    first_iteration = builder._build_user_conversation(
        query="分析招投标数据",
        iteration=1,
        latest_observation="",
        conversation_history=[],
    )
    later_iteration = builder._build_user_conversation(
        query="分析招投标数据",
        iteration=4,
        latest_observation="",
        conversation_history=[{"role": "user", "content": "历史消息"}],
    )
    system_prompt = builder._build_system_prompt()

    assert "当前时间" not in first_iteration
    assert "当前时间" not in later_iteration
    assert "迭代次数" not in first_iteration
    assert "迭代次数" not in later_iteration
    assert "系统参考时间" in system_prompt
    assert "<runtime_metadata>" in system_prompt
    assert "</runtime_metadata>" in system_prompt


def test_non_graph_non_query_modes_strip_map_context():
    builder = SimplifiedContextBuilder(None, None)
    builder.current_mode = "assistant"
    builder.map_context = {"active_map_id": "map_123"}

    builder._apply_mode_context_policy("assistant")

    assert builder.map_context is None


def test_router_forwards_map_context_for_graph_mode():
    source = Path("backend/app/api/agent.py").read_text(encoding="utf-8")

    assert 'if request.mode in {"query", "graph"} and request.map_context:' in source
    assert 'analyze_kwargs["map_context"] = request.map_context' in source


def test_react_agent_sets_map_context_for_graph_mode():
    source = Path("backend/app/agent/react_agent.py").read_text(encoding="utf-8")

    assert 'if manual_mode in {"query", "graph"} and map_context:' in source
    assert "react_loop.context_builder.map_context = map_context" in source


def test_memory_consolidator_preserves_existing_graph_memory_tool_context():
    _clear_memory_tool_context()
    try:
        RememberFactTool.set_memory_context("graph", "global")
        ReplaceMemoryTool.set_memory_context("graph", "global")
        RemoveMemoryTool.set_memory_context("graph", "global")

        ReActAgent._set_mode_memory_tool_context(
            manual_mode="memory_consolidator",
            memory_tool_mode="memory_consolidator",
            user_identifier="global",
        )

        assert RememberFactTool._current_mode == "graph"
        assert ReplaceMemoryTool._current_mode == "graph"
        assert RemoveMemoryTool._current_mode == "graph"
    finally:
        _clear_memory_tool_context()


def test_graph_mode_sets_memory_tool_context():
    _clear_memory_tool_context()
    try:
        ReActAgent._set_mode_memory_tool_context(
            manual_mode="graph",
            memory_tool_mode="graph",
            user_identifier="global",
        )

        assert RememberFactTool._current_mode == "graph"
        assert ReplaceMemoryTool._current_mode == "graph"
        assert RemoveMemoryTool._current_mode == "graph"
    finally:
        _clear_memory_tool_context()

from pathlib import Path

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tool_order
from app.project_config.loader import load_project_context
from config.settings import settings


REPO_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_TOOLS = [
    "knowledge_qa_workflow",
    "knowledge_document_reader",
    "knowledge_graph_query",
    "read_session_resource",
    "read_file",
    "edit_file",
    "write_file",
    "web_search",
    "web_fetch",
]


def test_jiangsu_declares_dedicated_knowledge_mode_and_tools():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)

    assert "knowledge" in context.manifest.frontend.agent_modes
    assert context.manifest.backend.agent_mode_tools["knowledge"] == EXPECTED_TOOLS
    assert (
        context.manifest.backend.mode_prompt_files["knowledge"]
        == "projects/jiangsu-ops/prompts/knowledge.md"
    )


def test_jiangsu_knowledge_mode_loads_project_prompt_and_tool_surface(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangsu-ops")

    assert get_tool_order("knowledge") == EXPECTED_TOOLS
    prompt = build_react_system_prompt("knowledge")

    assert "你是江苏项目的知识问答智能体" in prompt
    assert "read_session_resource" in prompt
    assert "web_search` / `web_fetch" in prompt
    assert "不执行数据库问数" in prompt

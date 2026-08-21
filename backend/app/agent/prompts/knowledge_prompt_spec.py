from app.agent.prompts.knowledge_prompt import build_knowledge_prompt
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from config.settings import settings


def test_knowledge_mode_exposes_retrieval_web_and_registered_resources(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "default")

    assert list(get_tools_by_mode("knowledge")) == [
        "knowledge_qa_workflow",
        "knowledge_document_reader",
        "knowledge_graph_query",
        "read_session_resource",
        "web_search",
        "web_fetch",
    ]


def test_generic_knowledge_prompt_prioritizes_one_pass_retrieval():
    prompt = build_knowledge_prompt([])

    assert "一次检索尽量覆盖用户问题" in prompt
    assert "不得凭常识补成知识库结论" in prompt
    assert "全文总结才读取全文" in prompt
    assert "read_session_resource" in prompt
    assert "web_search / web_fetch" in prompt


def test_knowledge_mode_builds_generic_prompt(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "default")

    prompt = build_react_system_prompt("knowledge")

    assert "你是知识问答智能体" in prompt
    assert "knowledge_graph_query" in prompt

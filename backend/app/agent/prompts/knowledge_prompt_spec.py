from app.agent.prompts.knowledge_prompt import build_knowledge_prompt
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from config.settings import settings


def test_knowledge_mode_exposes_only_retrieval_and_document_reading(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")

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


def test_xuchang_knowledge_mode_loads_project_prompt(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")

    prompt = build_react_system_prompt("knowledge")

    assert "你是许昌项目的知识问答智能体" in prompt
    assert "共享、本地和个人知识库" in prompt
    assert "不进行数据库问数" in prompt

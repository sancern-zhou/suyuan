from types import SimpleNamespace

import pytest

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tool_order, get_tools_by_mode
from app.tools.workflow.knowledge_qa_workflow import KnowledgeQAWorkflow


def test_enforcement_exam_has_only_the_minimal_tools():
    tools = get_tools_by_mode("enforcement_exam")
    assert list(tools) == [
        "exam_practice",
        "generate_exam_bank",
        "knowledge_qa_workflow",
        "knowledge_document_reader",
        "web_search",
        "web_fetch",
        "schedule_task",
        "create_report_package",
        "edit_file",
    ]
    assert get_tool_order("enforcement_exam") == list(tools)
    assert "bash" not in tools
    assert "web_search" in tools
    assert "web_fetch" in tools


def test_enforcement_exam_prompt_requires_tool_grading_and_grounded_explanations():
    prompt = build_react_system_prompt("enforcement_exam")
    assert "正式练习题必须通过 `exam_practice` 获取" in prompt
    assert "客观题必须调用 `exam_practice(action=\"submit_and_next\")` 判分并推进" in prompt
    assert "knowledge_document_reader" in prompt
    assert "generate_exam_bank" in prompt
    assert "list_banks" in prompt
    assert "用户可以只要一种或部分题型" in prompt
    assert "不要把示例当成固定要求" in prompt
    assert "仅限名称为“执法知识”的知识库" in prompt
    assert "`web_search`" in prompt
    assert "`web_fetch`" in prompt
    assert "不得提前查询、暗示或泄露答案" in prompt
    assert "直接调用 `submit_and_next`" in prompt
    assert "默认不调用知识库工具读取原文" in prompt
    assert "再调用 `grade_and_next`" in prompt
    assert "在同一条消息中先完整解析 `last_result`，再展示下一题" in prompt
    assert "刷题以效率和连续练习体验为优先" in prompt
    assert "无需等待下一轮消息即可继续作答" in prompt
    assert "不得只展示下一题" in prompt
    assert "不展示内部推理过程" in prompt


@pytest.mark.asyncio
async def test_enforcement_exam_search_forces_designated_knowledge_base(monkeypatch):
    captured = {}

    async def resolve(_user_id):
        return ["enforcement-kb"]

    async def search(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        "app.tools.workflow.knowledge_qa_workflow.resolve_enforcement_exam_knowledge_base_ids",
        resolve,
    )
    monkeypatch.setattr("app.api.knowledge_qa.search_knowledge_bases", search)

    result = await KnowledgeQAWorkflow().execute(
        context=SimpleNamespace(
            runtime_mode="enforcement_exam",
            user_identifier="user-1",
        ),
        query="行政处罚程序",
        knowledge_base_ids=["other-kb"],
    )

    assert result["success"] is True
    assert captured["knowledge_base_ids"] == ["enforcement-kb"]
    assert captured["user_id"] == "user-1"



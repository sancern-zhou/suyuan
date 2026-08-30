from pathlib import Path

from app.agent.prompts.project_prompt import load_project_mode_prompt
from app.project_config.loader import load_project_context


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_jiangxi_exposes_sound_environment_knowledge_qa_mode():
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    assert context.manifest.frontend.agent_modes == [
        "query",
        "assistant",
        "expert",
        "report",
    ]
    override = context.manifest.frontend.agent_mode_overrides["assistant"]
    assert override["name"] == "声环境知识问答智能体"
    assert "声环境" in override["description"]


def test_jiangxi_knowledge_qa_mode_has_only_requested_tools():
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    assert context.manifest.backend.agent_mode_tools["assistant"] == [
        "knowledge_qa_workflow",
        "web_search",
        "publish_session_file",
    ]


def test_jiangxi_knowledge_qa_mode_loads_project_owned_prompt():
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    prompt = load_project_mode_prompt("assistant", context=context)

    assert prompt is not None
    assert "你是声环境知识问答智能体" in prompt
    assert "`knowledge_qa_workflow`" in prompt
    assert "`web_search`" in prompt
    assert "`publish_session_file`" in prompt

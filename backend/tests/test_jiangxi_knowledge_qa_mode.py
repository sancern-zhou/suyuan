from pathlib import Path

from app.agent.prompts.project_prompt import load_project_mode_prompt
from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.project_config.loader import load_project_context
from app.utils.path_config import PROJECT_ROOT
from config.settings import settings


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_jiangxi_exposes_sound_environment_knowledge_qa_mode():
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    assert context.manifest.frontend.agent_modes == [
        "query",
        "knowledge",
        "expert",
        "report",
    ]
    override = context.manifest.frontend.agent_mode_overrides["knowledge"]
    assert override["name"] == "声环境知识问答智能体"
    assert "声环境" in override["description"]


def test_jiangxi_knowledge_qa_mode_has_only_requested_tools():
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    assert context.manifest.backend.agent_mode_tools["knowledge"] == [
        "knowledge_qa_workflow",
        "web_search",
        "publish_session_file",
        "edit_file",
    ]


def test_jiangxi_knowledge_qa_mode_loads_project_owned_prompt():
    context = load_project_context("jiangxi", repo_root=REPO_ROOT)

    prompt = load_project_mode_prompt("knowledge", context=context)

    assert prompt is not None
    assert "你是声环境知识问答智能体" in prompt
    assert "`knowledge_qa_workflow`" in prompt
    assert "`web_search`" in prompt
    assert "`publish_session_file`" in prompt


def test_jiangxi_knowledge_qa_mode_gets_mode_level_memory_contract(monkeypatch):
    # 知识问答走独立 knowledge 模式 ID（非 assistant）：提示词自动附加
    # 模式级 MEMORY.md 维护契约，且工具面含 edit_file 可执行维护。
    monkeypatch.setattr(settings, "project_id", "jiangxi")

    relative_path = "backend/backend_data_registry/memory/knowledge/MEMORY.md"
    prompt = build_react_system_prompt(
        "knowledge",
        memory_file_path=str(PROJECT_ROOT / relative_path),
    )

    assert f"常驻长期记忆 `MEMORY.md`：路径 `{relative_path}`" in prompt
    assert "不得读取或修改其他模式的记忆文件" in prompt

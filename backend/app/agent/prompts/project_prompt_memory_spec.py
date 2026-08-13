from app.agent.prompts import prompt_builder
from app.utils.path_config import PROJECT_ROOT


def test_project_prompt_includes_relative_memory_path_and_platform_contract(monkeypatch):
    monkeypatch.setattr(
        prompt_builder,
        "load_project_mode_prompt",
        lambda _mode: "项目专属提示词",
    )
    relative_path = "backend/backend_data_registry/memory/query/MEMORY.md"

    prompt = prompt_builder.build_react_system_prompt(
        "query",
        memory_file_path=str(PROJECT_ROOT / relative_path),
    )

    assert f"当前模式长期记忆文件路径：`{relative_path}`" in prompt
    assert str(PROJECT_ROOT) not in prompt
    assert "不得读取或修改其他模式的 MEMORY.md" in prompt
    assert "文件系统路径约定" in prompt

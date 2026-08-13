from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.utils.path_config import PROJECT_ROOT
from config.settings import settings


def test_xuchang_query_and_expert_prompts_include_relative_memory_paths(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "xuchang")

    for mode in ("query", "knowledge", "expert"):
        relative_path = f"backend/backend_data_registry/memory/{mode}/MEMORY.md"
        absolute_path = PROJECT_ROOT / relative_path
        prompt = build_react_system_prompt(
            mode,
            memory_file_path=str(absolute_path),
        )

        assert f"当前模式长期记忆文件路径：`{relative_path}`" in prompt
        assert str(PROJECT_ROOT) not in prompt
        assert "不得读取或修改其他模式的 MEMORY.md" in prompt

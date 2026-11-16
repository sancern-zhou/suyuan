from pathlib import Path

from app.social.cli_task_store import CliTaskStore
from app.social.task_status_store import TaskStatusStore
from app.tools.social.web_search.tool import WebSearchTool
from config.settings import settings


def test_social_fallback_files_use_active_project_registry(tmp_path, monkeypatch):
    registry = tmp_path / "backend_data_registry_jiangsu_ops"
    monkeypatch.setattr(settings, "data_registry_dir", str(registry))

    cli_tasks = CliTaskStore()
    spawn_tasks = TaskStatusStore()

    assert Path(cli_tasks.json_path) == registry / "cli_tasks.json"
    assert Path(spawn_tasks.json_path) == registry / "spawn_tasks.json"


def test_social_web_search_uses_jiangsu_config_from_environment(tmp_path, monkeypatch):
    shared_path = tmp_path / "shared.yaml"
    jiangsu_path = tmp_path / "jiangsu.yaml"
    shared_path.write_text("web_search:\n  api_key: shared-key\n", encoding="utf-8")
    jiangsu_path.write_text("web_search:\n  api_key: jiangsu-key\n", encoding="utf-8")
    monkeypatch.setenv("SOCIAL_CONFIG_PATH", str(jiangsu_path))

    assert WebSearchTool._load_config_key("web_search", "api_key") == "jiangsu-key"

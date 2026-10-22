from pathlib import Path

from app.agent.prompts.social_prompt import build_social_prompt
from app.api import social_account_routes
from app.project_config.loader import load_project_context
from app.social.cli_task_store import CliTaskStore
from app.social.session_mapper import SessionMapper
from app.social.task_status_store import TaskStatusStore
from app.tools.social.web_search.tool import WebSearchTool
from config import social_config
from config.settings import settings


def test_social_fallback_files_use_active_project_registry(tmp_path, monkeypatch):
    registry = tmp_path / "backend_data_registry_jiangsu_ops"
    monkeypatch.setattr(settings, "data_registry_dir", str(registry))

    mapper = SessionMapper()
    cli_tasks = CliTaskStore()
    spawn_tasks = TaskStatusStore()

    assert mapper.mappings_file == registry / "social" / "session_mappings.json"
    assert Path(cli_tasks.json_path) == registry / "cli_tasks.json"
    assert Path(spawn_tasks.json_path) == registry / "spawn_tasks.json"


def test_social_account_routes_use_active_deployment_config(tmp_path, monkeypatch):
    config_path = tmp_path / "jiangsu-social.yaml"
    monkeypatch.setattr(settings, "social_config_path", str(config_path))
    monkeypatch.setattr(social_config, "get_social_dir", lambda: tmp_path / "social")

    config = social_config.SocialConfig(
        weixin=social_config.WeixinConfig(enabled=True, accounts=[])
    )

    assert social_account_routes.save_config(config)
    assert config_path.is_file()
    assert social_account_routes.load_config().weixin.enabled is True



def test_social_web_search_uses_jiangsu_config_from_environment(tmp_path, monkeypatch):
    shared_path = tmp_path / "shared.yaml"
    jiangsu_path = tmp_path / "jiangsu.yaml"
    shared_path.write_text("web_search:\n  api_key: shared-key\n", encoding="utf-8")
    jiangsu_path.write_text("web_search:\n  api_key: jiangsu-key\n", encoding="utf-8")
    monkeypatch.setenv("SOCIAL_CONFIG_PATH", str(jiangsu_path))

    assert WebSearchTool._load_config_key("web_search", "api_key") == "jiangsu-key"



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


def test_jiangsu_config_does_not_adopt_orphan_account_state(tmp_path, monkeypatch):
    config_path = tmp_path / "jiangsu-social.yaml"
    social_dir = tmp_path / "social"
    orphan_dir = social_dir / "weixin" / "shared-account"
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "account.json").write_text(
        '{"token":"shared-token","base_url":"https://example.invalid"}',
        encoding="utf-8",
    )
    config_path.write_text(
        "weixin:\n"
        "  enabled: true\n"
        "  recover_orphan_accounts: false\n"
        "  accounts: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(social_config, "get_social_dir", lambda: social_dir)

    loaded = social_config.load_social_config(str(config_path))

    assert loaded.weixin.accounts == []


def test_social_web_search_uses_jiangsu_config_from_environment(tmp_path, monkeypatch):
    shared_path = tmp_path / "shared.yaml"
    jiangsu_path = tmp_path / "jiangsu.yaml"
    shared_path.write_text("web_search:\n  api_key: shared-key\n", encoding="utf-8")
    jiangsu_path.write_text("web_search:\n  api_key: jiangsu-key\n", encoding="utf-8")
    monkeypatch.setenv("SOCIAL_CONFIG_PATH", str(jiangsu_path))

    assert WebSearchTool._load_config_key("web_search", "api_key") == "jiangsu-key"


def test_jiangsu_social_mode_owns_a_read_only_project_tool_surface():
    context = load_project_context("jiangsu-ops")
    tools = context.manifest.backend.agent_mode_tools["social"]

    assert "jiangsu_fetch_city_data" in tools
    assert "jiangsu_fetch_station_alarm_logs" in tools
    assert "schedule_task" in tools
    assert "jiangsu_execute_device_control" not in tools
    assert "call_sub_agent" not in tools
    assert "bash" not in tools


def test_jiangsu_social_prompt_names_the_active_project(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "jiangsu-ops")

    prompt = build_social_prompt(available_tools=[])

    assert "当前部署：江苏省运维审核管理服务平台（jiangsu-ops）" in prompt
    assert "不得引用或推断其他项目的配置与数据" in prompt

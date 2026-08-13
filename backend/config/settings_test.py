from pathlib import Path

from config.settings import Settings


def test_settings_loads_backend_env_when_current_directory_is_repo_root(monkeypatch):
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(repo_root)
    monkeypatch.delenv("BAILIAN_API_KEY", raising=False)

    settings = Settings()

    assert settings.bailian_api_key

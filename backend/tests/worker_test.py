import os


def test_worker_env_file_loader_applies_deployment_overrides(tmp_path, monkeypatch):
    from app.worker import _load_requested_env_file

    env_file = tmp_path / "worker.env"
    env_file.write_text("PROJECT=jiangsu-ops\nSOCIAL_WORKER_INTERNAL_PORT=8012\n", encoding="utf-8")
    monkeypatch.delenv("PROJECT", raising=False)
    monkeypatch.delenv("SOCIAL_WORKER_INTERNAL_PORT", raising=False)

    _load_requested_env_file(["--env-file", str(env_file)])

    assert os.environ["PROJECT"] == "jiangsu-ops"
    assert os.environ["SOCIAL_WORKER_INTERNAL_PORT"] == "8012"

from config.settings import Settings


def test_sse_transport_defaults():
    config = Settings(_env_file=None)

    assert config.sse_heartbeat_interval_seconds == 15.0
    assert config.sse_send_timeout_seconds == 30.0


def test_sse_transport_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("SSE_HEARTBEAT_INTERVAL_SECONDS", "22.5")
    monkeypatch.setenv("SSE_SEND_TIMEOUT_SECONDS", "45")

    config = Settings(_env_file=None)

    assert config.sse_heartbeat_interval_seconds == 22.5
    assert config.sse_send_timeout_seconds == 45.0

import pytest

from app.external_apis.dify_client import DifyClient
from app.fetchers.city_statistics.city_statistics_fetcher import (
    SQLServerClient as StatisticsSQLServerClient,
)
from app.services.gd_suncere_api_client import GDSuncereAPIClient
from app.tools.query.query_xcai_city_history.sql_client import (
    SQLServerClient as HistorySQLServerClient,
)
from config.settings import Settings


def test_sqlserver_password_has_no_fallback(monkeypatch):
    monkeypatch.delenv("SQLSERVER_PASSWORD", raising=False)

    settings = Settings(_env_file=None)

    assert settings.sqlserver_password == ""


@pytest.mark.parametrize(
    "client_class", [HistorySQLServerClient, StatisticsSQLServerClient]
)
def test_sqlserver_credentials_are_required_at_connection_time(
    monkeypatch, client_class
):
    monkeypatch.delenv("SQLSERVER_PASSWORD", raising=False)

    client = client_class()

    with pytest.raises(RuntimeError, match="SQLSERVER_PASSWORD"):
        client._build_connection_string()


def test_dify_credentials_are_required_at_request_time(monkeypatch):
    monkeypatch.delenv("DIFY_BASE_URL", raising=False)
    monkeypatch.delenv("DIFY_API_KEY", raising=False)

    client = DifyClient()

    with pytest.raises(RuntimeError, match="DIFY_BASE_URL"):
        client._headers()


def test_dify_allows_explicit_runtime_credentials():
    client = DifyClient(base_url="https://dify.example", api_key="runtime-secret")

    assert client._headers()["Authorization"] == "Bearer runtime-secret"


def test_gd_suncere_credentials_are_required_before_network(monkeypatch):
    monkeypatch.delenv("GD_SUNCERE_API_USERNAME", raising=False)
    monkeypatch.delenv("GD_SUNCERE_API_PASSWORD", raising=False)
    client = GDSuncereAPIClient()

    with pytest.raises(RuntimeError, match="GD_SUNCERE_API_USERNAME"):
        client.get_token()

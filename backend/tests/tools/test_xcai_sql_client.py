from app.tools.query.query_xcai_city_history.sql_client import (
    SQLServerClient,
    resolve_sqlserver_driver,
)


def test_uses_configured_driver_when_installed():
    assert resolve_sqlserver_driver(
        "ODBC Driver 18 for SQL Server",
        ["FreeTDS", "ODBC Driver 18 for SQL Server"],
    ) == "ODBC Driver 18 for SQL Server"


def test_falls_back_to_freetds_when_microsoft_driver_is_unavailable():
    assert resolve_sqlserver_driver(
        "ODBC Driver 17 for SQL Server",
        ["PostgreSQL", "FreeTDS"],
    ) == "FreeTDS"


def test_freetds_connection_uses_modern_tds_protocol(monkeypatch):
    monkeypatch.setattr(
        "app.tools.query.query_xcai_city_history.sql_client.pyodbc.drivers",
        lambda: ["FreeTDS"],
    )

    client = SQLServerClient(password="test-password")

    assert "DRIVER={FreeTDS};" in client.connection_string
    assert "TDS_Version=7.4;" in client.connection_string

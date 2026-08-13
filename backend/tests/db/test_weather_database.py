def test_weather_database_url_prefers_dedicated_setting(monkeypatch):
    monkeypatch.setenv(
        "WEATHER_DATABASE_URL",
        "postgresql://weather_user:secret@weather-host:5432/weather_db",
    )

    from app.db.weather_database import resolve_weather_database_url

    assert resolve_weather_database_url() == (
        "postgresql+asyncpg://weather_user:secret@weather-host:5432/weather_db"
    )


def test_weather_database_url_falls_back_to_primary_setting(monkeypatch):
    monkeypatch.delenv("WEATHER_DATABASE_URL", raising=False)

    from app.db.database import DATABASE_URL
    from app.db.weather_database import resolve_weather_database_url

    assert resolve_weather_database_url() == DATABASE_URL

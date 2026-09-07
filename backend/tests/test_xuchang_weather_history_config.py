from app.project_config import load_project_context
from app.services.weather_history import WeatherHistoryService, grid_point


def test_xuchang_history_covers_henan_without_legacy_region(tmp_path):
    context = load_project_context("xuchang")
    backend = context.manifest.backend
    assert "city_weather_history" in backend.fetchers
    assert "era5" not in backend.fetchers
    config = backend.weather_history
    assert len(config.points) == 18
    assert config.bootstrap_days == 90
    assert config.lookback_days == 7
    assert {p.province for p in config.points} == {"河南省"}
    service = WeatherHistoryService(config, project_id="xuchang", root=tmp_path)
    assert {p.city for p in config.points} >= {"许昌市", "郑州市", "平顶山市", "漯河市", "周口市", "济源市"}
    target = service.resolve("许昌")
    assert grid_point(target.lat, target.lon) == (34, 113.75)
    assert len({grid_point(p.lat, p.lon) for p in config.points}) == 18

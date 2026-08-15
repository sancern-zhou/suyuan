from app.project_config.loader import load_project_context
from app.services.lifecycle_manager import _configured_fetchers


def _fetcher_names(project_id: str) -> list[str]:
    context = load_project_context(project_id)
    return [fetcher.name for fetcher in _configured_fetchers(context)]


def test_default_project_does_not_implicitly_start_jiangsu_fetcher():
    assert "jiangsu_station_fault_event" not in _fetcher_names("default")
    assert "jiangsu_nmc_observed_weather_fetcher" not in _fetcher_names("default")


def test_jiangsu_project_explicitly_starts_only_its_fetcher():
    assert _fetcher_names("jiangsu-ops") == [
        "jiangsu_station_fault_event",
        "jiangsu_nmc_observed_weather_fetcher",
    ]

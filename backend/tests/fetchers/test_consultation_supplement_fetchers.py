from app.fetchers import create_scheduler


def test_monthly_consultation_supplement_fetchers_are_registered(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "project_id", "default")
    scheduler = create_scheduler()

    expected = {
        "monthly_district_pollutant_ranking_fetcher": "30 7 4 * *",
        "monthly_station_high_values_fetcher": "40 7 4 * *",
        "monthly_pollution_events_components_fetcher": "50 7 4 * *",
        "monthly_meteorology_support_fetcher": "30 12 1 * *",
    }

    for name, schedule in expected.items():
        fetcher = scheduler.get_fetcher(name)
        assert fetcher is not None
        assert fetcher.schedule == schedule


def test_monthly_consultation_supplement_fetchers_are_registered_in_lifecycle(monkeypatch):
    from app.fetchers.base.scheduler import FetcherScheduler
    from app.services import lifecycle_manager
    from config.settings import settings

    monkeypatch.setattr(settings, "project_id", "default")

    scheduler = FetcherScheduler()
    monkeypatch.setattr(lifecycle_manager, "fetcher_scheduler", scheduler)

    lifecycle_manager.initialize_fetchers()
    try:
        expected = {
            "monthly_district_pollutant_ranking_fetcher": "30 7 4 * *",
            "monthly_station_high_values_fetcher": "40 7 4 * *",
            "monthly_pollution_events_components_fetcher": "50 7 4 * *",
            "monthly_meteorology_support_fetcher": "30 12 1 * *",
        }

        for name, schedule in expected.items():
            fetcher = scheduler.get_fetcher(name)
            assert fetcher is not None
            assert fetcher.schedule == schedule
    finally:
        if scheduler.is_running():
            scheduler.stop()

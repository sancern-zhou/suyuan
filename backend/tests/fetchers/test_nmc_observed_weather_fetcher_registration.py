from app.fetchers import create_scheduler


def test_nmc_observed_weather_fetcher_is_registered_in_scheduler_factory():
    scheduler = create_scheduler()

    fetcher = scheduler.get_fetcher("nmc_observed_weather_fetcher")

    assert fetcher is not None
    assert fetcher.schedule == "8 * * * *"


def test_nmc_observed_weather_fetcher_is_registered_in_lifecycle(monkeypatch):
    from app.services import lifecycle_manager

    registered = []

    class FakeScheduler:
        def register(self, fetcher):
            registered.append(fetcher.name)

        def list_fetchers(self):
            return registered

        def start(self):
            return None

    monkeypatch.setattr(lifecycle_manager, "fetcher_scheduler", FakeScheduler())

    lifecycle_manager.initialize_fetchers()

    assert "nmc_observed_weather_fetcher" in registered

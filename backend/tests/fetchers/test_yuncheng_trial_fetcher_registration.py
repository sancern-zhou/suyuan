from app.fetchers import create_scheduler


def test_yuncheng_trial_fetcher_is_registered_in_scheduler_factory():
    scheduler = create_scheduler()

    fetcher = scheduler.get_fetcher("yuncheng_trial_fetcher")

    assert fetcher is not None
    assert fetcher.schedule == "0 * * * *"


def test_yuncheng_trial_fetcher_is_registered_in_lifecycle(monkeypatch):
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

    assert "yuncheng_trial_fetcher" in registered


def test_lifecycle_honors_explicit_empty_project_fetcher_allowlist(monkeypatch):
    from app.project_config.loader import load_project_context
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
    monkeypatch.setattr(
        lifecycle_manager,
        "load_project_context",
        lambda _project_id: load_project_context("jiangsu-ops"),
    )

    assert lifecycle_manager.initialize_fetchers() is True
    assert registered == []

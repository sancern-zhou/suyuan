from app.fetchers import create_scheduler
from app.fetchers.tenders import TenderInformationFetcher


def test_tender_information_fetcher_is_registered_in_scheduler_factory():
    scheduler = create_scheduler()

    assert "tender_information_fetcher" in scheduler.fetchers


def test_tender_information_fetcher_is_registered_in_lifecycle(monkeypatch):
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
    monkeypatch.setattr(lifecycle_manager.settings, "project_id", "default")

    assert lifecycle_manager.initialize_fetchers() is True

    assert TenderInformationFetcher().name in registered


def test_jiangxi_project_does_not_register_fetchers(monkeypatch):
    from app.services import lifecycle_manager

    class FailingScheduler:
        def register(self, fetcher):
            raise AssertionError(f"unexpected fetcher registration: {fetcher.name}")

        def start(self):
            raise AssertionError("fetcher scheduler must not start")

    monkeypatch.setattr(lifecycle_manager, "fetcher_scheduler", FailingScheduler())
    monkeypatch.setattr(lifecycle_manager.settings, "project_id", "jiangxi")

    assert lifecycle_manager.initialize_fetchers() is False

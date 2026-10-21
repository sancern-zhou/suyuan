from app.fetchers import create_scheduler


def test_fault_diagnosis_fetcher_is_registered(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "project_id", "default")
    scheduler = create_scheduler()
    fetcher = scheduler.fetchers["fault_diagnosis_fetcher"]

    assert fetcher.schedule == "10 * * * *"

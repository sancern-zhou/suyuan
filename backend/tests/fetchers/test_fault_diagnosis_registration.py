from app.fetchers import create_scheduler


def test_fault_diagnosis_fetcher_is_registered():
    scheduler = create_scheduler()
    fetcher = scheduler.fetchers["fault_diagnosis_fetcher"]

    assert fetcher.schedule == "10 * * * *"

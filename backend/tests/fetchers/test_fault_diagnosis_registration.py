from app.fetchers import create_scheduler


def test_fault_diagnosis_fetcher_is_registered():
    scheduler = create_scheduler()
    assert "fault_diagnosis_fetcher" in scheduler.fetchers

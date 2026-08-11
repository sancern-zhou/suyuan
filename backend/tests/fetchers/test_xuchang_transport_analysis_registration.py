from app.fetchers import create_scheduler
from app.fetchers.xuchang_transport_analysis import XuchangTransportAnalysisFetcher
from app.scheduled_tasks.event_catalog import get_event_definition


def test_xuchang_transport_analysis_fetcher_is_registered():
    scheduler = create_scheduler()

    assert XuchangTransportAnalysisFetcher().name in scheduler.fetchers


def test_xuchang_transport_event_types_are_registered():
    assert get_event_definition("xuchang.station_deviation.escalated") is not None
    assert get_event_definition("xuchang.transport_analysis.completed") is not None

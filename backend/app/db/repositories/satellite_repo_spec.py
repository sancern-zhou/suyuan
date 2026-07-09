from datetime import datetime, timezone

from app.db.repositories.satellite_repo import fire_hotspot_key, filter_existing_fire_hotspots


def test_fire_hotspot_key_normalizes_coordinates_and_time() -> None:
    hotspot = {
        "lat": 35.1234567,
        "lon": 111.9876543,
        "acq_datetime": datetime(2026, 7, 8, 6, 8),
        "satellite": "N20",
    }

    assert fire_hotspot_key(hotspot) == (35.12346, 111.98765, datetime(2026, 7, 8, 6, 8), "N20")


def test_filter_existing_fire_hotspots_removes_existing_and_batch_duplicates() -> None:
    existing = {
        (35.1, 111.2, datetime(2026, 7, 8, 6, 8), "N20"),
    }
    hotspots = [
        {"lat": 35.1, "lon": 111.2, "acq_datetime": datetime(2026, 7, 8, 6, 8), "satellite": "N20"},
        {"lat": 35.2, "lon": 111.3, "acq_datetime": datetime(2026, 7, 8, 6, 9), "satellite": "N21"},
        {"lat": 35.2, "lon": 111.3, "acq_datetime": datetime(2026, 7, 8, 6, 9), "satellite": "N21"},
    ]

    filtered = filter_existing_fire_hotspots(hotspots, existing)

    assert filtered == [
        {"lat": 35.2, "lon": 111.3, "acq_datetime": datetime(2026, 7, 8, 6, 9), "satellite": "N21"},
    ]


def test_filter_existing_fire_hotspots_matches_aware_and_naive_utc_times() -> None:
    existing = {
        (35.1, 111.2, datetime(2026, 7, 8, 6, 8), "N20"),
    }
    hotspots = [
        {
            "lat": 35.1,
            "lon": 111.2,
            "acq_datetime": datetime(2026, 7, 8, 6, 8, tzinfo=timezone.utc),
            "satellite": "N20",
        },
    ]

    assert filter_existing_fire_hotspots(hotspots, existing) == []

from datetime import datetime, timezone

from app.tools.analysis.meteorological_trajectory_analysis.tool import (
    _resolve_trajectory_timing,
)
from app.external_apis.noaa_hysplit_api import NOAAHysplitAPI


def test_recent_backward_gfs_start_time_uses_latest_available_hour():
    requested = datetime(2026, 7, 8, 4, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 8, 5, 5, tzinfo=timezone.utc)

    timing = _resolve_trajectory_timing(
        requested_start=requested,
        now=now,
        direction="Backward",
        meteo_source="gdas1",
    )

    assert timing.effective_start == datetime(2026, 7, 8, 3, 0, tzinfo=timezone.utc)
    assert timing.requested_start == requested
    assert timing.meteo_source == "gfs0p25"
    assert timing.adjusted is True
    assert timing.reason == "recent_gfs_data_not_yet_available"


def test_recent_backward_gfs_keeps_requested_time_when_available():
    requested = datetime(2026, 7, 8, 3, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 8, 5, 5, tzinfo=timezone.utc)

    timing = _resolve_trajectory_timing(
        requested_start=requested,
        now=now,
        direction="Backward",
        meteo_source="gdas1",
    )

    assert timing.effective_start == requested
    assert timing.meteo_source == "gfs0p25"
    assert timing.adjusted is False
    assert timing.reason == "recent_analysis_uses_gfs"


def test_local_trajectory_plot_labels_display_beijing_time():
    labels = NOAAHysplitAPI._format_local_plot_labels(
        direction="Backward",
        start_time="2026-07-07T16:00:00+00:00",
        meteo_source="gfs0p25",
        job_id="123",
        lat=35.0264,
        lon=111.0075,
        heights=[10, 500, 1000],
        hours=72,
    )

    assert labels["title_lines"][1] == "72小时后向轨迹，终止时间：2026年07月08日 00:00 北京时间"
    assert "生成时间:" in labels["info_text"]
    assert "北京时间" in labels["info_text"]

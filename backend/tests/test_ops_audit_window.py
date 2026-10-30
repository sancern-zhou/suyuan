"""审核窗口口径单测：周一运行审核上上周完整自然周创建的工单（不限完成状态）。"""

from datetime import datetime
from unittest.mock import patch

from app.services.ops_audit.audit_window import calculate_weekly_created_window
from app.services.ops_audit.dataset_fetcher import DatasetFetchRequest, _apply_window_defaults


def test_monday_run_covers_previous_previous_full_week():
    """2026-10-26（周一）运行 → 创建窗口 10-12 00:00 ~ 10-19 00:00。"""

    window = calculate_weekly_created_window(
        now=datetime(2026, 10, 26, 10, 0, 0),
        anchor_weekday=0,
        finish_start_offset_days=14,
        finish_end_offset_days=7,
    )
    assert window.create_time_start == "2026-10-12 00:00:00"
    assert window.create_time_end == "2026-10-19 00:00:00"
    assert window.finish_time_start == "2026-10-12 00:00:00"
    assert window.finish_time_end == "2026-10-19 00:00:00"
    assert window.order_statuses == ["Finish"]


def test_window_without_finish_offsets_keeps_create_only():
    """未传完成窗口偏移时保持旧行为（仅创建时间，不约束完成时间）。"""

    window = calculate_weekly_created_window(now=datetime(2026, 10, 26, 10, 0, 0), anchor_weekday=0)
    assert window.create_time_start == "2026-10-12 00:00:00"
    assert window.finish_time_start == ""
    assert window.finish_time_end == ""


def test_fetcher_applies_configured_create_window_without_finish():
    """取数管线读配置：周一运行时仅按创建窗口取上上周，不限完成状态。"""

    request = DatasetFetchRequest(order_types=["Check"], audit_window_preset="weekly_created")
    real_calc = _apply_window_defaults.__module__
    with patch(f"{real_calc}.calculate_weekly_created_window") as mocked:
        mocked.side_effect = lambda **kw: calculate_weekly_created_window(
            now=datetime(2026, 10, 26, 10, 0, 0),
            **{k: v for k, v in kw.items() if k != "now"},
        )
        applied = _apply_window_defaults(request)

    assert applied.create_time_start == "2026-10-12 00:00:00"
    assert applied.create_time_end == "2026-10-19 00:00:00"
    assert not applied.finish_time_start
    assert not applied.finish_time_end
    assert applied.order_statuses == ["Finish", "Doing", "Wait"]


def test_explicit_time_overrides_preset():
    """显式时间参数优先于预设（既有口径保护）。"""

    request = DatasetFetchRequest(
        order_types=["Check"],
        create_time_start="2026-05-22 00:00:00",
        create_time_end="2026-06-01 00:00:00",
        audit_window_preset="weekly_created",
    )
    applied = _apply_window_defaults(request)
    assert applied.create_time_start == "2026-05-22 00:00:00"
    assert not applied.finish_time_start

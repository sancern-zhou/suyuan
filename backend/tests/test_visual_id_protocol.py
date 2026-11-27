"""Visualization payload and filename IDs are sanitized independently of chat."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.image_cache import sanitize_image_id
from app.tools.visualization.create_business_chart.renderer import _safe_chart_id
from app.utils.visual_ids import VISUAL_ID_PATTERN, new_visual_id, sanitize_visual_id

_FULL_ID_RE = re.compile(rf"^{VISUAL_ID_PATTERN}$")


def test_short_id_generator_output_matches_protocol():
    for index in range(20):
        assert _FULL_ID_RE.match(new_visual_id("echarts", index))
        assert _FULL_ID_RE.match(new_visual_id("matplotlib"))


def test_sanitize_visual_id_collapses_unsafe_chars():
    assert sanitize_visual_id("generic_pollutant_wind_rose_PM2.5") == "generic_pollutant_wind_rose_PM2.5"
    assert sanitize_visual_id("风速玫瑰图") == ""
    assert sanitize_visual_id("PM$_{2.5}$ 污染物") == "PM_2.5"
    assert sanitize_visual_id("SO$_4^{2-}$") == "SO_4_2"
    assert sanitize_visual_id("///") == ""
    assert len(sanitize_visual_id("x" * 500)) == 100


def test_sanitize_image_id_output_is_protocol_safe():
    nasty_inputs = [
        "PM$_{2.5}$",
        "SO$_4^{2-}$",
        "风速玫瑰图",
        "O$_3$",
        "generic_pollutant_wind_rose_PM2.5",
        "风玫瑰/PM2.5 测试",
        "",
        "///",
        "x" * 500,
    ]
    for value in nasty_inputs:
        assert _FULL_ID_RE.match(sanitize_image_id(value)), value


def test_business_chart_safe_chart_id_matches_protocol():
    for value in ("generic_pollutant_wind_rose_PM2.5", "风速玫瑰", "", "a/b\\c"):
        assert _FULL_ID_RE.match(_safe_chart_id(value)), value

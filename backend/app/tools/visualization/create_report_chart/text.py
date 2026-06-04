from __future__ import annotations

from typing import Any


def normalize_matplotlib_label_text(value: Any) -> Any:
    """Normalize common pollutant subscripts/superscripts for Matplotlib labels."""
    if not isinstance(value, str) or not value:
        return value
    replacements = [
        ("PM₂.₅", "PM$_{2.5}$"),
        ("PM₂₅", "PM$_{2.5}$"),
        ("PM₁₀", "PM$_{10}$"),
        ("O₃", "O$_3$"),
        ("NO₂", "NO$_2$"),
        ("SO₂", "SO$_2$"),
        ("CO₂", "CO$_2$"),
        ("CH₄", "CH$_4$"),
        ("N₂O", "N$_2$O"),
        ("μg/m³", "μg/m$^3$"),
        ("ug/m³", "ug/m$^3$"),
        ("/m³", "/m$^3$"),
        ("m³", "m$^3$"),
        ("km²", "km$^2$"),
        ("m²", "m$^2$"),
    ]
    normalized = value
    for old, new in replacements:
        normalized = normalized.replace(old, new)
    return normalized

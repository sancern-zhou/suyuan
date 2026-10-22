from __future__ import annotations

from typing import Any


def normalize_matplotlib_label_text(value: Any) -> Any:
    """Normalize common pollutant subscripts/superscripts for Matplotlib labels."""
    if not isinstance(value, str) or not value:
        return value
    replacements = [
        ("O₃_8H", "O$_3$-8H"),
        ("O₃_8h", "O$_3$-8h"),
        ("O3_8H", "O$_3$-8H"),
        ("O3_8h", "O$_3$-8h"),
        ("PM2.5", "PM$_{2.5}$"),
        ("PM2_5", "PM$_{2.5}$"),
        ("PM10", "PM$_{10}$"),
        ("SO2", "SO$_2$"),
        ("NO2", "NO$_2$"),
        ("O3", "O$_3$"),
        ("SO₄²⁻", "SO$_4^{2-}$"),
        ("SO4²⁻", "SO$_4^{2-}$"),
        ("NO₃⁻", "NO$_3^-$"),
        ("NO3⁻", "NO$_3^-$"),
        ("NO₂⁻", "NO$_2^-$"),
        ("NO2⁻", "NO$_2^-$"),
        ("NH₄⁺", "NH$_4^+$"),
        ("NH4⁺", "NH$_4^+$"),
        ("PO₄³⁻", "PO$_4^{3-}$"),
        ("PO4³⁻", "PO$_4^{3-}$"),
        ("Mg²⁺", "Mg$^{2+}$"),
        ("Ca²⁺", "Ca$^{2+}$"),
        ("Al³⁺", "Al$^{3+}$"),
        ("Li⁺", "Li$^+$"),
        ("Na⁺", "Na$^+$"),
        ("K⁺", "K$^+$"),
        ("F⁻", "F$^-$"),
        ("Cl⁻", "Cl$^-$"),
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

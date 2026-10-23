"""Stable visual tokens for governed report charts.

Agents choose semantic roles and annotations; they do not choose raw Matplotlib
colors, font sizes, or canvas geometry for standard report charts.
"""

from functools import lru_cache

from app.utils.chart_theme import SERIES_COLORS

REPORT_THEME = {
    "font_family": "sans-serif",
    "font_fallbacks": [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Microsoft YaHei",
        "SimHei",
        "Droid Sans Fallback",
        "DejaVu Sans",
    ],
    "colors": {
        "primary": "#1F5C99",
        "secondary": "#9FB6CC",
        "muted": "#C8CFD8",
        "warning": "#D35400",
        "danger": "#C0392B",
        "positive": "#1E8449",
        "grid": "#E6EAEE",
        "title": "#1E2A36",
        "body": "#2C2C2A",
        "axis": "#5F5E5A",
        "tick": "#888780",
        "note": "#B4B2A9",
    },
    "font_sizes": {
        "title": 14.0,
        "axis": 11.0,
        "data_label": 10.5,
        "tick": 9.8,
        "note": 8.5,
    },
    "dpi": 160,
    "export": {
        "format": "png",
        "min_dpi": 150,
        "background": "white",
    },
    "bar_width": 0.56,
    "grid_linewidth": 0.6,
    "label_padding_fraction": 0.012,
}


def theme_color(role: str, fallback: str | None = None) -> str:
    return str(REPORT_THEME["colors"].get(role, fallback or REPORT_THEME["colors"]["primary"]))


@lru_cache(maxsize=1)
def resolved_font_fallbacks() -> list[str]:
    """Font list whose first entry actually resolves in matplotlib and covers CJK.

    Host fontconfig may expose Noto CJK only under another face name (ttc
    collections register their first face), so the bundled preferred font is
    registered and put first; the static fallbacks stay as later entries.
    """
    names: list[str] = []
    try:
        from matplotlib import font_manager as fm

        from app.utils.font_utils import select_preferred_chinese_font_path

        font_path = select_preferred_chinese_font_path()
        if font_path is not None:
            fm.fontManager.addfont(str(font_path))
            names.append(fm.FontProperties(fname=str(font_path)).get_name())
    except Exception:
        pass
    names.extend(name for name in REPORT_THEME["font_fallbacks"] if name not in names)
    return names


def matplotlib_report_style() -> dict:
    """Shared defaults for Python figures; layout remains analysis-specific."""
    colors = REPORT_THEME["colors"]
    sizes = REPORT_THEME["font_sizes"]
    return {
        "figure.figsize": (7.2, 4.6),
        "figure.dpi": REPORT_THEME["dpi"],
        "figure.facecolor": "white",
        "savefig.dpi": REPORT_THEME["dpi"],
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
        "font.family": REPORT_THEME["font_family"],
        "font.sans-serif": resolved_font_fallbacks(),
        "font.size": sizes["axis"],
        "text.color": colors["body"],
        "axes.facecolor": "white",
        "axes.titlesize": sizes["title"],
        "axes.titleweight": "bold",
        "axes.titlecolor": colors["title"],
        "axes.titlelocation": "left",
        "axes.titlepad": 14,
        "axes.labelsize": sizes["axis"],
        "axes.labelcolor": colors["axis"],
        "axes.edgecolor": colors["grid"],
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.axisbelow": True,
        "axes.grid": False,
        "axes.unicode_minus": False,
        "xtick.labelsize": sizes["tick"],
        "ytick.labelsize": sizes["tick"],
        "xtick.color": colors["tick"],
        "ytick.color": colors["tick"],
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "grid.color": colors["grid"],
        "grid.linewidth": REPORT_THEME["grid_linewidth"],
        "grid.linestyle": "-",
        "grid.alpha": 1.0,
        "legend.fontsize": sizes["tick"],
        "legend.frameon": False,
        "lines.linewidth": 2.0,
    }

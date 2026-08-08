import os
from typing import Dict, Any, Optional
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from app.utils.font_utils import apply_font_to_figure, configure_chinese_font

configure_chinese_font()
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['mathtext.fontset'] = 'stix'


def render_carbon_from_payload(payload: Dict[str, Any], out_path: str, dpi: int = 400, fmt: str = "svg"):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    data = payload.get("data", [])
    if not data:
        fig = plt.figure(figsize=(6, 4))
        plt.text(0.5, 0.5, "No data", ha="center", va="center")
        plt.axis("off")
        apply_font_to_figure(fig)
        fig.savefig(out_path, dpi=dpi, format=fmt, bbox_inches="tight")
        plt.close(fig)
        return {fmt: out_path}
    df = pd.DataFrame.from_records(data)
    # stacked time if timestamp exists
    x = payload.get("x", "timestamp")
    series = payload.get("series", ["SOC", "POC", "EC"])
    try:
        df[x] = pd.to_datetime(df[x])
        df = df.set_index(x)
    except Exception:
        pass

    fig, ax = plt.subplots(figsize=(12, 6))
    plot_df = df[[s for s in series if s in df.columns]]
    if not plot_df.empty:
        plot_df.plot(kind="bar", stacked=True, ax=ax)
    ax.set_title("Carbon components")
    plt.tight_layout()
    apply_font_to_figure(fig)
    fig.savefig(out_path, dpi=dpi, format=fmt, bbox_inches="tight")
    # generate png copy
    saved = {fmt: out_path}
    try:
        png = os.path.splitext(out_path)[0] + ".png"
        fig.savefig(png, dpi=dpi, format="png", bbox_inches="tight")
        saved["png"] = png
    except Exception:
        pass
    plt.close(fig)
    return saved









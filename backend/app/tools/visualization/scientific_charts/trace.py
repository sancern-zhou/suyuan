import os
from typing import Dict, Any
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from app.utils.font_utils import apply_font_to_figure, configure_chinese_font

configure_chinese_font()
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['mathtext.fontset'] = 'stix'


def render_trace_from_payload(payload: Dict[str, Any], out_path: str, dpi: int = 400, fmt: str = "svg"):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    data = payload.get("data", [])
    if not data:
        fig = plt.figure(figsize=(6, 4))
        plt.text(0.5, 0.5, "No data", ha="center")
        plt.axis("off")
        apply_font_to_figure(fig)
        fig.savefig(out_path, dpi=dpi, format=fmt, bbox_inches="tight")
        plt.close(fig)
        return {fmt: out_path}
    df = pd.DataFrame.from_records(data)
    fig, ax = plt.subplots(figsize=(10, 6))
    if "value" in df.columns and "element" in df.columns:
        ax.bar(df["element"], df["value"])
    else:
        ax.text(0.5, 0.5, "Invalid data", ha="center")
    ax.set_title("Trace elements enrichment")
    plt.tight_layout()
    apply_font_to_figure(fig)
    fig.savefig(out_path, dpi=dpi, format=fmt, bbox_inches="tight")
    saved = {fmt: out_path}
    try:
        png = os.path.splitext(out_path)[0] + ".png"
        fig.savefig(png, dpi=dpi, format="png", bbox_inches="tight")
        saved["png"] = png
    except Exception:
        pass
    plt.close(fig)
    return saved









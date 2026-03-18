import os
from typing import Dict, Any, Optional
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 显式指定中文字体路径（Linux服务器）
font_path = '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    plt.rcParams['font.sans-serif'] = [fm.FontProperties(fname=font_path).get_name()]
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['mathtext.fontset'] = 'stix'


def render_carbon_from_payload(payload: Dict[str, Any], out_path: str, dpi: int = 400, fmt: str = "svg"):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    data = payload.get("data", [])
    if not data:
        fig = plt.figure(figsize=(6, 4))
        plt.text(0.5, 0.5, "No data", ha="center", va="center")
        plt.axis("off")
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










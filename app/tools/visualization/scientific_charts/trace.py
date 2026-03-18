import os
from typing import Dict, Any
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


def render_trace_from_payload(payload: Dict[str, Any], out_path: str, dpi: int = 400, fmt: str = "svg"):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    data = payload.get("data", [])
    if not data:
        fig = plt.figure(figsize=(6, 4))
        plt.text(0.5, 0.5, "No data", ha="center")
        plt.axis("off")
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










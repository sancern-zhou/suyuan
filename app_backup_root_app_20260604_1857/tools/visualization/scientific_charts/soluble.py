import os
from typing import Dict, Any, Optional
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from PIL import Image

# 显式指定中文字体路径（Linux服务器）
font_path = '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    _chinese_font = fm.FontProperties(fname=font_path)
    plt.rcParams['font.sans-serif'] = [_chinese_font.get_name()]
else:
    _chinese_font = None
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['mathtext.fontset'] = 'stix'

try:
    from backend.app.utils.ternary_plot import to_ternary_coordinates
except ModuleNotFoundError:
    try:
        from app.utils.ternary_plot import to_ternary_coordinates
    except ModuleNotFoundError:
        to_ternary_coordinates = None


def render_soluble_from_payload(payload: Dict[str, Any], out_path: str, dpi: int = 400, fmt: str = "svg"):
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
    # if ternary payload
    if "x" in payload and "y" in payload and "S" in df.columns:
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.scatter(df["x"], df["y"], c=df.get("PM2.5", None), cmap="viridis", alpha=0.7)
        ax.set_title("Ternary plot (S-N-A)")
        ax.axis("off")
    else:
        fig, ax = plt.subplots(figsize=(10, 6))
        series = payload.get("series", [])
        plot_df = df[[s for s in series if s in df.columns]] if series else df
        if not plot_df.empty:
            plot_df.plot(kind="bar", stacked=True, ax=ax)
        ax.set_title("Soluble ions")

    # 强制所有文本使用中文字体（所有分支都要应用）
    if _chinese_font:
        for text in ax.get_xticklabels():
            text.set_fontproperties(_chinese_font)
        for text in ax.get_yticklabels():
            text.set_fontproperties(_chinese_font)
        # 设置x轴标签和标题字体
        if ax.get_xlabel():
            ax.set_xlabel(ax.get_xlabel(), fontproperties=_chinese_font)
        if ax.get_ylabel():
            ax.set_ylabel(ax.get_ylabel(), fontproperties=_chinese_font)
        ax.set_title(ax.get_title(), fontproperties=_chinese_font)

    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi, format=fmt, bbox_inches="tight")
    saved = {fmt: out_path}
    try:
        png = os.path.splitext(out_path)[0] + ".png"
        fig.savefig(png, dpi=dpi, format="png", bbox_inches="tight")
        # 用PIL重新保存，确保中文字体正确嵌入
        img = Image.open(png)
        img.save(png)
        saved["png"] = png
    except Exception:
        pass
    plt.close(fig)
    return saved










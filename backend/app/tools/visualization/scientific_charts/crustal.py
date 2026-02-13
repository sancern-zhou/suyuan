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
    # 创建字体属性对象，供后续使用
    _chinese_font = fm.FontProperties(fname=font_path)
    plt.rcParams['font.sans-serif'] = [_chinese_font.get_name()]
else:
    _chinese_font = None
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['mathtext.fontset'] = 'stix'


def render_crustal_from_payload(payload: Dict[str, Any], out_path: str, dpi: int = 400, fmt: str = "svg"):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    data = payload.get("data", [])
    if isinstance(data, dict):
        box_data = data
    else:
        box_data = {}
    fig, ax = plt.subplots(figsize=(10, 6))
    if box_data:
        labels = list(box_data.keys())
        arrays = [box_data[k] for k in labels]
        ax.boxplot(arrays, labels=labels, patch_artist=True)
        # 设置x轴标签字体（支持中文）
        if _chinese_font:
            ax.set_xticklabels(labels, fontproperties=_chinese_font)
    else:
        ax.text(0.5, 0.5, "No data", ha="center")
    ax.set_title("Crustal elements distribution")
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










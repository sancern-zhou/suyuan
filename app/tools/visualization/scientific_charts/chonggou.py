import os
from typing import Dict, Any, List, Optional
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


def render_chonggou_from_payload(
    payload: Dict[str, Any],
    out_path: str,
    dpi: int = 400,
    fmt: str = "svg",
    font_family: Optional[str] = None,
):
    """
    根据 calculate_reconstruction 的 visuals payload 渲染出版级物质重构组合图并保存为 SVG/PNG/PDF。
    payload 格式参考 calculate_reconstruction 输出：payload['data'] 为 records，series 为组分列表，x 字段是 timestamp。
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    data_records = payload.get("data", [])
    series = payload.get("series", [])
    x_field = payload.get("x", "timestamp")

    if not data_records or not series:
        # 生成空白图片提示
        fig = plt.figure(figsize=(8, 6))
        plt.text(0.5, 0.5, "No data to render", ha="center", va="center", fontsize=12)
        plt.axis("off")
        fig.savefig(out_path, dpi=dpi, format=fmt, bbox_inches="tight")
        plt.close(fig)
        return out_path

    df = pd.DataFrame.from_records(data_records)
    # 如果存在 timestamp 字段，尝试解析为 datetime 并设置为索引
    if x_field in df.columns:
        try:
            df[x_field] = pd.to_datetime(df[x_field])
            df = df.set_index(x_field)
        except Exception:
            pass

    # 提取 series 数据并确保存在
    available_series = [s for s in series if s in df.columns]
    if not available_series:
        fig = plt.figure(figsize=(8, 6))
        plt.text(0.5, 0.5, "No matching series in data", ha="center", va="center", fontsize=12)
        plt.axis("off")
        fig.savefig(out_path, dpi=dpi, format=fmt, bbox_inches="tight")
        plt.close(fig)
        return out_path

    # 图表布局：上左 日值堆叠+PM2.5，右上 饼图，下 通栏 小时堆叠+PM2.5
    fig = plt.figure(figsize=(18, 14))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1], width_ratios=[2, 1])
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])

    colors = plt.get_cmap("tab10").colors
    color_list = [colors[i % len(colors)] for i in range(len(available_series))]

    # 日值堆叠（如果索引为时间则按日聚合）
    plot_df = df[available_series].copy()
    if isinstance(plot_df.index, pd.DatetimeIndex):
        daily = plot_df.resample("D").mean()
        hourly = plot_df
    else:
        daily = plot_df
        hourly = plot_df

    daily.plot(kind="bar", stacked=True, ax=ax1, color=color_list, edgecolor="white", linewidth=0.5)
    # 尝试绘制 PM2.5 若存在
    if "PM2.5" in df.columns:
        ax1_twin = ax1.twinx()
        ax1_twin.plot(range(len(daily)), daily["PM2.5"], color="#DC3545", linewidth=2.5, marker="o", markersize=4)
        ax1_twin.set_ylabel(r"PM2.5 ($\mu$g/m$^3$)", color="#DC3545")
    ax1.set_title("PM2.5 每日组分重构浓度堆叠图", fontproperties=_chinese_font)
    ax1.set_ylabel(r"组分浓度 ($\mu$g/m$^3$)", fontproperties=_chinese_font)

    # 右上饼图（平均占比）
    comp_avg = daily[available_series].mean()
    ax2.pie(comp_avg.values, labels=comp_avg.index, autopct="%1.1f%%", colors=color_list, wedgeprops=dict(width=0.6, edgecolor="white"))
    ax2.set_title("各组分平均占比", fontproperties=_chinese_font)

    # 下方小时堆叠（或原始时序）
    hourly.plot(kind="bar", stacked=True, ax=ax3, color=color_list, edgecolor="white", linewidth=0.0)
    if "PM2.5" in df.columns:
        ax3_twin = ax3.twinx()
        ax3_twin.plot(range(len(hourly)), hourly["PM2.5"], color="#DC3545", linewidth=1.5, marker="o", markersize=2)
        ax3_twin.set_ylabel(r"PM2.5 ($\mu$g/m$^3$)", color="#DC3545")
    ax3.set_title("PM2.5 小时组分重构浓度堆叠图", fontproperties=_chinese_font)
    ax3.set_xlabel("时间", fontproperties=_chinese_font)
    ax3.set_ylabel(r"组分浓度 ($\mu$g/m$^3$)", fontproperties=_chinese_font)

    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi, format=fmt, bbox_inches="tight")
    saved = {fmt: out_path}
    # 同时保存 PNG 以便前端展示兼容性（如果主格式为矢量则生成位图副本）
    try:
        if fmt.lower() in ("svg", "pdf"):
            png_path = os.path.splitext(out_path)[0] + ".png"
            fig.savefig(png_path, dpi=dpi, format="png", bbox_inches="tight")
            # 用PIL重新保存，确保中文字体正确嵌入
            img = Image.open(png_path)
            img.save(png_path)
            saved["png"] = png_path
    except Exception:
        # 忽略位图生成失败，但保证矢量文件可用
        pass
    plt.close(fig)
    return saved



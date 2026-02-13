"""
统一颗粒物分析可视化模块

生成碳组分、水溶性离子、地壳元素、微量元素、重构分析等图表
格式统一为 UDF v2.0 + Chart v3.1 规范，与 EKMAVisualizer 保持一致
"""

import io
import os
import base64
from typing import Dict, List, Any, Optional
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import structlog
from PIL import Image

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.font_manager as fm

# 获取后端服务器地址
BACKEND_HOST = os.getenv("BACKEND_HOST", "http://localhost:8000")

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

logger = structlog.get_logger()

# 离子字段中英文映射（用于图表标签）
ION_LABEL_MAP = {
    'sulfate': '硫酸盐',
    'nitrate': '硝酸盐',
    'ammonium': '铵盐',
    'calcium': '钙',
    'magnesium': '镁',
    'potassium': '钾',
    'sodium': '钠',
    'chloride': '氯',
}


class ParticulateVisualizer:
    """
    颗粒物分析统一可视化器

    与 EKMAVisualizer 保持一致的返回格式：
    {
        "id": chart_id,
        "type": "chart",
        "schema": "chart_config",
        "payload": {
            "type": "image",
            "data": "data:image/png;base64,...",
            "title": "图表标题",
            "meta": {...}
        },
        "meta": {...}
    }
    """

    def __init__(self, figure_size: tuple = (10, 8), dpi: int = 150):
        self.figure_size = figure_size
        self.dpi = dpi

    def _fig_to_base64(self, fig: plt.Figure) -> str:
        """将matplotlib图形转换为base64编码"""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=self.dpi, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        # 用PIL重新保存，确保中文字体正确嵌入
        img = Image.open(buf)
        buf2 = io.BytesIO()
        img.save(buf2, format='PNG')
        buf2.seek(0)
        img_base64 = base64.b64encode(buf2.read()).decode('utf-8')
        buf.close()
        buf2.close()
        plt.close(fig)
        return f"data:image/png;base64,{img_base64}"

    def _create_visual(
        self,
        fig: plt.Figure,
        chart_id: str,
        title: str,
        chart_type: str,
        scenario: str,
        extra_meta: Optional[Dict] = None,
        source_data_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建符合前端渲染规范的 visual 结构

        返回格式（URL直接渲染方案）:
        {
            "id": "image_id",
            "type": "image",
            "schema": "chart_config",
            "payload": {
                "type": "image",
                "data": "[IMAGE:image_id]",
                "image_id": "image_id",
                "image_url": "/api/image/xxx",  # 完整URL，供LLM生成Markdown链接
                "markdown_image": "![title](/api/image/xxx)",  # 预生成的Markdown格式
                "title": "..."
            },
            "meta": {...}
        }
        """
        from app.services.image_cache import get_image_cache

        # 生成base64图片
        img_base64 = self._fig_to_base64(fig)

        # 保存图片并获取image_id
        cache = get_image_cache()
        saved_image_id = cache.save(img_base64, chart_id)

        # 拼接完整URL（参考 meteorological_trajectory_analysis 的实现）
        image_relative_path = f"/api/image/{saved_image_id}"
        image_url = f"{BACKEND_HOST}{image_relative_path}"  # 完整URL

        meta = {
            "schema_version": "3.1",
            "generator": "ParticulateVisualizer",
            "scenario": scenario,
        }
        if extra_meta:
            meta.update(extra_meta)

        # 构建source_data_ids列表
        source_data_ids = [source_data_id] if source_data_id else []

        return {
            "id": saved_image_id,
            "type": "image",
            "schema": "chart_config",
            "payload": {
                "type": "image",
                "data": f"[IMAGE:{saved_image_id}]",
                "image_id": saved_image_id,
                "image_url": image_url,  # 完整URL，供LLM生成Markdown链接
                "markdown_image": f"![{title}]({image_url})",  # 预生成的Markdown格式（完整URL）
                "title": title,
                "meta": meta
            },
            "meta": {
                "chart_type": chart_type,
                "scenario": scenario,
                "source_data_ids": source_data_ids,
                "layout_hint": "wide",
                "image_url": image_url,  # 完整URL
                "markdown_image": f"![{title}]({image_url})"  # 完整URL
            }
        }

    # ==================== 碳组分分析图表 ====================

    def generate_carbon_bar_chart(
        self,
        result_df: pd.DataFrame,
        pm25: Optional[pd.Series] = None,
        source_data_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """生成碳组分堆积柱状图（时序图）"""
        try:
            required_cols = ['SOC', 'POC', 'EC']
            if not all(col in result_df.columns for col in required_cols):
                return None

            carbon_data = result_df[required_cols].copy()
            pm25_data = pm25.copy() if pm25 is not None else None

            if isinstance(carbon_data.index, pd.DatetimeIndex):
                x_labels = carbon_data.index.strftime('%m/%d %H:%M')
                x = np.arange(len(carbon_data))
            else:
                x_labels = [f't{i}' for i in range(len(carbon_data))]
                x = np.arange(len(carbon_data))

            valid_mask = carbon_data.notna().any(axis=1)
            valid_indices = x[valid_mask]
            valid_carbon_data = carbon_data[valid_mask]

            if len(valid_indices) == 0:
                return None

            fig, ax1 = plt.subplots(figsize=(14, 8))
            colors = ['#2E8B57', '#87CEEB', '#2F4F4F']
            line_colors = ['#E74C3C', '#8E44AD']

            # 中文字体
            chinese_font = _chinese_font if _chinese_font else None

            bar_width = 0.8
            bottom = np.zeros(len(valid_indices))

            for i, col in enumerate(required_cols):
                values = valid_carbon_data[col].values
                plot_values = np.where(np.isnan(values), 0, values)
                ax1.bar(valid_indices, plot_values, bottom=bottom, label=col,
                        width=bar_width, color=colors[i], alpha=0.85,
                        edgecolor='white', linewidth=0.3)
                bottom += plot_values

            bar_heights = bottom

            ax2 = ax1.twinx()
            if pm25_data is not None:
                valid_pm25_mask = ~pm25_data.isna()
                valid_pm25_indices = x[valid_pm25_mask]
                valid_pm25_vals = pm25_data.values[valid_pm25_mask]
                if len(valid_pm25_indices) > 0:
                    ax2.plot(valid_pm25_indices, valid_pm25_vals, color=line_colors[0],
                            linewidth=2, marker='o', markersize=3, label='PM2.5',
                            alpha=0.9, markeredgecolor='white', markeredgewidth=0.5, zorder=5)

            ax3 = ax1.twinx()
            ax3.spines['right'].set_position(('outward', 60))
            if 'EC_OC' in result_df.columns:
                ec_oc_data = result_df['EC_OC']
                valid_ecoc_mask = ~ec_oc_data.isna()
                valid_ecoc_indices = x[valid_ecoc_mask]
                valid_ecoc_vals = ec_oc_data.values[valid_ecoc_mask]
                if len(valid_ecoc_indices) > 0:
                    ax3.plot(valid_ecoc_indices, valid_ecoc_vals, color=line_colors[1],
                            linewidth=2, linestyle='--', marker='s', markersize=3,
                            label='EC/OC', alpha=0.9, zorder=5)

            ax1.set_xlabel('时间', fontsize=12, fontweight='bold', fontproperties=chinese_font)
            ax1.set_ylabel(r'碳组分浓度 ($\mu$g/m$^3$)', fontsize=12, fontweight='bold', color='#2E8B57', fontproperties=chinese_font)
            ax2.set_ylabel(r'PM2.5浓度 ($\mu$g/m$^3$)', fontsize=12, fontweight='bold', color=line_colors[0], fontproperties=chinese_font)
            ax3.set_ylabel('EC/OC 比值', fontsize=12, fontweight='bold', color=line_colors[1], fontproperties=chinese_font)

            if len(bar_heights) > 0:
                max_bar_height = np.max(bar_heights)
                if max_bar_height > 0:
                    ax1.set_ylim(0, max_bar_height * 1.2)

            if pm25_data is not None:
                pm25_max = pm25_data.max()
                if not np.isnan(pm25_max):
                    ax2.set_ylim(0, pm25_max * 1.2)

            if len(x) > 24:
                tick_positions = [i for i in range(len(x)) if x[i] % 6 == 0]
                tick_labels = [x_labels[i] if i < len(x_labels) else '' for i in tick_positions]
                plt.xticks(tick_positions, tick_labels, rotation=45, ha='right', fontsize=9)
            else:
                step = max(1, len(valid_indices) // 10)
                plt.xticks(valid_indices[::step],
                          [x_labels[i] if i < len(x_labels) else '' for i in valid_indices[::step]],
                          rotation=45, ha='right', fontsize=9)

            ax1.grid(axis='y', alpha=0.3, linestyle='--')
            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            lines3, labels3 = ax3.get_legend_handles_labels()
            ax1.legend(lines1 + lines2 + lines3, labels1 + labels2 + labels3,
                      loc='upper right', fontsize=10, framealpha=0.9, prop=chinese_font)

            plt.title('碳组分堆积柱状图与污染物变化趋势分析\n(SOC→POC→EC 与 PM2.5、EC/OC 变化趋势)',
                     fontsize=14, fontweight='bold', pad=15, fontproperties=chinese_font)
            plt.tight_layout()

            chart_id = f"carbon_bar_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(fig, chart_id, "碳组分堆积柱状图", "carbon_bar_chart", "pm_carbon_analysis", source_data_id=source_data_id)

        except Exception as e:
            logger.warning(f"生成碳组分柱状图失败: {e}")
            return None

    def generate_ec_oc_scatter_chart(
        self,
        result_df: pd.DataFrame,
        source_data_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """生成 EC vs OC 散点图"""
        try:
            if 'EC' not in result_df.columns or 'OC' not in result_df.columns:
                return None

            data = result_df[['EC', 'OC']].dropna()
            if len(data) == 0:
                return None

            fig, ax = plt.subplots(figsize=(10, 8))

            # 中文字体
            chinese_font = _chinese_font if _chinese_font else None

            # 使用 .loc[data.index] 确保索引对齐，同时处理重复索引问题
            if 'PM2.5' in result_df.columns:
                pm25 = result_df.loc[data.index, 'PM2.5']
                # 确保pm25是一维的，与data长度一致
                pm25_values = pm25.values.flatten() if hasattr(pm25.values, 'flatten') else pm25.values
                scatter = ax.scatter(data['EC'], data['OC'], c=pm25_values,
                                    cmap='plasma', alpha=0.7, s=80, edgecolors='white', linewidths=0.8)
                cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
                cbar.set_label(r'PM2.5 ($\mu$g/m$^3$)', rotation=270, labelpad=15, fontproperties=chinese_font)
            else:
                ax.scatter(data['EC'], data['OC'], alpha=0.7, s=80,
                          edgecolors='white', linewidths=0.8, color='steelblue')

            z = np.polyfit(data['EC'], data['OC'], 1)
            p = np.poly1d(z)
            x_line = np.linspace(data['EC'].min(), data['EC'].max(), 100)
            ax.plot(x_line, p(x_line), "r--", alpha=0.8, linewidth=2, label='趋势线')

            corr = data['EC'].corr(data['OC'])
            stats_text = f'样本数: {len(data)}\n相关系数: R = {corr:.3f}'
            ax.text(0.05, 0.95, stats_text, transform=ax.transAxes,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.8),
                   verticalalignment='top', fontsize=11, fontproperties=chinese_font)

            ax.set_xlabel(r'EC ($\mu$g/m$^3$)', fontsize=12, fontweight='bold')
            ax.set_ylabel(r'OC ($\mu$g/m$^3$)', fontsize=12, fontweight='bold')
            ax.set_title('EC 与 OC 相关性分析', fontsize=14, fontweight='bold', pad=15, fontproperties=chinese_font)
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.legend(loc='upper left', fontsize=10, prop=chinese_font)

            plt.tight_layout()

            chart_id = f"ec_oc_scatter_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(fig, chart_id, "EC vs OC 散点图", "ec_oc_scatter", "pm_carbon_analysis", source_data_id=source_data_id)

        except Exception as e:
            logger.warning(f"生成EC-OC散点图失败: {e}")
            return None

    # ==================== 水溶性离子分析图表 ====================

    def generate_ion_timeseries_chart(
        self,
        df: pd.DataFrame,
        available_ions: List[str],
        pm25: Optional[pd.Series] = None,
        source_data_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """生成水溶性离子浓度堆积柱状图（与PM2.5双Y轴）"""
        try:
            if not available_ions or df.empty:
                return None

            ion_data = df[available_ions].copy()

            if isinstance(df.index, pd.DatetimeIndex):
                x_labels = df.index.strftime('%m/%d %H:%M')
                x = np.arange(len(df))
            else:
                x_labels = [f't{i}' for i in range(len(df))]
                x = np.arange(len(df))

            valid_mask = ion_data.notna().any(axis=1)
            valid_indices = x[valid_mask]

            if len(valid_indices) == 0:
                return None

            fig, ax1 = plt.subplots(figsize=(16, 8))
            ax2 = ax1.twinx()

            # 行业常用科研配色（8种离子，区分度高、低饱和、适配黑白打印）
            colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#7209B7', '#43AA8B', '#F9C74F', '#577590']

            # 中文字体
            chinese_font = _chinese_font if _chinese_font else None

            # 堆积柱状图
            bar_width = 0.8
            bottom = np.zeros(len(valid_indices))
            valid_ion_data = ion_data.loc[valid_mask]

            for i, ion in enumerate(available_ions):
                if ion in valid_ion_data.columns:
                    values = valid_ion_data[ion].fillna(0).values
                    # 使用中文标签
                    ion_label = ION_LABEL_MAP.get(ion, ion)
                    ax1.bar(valid_indices, values, bottom=bottom, label=ion_label,
                            width=bar_width, color=colors[i % len(colors)], alpha=0.85,
                            edgecolor='white', linewidth=0.3)
                    bottom += values

            # PM2.5折线图（右Y轴）
            if pm25 is not None:
                valid_pm25 = pm25.fillna(np.nan)
                valid_pm25_mask = ~valid_pm25.isna()
                valid_pm25_indices = x[valid_pm25_mask]
                valid_pm25_values = valid_pm25.values[valid_pm25_mask]
                if len(valid_pm25_indices) > 0:
                    ax2.plot(valid_pm25_indices, valid_pm25_values, color='#E74C3C',
                            linewidth=2, marker='o', markersize=3, label='PM2.5',
                            alpha=0.9, markeredgecolor='white', markeredgewidth=0.5, zorder=5)

            ax1.set_xlabel('时间', fontsize=12, fontweight='bold', fontproperties=chinese_font)
            ax1.set_ylabel(r'水溶性离子浓度 ($\mu$g/m$^3$)', fontsize=12, fontweight='bold', color='#34495E', fontproperties=chinese_font)
            ax1.tick_params(axis='y', labelcolor='#34495E')

            max_ion_height = np.max(bottom) if len(bottom) > 0 else 0
            if max_ion_height > 0:
                ax1.set_ylim(0, max_ion_height * 1.1)

            ax2.set_ylabel(r'PM2.5 ($\mu$g/m$^3$)', fontsize=12, fontweight='bold', color='#E74C3C', fontproperties=chinese_font)
            ax2.tick_params(axis='y', labelcolor='#E74C3C')
            if pm25 is not None:
                pm25_max = pm25.max()
                if not np.isnan(pm25_max):
                    ax2.set_ylim(0, pm25_max * 1.1)

            # X轴刻度
            if len(x) > 24:
                tick_positions = [i for i in range(len(x)) if x[i] % 6 == 0]
                tick_labels = [x_labels[i] if i < len(x_labels) else '' for i in tick_positions]
                plt.xticks(tick_positions, tick_labels, rotation=45, ha='right', fontsize=9)
            else:
                step = max(1, len(valid_indices) // 10)
                plt.xticks(valid_indices[::step],
                          [x_labels[i] if i < len(x_labels) else '' for i in valid_indices[::step]],
                          rotation=45, ha='right', fontsize=9)

            ax1.grid(axis='y', alpha=0.3, linestyle='--')

            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=10, framealpha=0.9, prop=chinese_font)

            plt.title('水溶性离子组分堆积时间序列与PM2.5浓度变化', fontsize=14, fontweight='bold', pad=15, fontproperties=chinese_font)
            plt.tight_layout()

            chart_id = f"ion_timeseries_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(fig, chart_id, "水溶性离子组分堆积时间序列与PM2.5浓度变化", "ion_timeseries", "pm_soluble_ion_analysis", source_data_id=source_data_id)

        except Exception as e:
            logger.warning(f"生成离子时序图失败: {e}")
            return None

    def generate_ternary_chart(
        self,
        ternary_df: pd.DataFrame,
        pm25: Optional[pd.Series] = None,
        source_data_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """生成三元图（S-N-A组成），带完整网格线和刻度标签"""
        try:
            if 'x' not in ternary_df.columns or 'y' not in ternary_df.columns:
                return None

            valid_mask = ternary_df['x'].notna() & ternary_df['y'].notna()
            x_data = ternary_df.loc[valid_mask, 'x'].values
            y_data = ternary_df.loc[valid_mask, 'y'].values

            if len(x_data) == 0:
                return None

            pm25_data = None
            if pm25 is not None:
                pm25_data = pm25[valid_mask].values

            fig, ax = plt.subplots(figsize=(12, 10))

            triangle_size = 1.0
            height = triangle_size * np.sqrt(3) / 2
            vertices = {
                'S': (0, 0),       # 硫酸根顶点
                'N': (triangle_size, 0),  # 硝酸根顶点
                'A': (triangle_size / 2, height)  # 铵离子顶点
            }

            # 绘制三角形边框
            ax.plot([vertices['S'][0], vertices['N'][0]], [vertices['S'][1], vertices['N'][1]], 'k-', lw=2.5)
            ax.plot([vertices['N'][0], vertices['A'][0]], [vertices['N'][1], vertices['A'][1]], 'k-', lw=2.5)
            ax.plot([vertices['A'][0], vertices['S'][0]], [vertices['A'][1], vertices['S'][1]], 'k-', lw=2.5)

            # 网格线参数（统一间隔）
            tick_interval = 0.2
            ticks = np.arange(tick_interval, 1.0, tick_interval)

            # 平行于底边(S-N)的网格线（固定A值）
            for a in ticks:
                x1 = 0.5 * a
                y1 = (np.sqrt(3) / 2) * a
                x2 = 0.5 * (2 * (1 - a) + a)
                y2 = y1
                ax.plot([x1, x2], [y1, y2], 'gray', linestyle='--', linewidth=1.0, alpha=0.5)
                ax.text((x1 + x2) / 2, y1 + 0.02, f'{a:.1f}', fontsize=9, color='gray',
                        ha='center', va='bottom')

            # 平行于左边(A-S)的网格线（固定N值）
            for n in ticks:
                x1 = n
                y1 = 0
                x2 = 0.5 * (n + 1)
                y2 = (np.sqrt(3) / 2) * (1 - n)
                ax.plot([x1, x2], [y1, y2], 'gray', linestyle='--', linewidth=1.0, alpha=0.5)
                ax.text(x1 - 0.02, y1 - 0.03, f'{n:.1f}', fontsize=9, color='gray',
                        ha='right', va='top')

            # 平行于右边(N-A)的网格线（固定S值）
            for s in ticks:
                x1 = 1 - s
                y1 = 0
                x2 = 0.5 * (1 - s)
                y2 = (np.sqrt(3) / 2) * (1 - s)
                ax.plot([x1, x2], [y1, y2], 'gray', linestyle='--', linewidth=1.0, alpha=0.5)
                ax.text(x1 + 0.02, y1 - 0.03, f'{s:.1f}', fontsize=9, color='gray',
                        ha='left', va='top')

            # 顶点标签（中文）
            vertex_font = _chinese_font if _chinese_font else None
            ax.text(vertices['S'][0] - 0.08, vertices['S'][1] - 0.08, '硫酸盐\n(Sulfate)', fontsize=12, ha='center', va='top', fontweight='bold', color='#2E86AB', fontproperties=vertex_font)
            ax.text(vertices['N'][0] + 0.08, vertices['N'][1] - 0.08, '硝酸盐\n(Nitrate)', fontsize=12, ha='center', va='top', fontweight='bold', color='#E74C3C', fontproperties=vertex_font)
            ax.text(vertices['A'][0], vertices['A'][1] + 0.06, '铵盐\n(Ammonium)', fontsize=12, ha='center', va='bottom', fontweight='bold', color='#F39C12', fontproperties=vertex_font)

            # 散点图（点大小和颜色表示PM2.5浓度）
            if pm25_data is not None:
                cmap = LinearSegmentedColormap.from_list('pm25', ['#87CEEB', '#4169E1', '#FF6347', '#DC143C'])
                sizes = np.interp(pm25_data, [np.nanmin(pm25_data), np.nanmax(pm25_data)], [60, 350])
                scatter = ax.scatter(x_data, y_data, s=sizes, c=pm25_data, cmap=cmap,
                                    alpha=0.7, edgecolors='white', linewidths=0.5)
                cbar = plt.colorbar(scatter, ax=ax, shrink=0.7, pad=0.08)
                cbar.set_label(r'PM2.5 ($\mu$g/m$^3$)', fontsize=11, fontweight='bold')

                # PM2.5图例
                pm25_labels = [int(np.nanmin(pm25_data)), int(np.nanmedian(pm25_data)), int(np.nanmax(pm25_data))]
                pm25_sizes = np.interp(pm25_labels, [np.nanmin(pm25_data), np.nanmax(pm25_data)], [60, 350])
                legend_elements = [plt.scatter([], [], s=s, c='gray', alpha=0.7, edgecolors='white', label=r'%d $\mu$g/m$^3$' % l)
                                   for s, l in zip(pm25_sizes, pm25_labels)]
                ax.legend(handles=legend_elements, title='PM2.5', loc='upper right', framealpha=0.9, fontsize=9)
            else:
                ax.scatter(x_data, y_data, s=80, alpha=0.7, color='steelblue',
                          edgecolors='white', linewidths=0.5)

            ax.set_xlim(-0.12, triangle_size + 0.12)
            ax.set_ylim(-0.12, height + 0.12)
            ax.set_aspect('equal')
            ax.axis('off')

            title_font = _chinese_font if _chinese_font else None
            plt.title('硫酸盐-硝酸盐-铵盐三元图', fontsize=14, fontweight='bold', pad=20, fontproperties=title_font)
            plt.tight_layout()

            chart_id = f"ternary_sna_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(fig, chart_id, "硫酸盐-硝酸盐-铵盐三元图", "ternary_SNA", "pm_soluble_ion_analysis", source_data_id=source_data_id)

        except Exception as e:
            logger.warning(f"生成三元图失败: {e}")
            return None

    def generate_sor_nor_chart(
        self,
        nor_series: pd.Series,
        sor_series: pd.Series,
        pm25: Optional[pd.Series] = None,
        source_data_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """生成SOR/NOR散点图（带中轴线、点大小映射PM2.5）"""
        try:
            logger.info(
                "[generate_sor_nor_chart] 输入参数",
                nor_notna=nor_series.notna().sum() if nor_series is not None else None,
                sor_notna=sor_series.notna().sum() if sor_series is not None else None,
                pm25_notna=pm25.notna().sum() if pm25 is not None else None,
                pm25_is_none=pm25 is None
            )

            valid_mask = (nor_series.notna() | sor_series.notna())
            nor_valid = nor_series[valid_mask].values
            sor_valid = sor_series[valid_mask].values

            if len(nor_valid) == 0 and len(sor_valid) == 0:
                logger.warning("[generate_sor_nor_chart] 无有效数据")
                return None

            fig, ax = plt.subplots(figsize=(12, 8))

            # 中文字体
            chinese_font = _chinese_font if _chinese_font else None

            valid_data = pd.DataFrame({
                'NOR': nor_series,
                'SOR': sor_series,
                'PM2.5': pm25
            }).dropna(subset=['NOR', 'SOR'], how='all')

            logger.info(
                "[generate_sor_nor_chart] valid_data",
                len=len(valid_data),
                columns=list(valid_data.columns),
                pm25_has_values=valid_data['PM2.5'].notna().sum() if 'PM2.5' in valid_data.columns else 0
            )

            if valid_data.empty:
                return None

            nor_vals = valid_data['NOR'].values
            sor_vals = valid_data['SOR'].values
            pm25_vals = valid_data['PM2.5'].values if 'PM2.5' in valid_data.columns else None

            logger.info(
                "[generate_sor_nor_chart] 数据值",
                nor_vals_len=len(nor_vals),
                sor_vals_len=len(sor_vals),
                pm25_vals_is_none=pm25_vals is None,
                pm25_vals_len=len(pm25_vals) if pm25_vals is not None else None
            )

            # 点大小映射PM2.5浓度
            N = 10  # 放大倍数
            legend_elements = []  # 初始化legend_elements

            if pm25_vals is not None:
                logger.info(
                    "[generate_sor_nor_chart] PM2.5数据检查",
                    pm25_vals_type=str(type(pm25_vals)),
                    pm25_vals_is_ndarray=isinstance(pm25_vals, np.ndarray),
                    pm25_vals_len=len(pm25_vals) if pm25_vals is not None else None,
                    pm25_vals_has_nan=any(pd.isna(pm25_vals)) if pm25_vals is not None else None
                )

                # 【修复】正确处理numpy array的NaN检查
                pm25_has_valid = False
                if isinstance(pm25_vals, np.ndarray):
                    pm25_has_valid = not np.all(pd.isna(pm25_vals))
                elif isinstance(pm25_vals, pd.Series):
                    pm25_has_valid = pm25_vals.notna().any()
                elif pm25_vals:
                    # list 或其他可迭代对象
                    pm25_has_valid = any(pd.isna(v) is False for v in pm25_vals)

                if pm25_has_valid:
                    dot_sizes = pm25_vals * N
                    cmap = plt.cm.jet
                    scatter = ax.scatter(nor_vals, sor_vals, s=dot_sizes, c=pm25_vals, cmap=cmap,
                                        alpha=0.7, edgecolors='white', linewidths=1.2,
                                        vmin=np.nanmin(pm25_vals), vmax=np.nanmax(pm25_vals))
                    cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
                    cbar.set_label(r'PM2.5 ($\mu$g/m$^3$)', fontsize=11, fontweight='bold')

                    # PM2.5图例
                    pm25_min, pm25_max = np.nanmin(pm25_vals), np.nanmax(pm25_vals)
                    pm25_labels = [int(pm25_min), int(np.median(pm25_vals)), int(pm25_max)]
                    size_values = np.interp(pm25_labels, [pm25_min, pm25_max], [pm25_min * N, pm25_max * N])
                    from matplotlib.lines import Line2D
                    legend_elements = [
                        Line2D([0], [0], marker='o', color='w', markerfacecolor=cmap(0.1),
                               markersize=np.sqrt(s) / 2, label=f'PM2.5: {l}', markeredgecolor='white')
                        for s, l in zip(size_values, pm25_labels)
                    ]
                else:
                    ax.scatter(nor_vals, sor_vals, s=80, alpha=0.7, color='steelblue',
                              edgecolors='white', linewidths=0.8)
            else:
                ax.scatter(nor_vals, sor_vals, s=80, alpha=0.7, color='steelblue',
                          edgecolors='white', linewidths=0.8)

            # 中轴线（对称范围，正中位置）
            nor_mean = np.nanmean(nor_vals)
            sor_mean = np.nanmean(sor_vals)

            # X轴中轴线（NOR均值）
            nor_max_dev = max(nor_mean - np.nanmin(nor_vals), np.nanmax(nor_vals) - nor_mean)
            x_mid = nor_mean
            x_left = nor_mean - nor_max_dev * 1.1
            x_right = nor_mean + nor_max_dev * 1.1

            # Y轴中轴线（SOR均值）
            sor_max_dev = max(sor_mean - np.nanmin(sor_vals), np.nanmax(sor_vals) - sor_mean)
            y_mid = sor_mean
            y_bottom = sor_mean - sor_max_dev * 1.1
            y_top = sor_mean + sor_max_dev * 1.1

            ax.set_xlim(x_left, x_right)
            ax.set_ylim(y_bottom, y_top)

            # 绘制中轴线
            ax.axvline(x=x_mid, color='#FF6B6B', linestyle='-', linewidth=2.5, alpha=0.9,
                      label=f'NOR基准线: {nor_mean:.3f}')
            ax.axhline(y=y_mid, color='#4ECDC4', linestyle='-', linewidth=2.5, alpha=0.9,
                      label=f'SOR基准线: {sor_mean:.3f}')

            # 1:1参考线
            max_val = max(np.nanmax(nor_vals), np.nanmax(sor_vals))
            min_val = min(np.nanmin(nor_vals), np.nanmin(sor_vals))
            if max_val > min_val:
                ax.plot([min_val, max_val], [min_val, max_val], 'k--', linewidth=1.5, alpha=0.5, label='1:1线')

            # 统计信息
            stats_text = f'样本数: {len(valid_data)}\n'
            stats_text += f'NOR均值: {nor_mean:.3f}\n'
            stats_text += f'SOR均值: {sor_mean:.3f}'
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9),
                   verticalalignment='top', fontsize=10)

            ax.set_xlabel('NOR (硝酸盐氧化率)', fontsize=12, fontweight='bold', fontproperties=chinese_font)
            ax.set_ylabel('SOR (硫酸盐氧化率)', fontsize=12, fontweight='bold', fontproperties=chinese_font)
            ax.set_title('SOR vs NOR 散点图（评估二次生成）\n（圆点大小和颜色：PM2.5浓度）',
                        fontsize=14, fontweight='bold', pad=15, fontproperties=chinese_font)
            ax.grid(True, alpha=0.3, linestyle='--', zorder=0)
            ax.set_axisbelow(True)

            # 合并图例
            all_handles = legend_elements + ax.get_legend_handles_labels()[0]
            ax.legend(handles=all_handles, loc='upper right', fontsize=9, framealpha=0.9,
                     ncol=1, labelspacing=0.6, prop=chinese_font)

            plt.tight_layout()

            chart_id = f"sor_nor_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(fig, chart_id, "SOR vs NOR 散点图", "sor_nor_scatter", "pm_soluble_ion_analysis", source_data_id=source_data_id)

        except Exception as e:
            logger.warning(f"生成SOR/NOR图失败: {e}")
            return None

    def generate_charge_balance_chart(
        self,
        cation_total: pd.Series,
        anion_total: pd.Series,
        source_data_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """生成阴阳离子电荷平衡图（带回归线和95%置信区间）"""
        try:
            from scipy import stats
            from sklearn.linear_model import LinearRegression

            valid_mask = cation_total.notna() & anion_total.notna()
            cation_vals = cation_total[valid_mask].values
            anion_vals = anion_total[valid_mask].values

            if len(cation_vals) == 0 or len(anion_vals) < 3:
                return None

            fig, ax = plt.subplots(figsize=(10, 8))

            # 中文字体
            chinese_font = _chinese_font if _chinese_font else None

            # 散点图
            ax.scatter(anion_vals, cation_vals, s=80, alpha=0.6, color='#2E86AB',
                      edgecolors='white', linewidths=0.8, label=f'样本点（n={len(cation_vals)}）')

            # 回归分析
            X = anion_vals.reshape(-1, 1)
            y = cation_vals
            model = LinearRegression()
            model.fit(X, y)
            y_pred = model.predict(X)

            # 回归线
            max_val = max(np.nanmax(cation_vals), np.nanmax(anion_vals))
            min_val = min(np.nanmin(cation_vals), np.nanmin(anion_vals))
            x_line = np.linspace(min_val, max_val, 100)
            y_line = model.predict(x_line.reshape(-1, 1))

            slope = model.coef_[0]
            intercept = model.intercept_
            r_value, p_value = stats.pearsonr(anion_vals, cation_vals)
            r2 = r_value ** 2

            # 绘制回归线
            ax.plot(x_line, y_line, color='#E74C3C', linewidth=2.5,
                   label=f'回归线：y={slope:.3f}x+{intercept:.3f}')

            # 95%置信区间（Bootstrap）
            if len(anion_vals) > 5:
                n_bootstrap = 1000
                np.random.seed(42)
                boot_preds = []
                for _ in range(n_bootstrap):
                    idx = np.random.choice(len(X), len(X), replace=True)
                    X_boot = X[idx]
                    y_boot = y[idx]
                    model_boot = LinearRegression()
                    model_boot.fit(X_boot, y_boot)
                    boot_preds.append(model_boot.predict(x_line.reshape(-1, 1)))
                boot_preds = np.array(boot_preds)
                ci_lower = np.percentile(boot_preds, 5, axis=0)
                ci_upper = np.percentile(boot_preds, 95, axis=0)
                ax.fill_between(x_line, ci_lower, ci_upper, alpha=0.2, color='#E74C3C',
                               label='95%置信区间')

            # 理想平衡线（1:1）
            if max_val > min_val:
                ax.plot([min_val, max_val], [min_val, max_val], 'k--', linewidth=1.5,
                       label='理想平衡线（y=x）')

            # 统计信息
            stats_text = (f'相关系数 R = {r_value:.3f}\n'
                         f'决定系数 R$2$ = {r2:.3f}\n'
                         f'斜率 = {slope:.3f}\n'
                         f'截距 = {intercept:.3f}\n'
                         f'显著性P值 = {p_value:.4f}')
            ax.text(0.05, 0.95, stats_text, transform=ax.transAxes,
                   bbox=dict(boxstyle="round,pad=0.4", facecolor='white', alpha=0.9),
                   verticalalignment='top', fontsize=10, fontproperties=chinese_font)

            ax.set_xlabel(r'阴离子总电荷 ($\mu$eq/m$^3$)', fontsize=12, fontweight='bold', fontproperties=chinese_font)
            ax.set_ylabel(r'阳离子总电荷 ($\mu$eq/m$^3$)', fontsize=12, fontweight='bold', fontproperties=chinese_font)
            ax.set_title(f'阴阳离子电荷平衡散点图（R$2$={r2:.3f}, p<0.001）',
                        fontsize=14, fontweight='bold', pad=15, fontproperties=chinese_font)
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.legend(loc='upper left', bbox_to_anchor=(0.5, 0.15), fontsize=9, framealpha=0.9, prop=chinese_font)
            ax.set_xlim(0, max_val * 1.1)
            ax.set_ylim(0, max_val * 1.1)

            plt.tight_layout()

            chart_id = f"charge_balance_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(fig, chart_id, "阴阳离子电荷平衡散点图", "charge_balance", "pm_soluble_ion_analysis", source_data_id=source_data_id)

        except Exception as e:
            logger.warning(f"生成电荷平衡图失败: {e}")
            return None

    # ==================== 地壳元素分析图表 ====================

    def generate_crustal_timeseries_chart(
        self,
        dust_df: pd.DataFrame,
        crustal_series: pd.Series,
        source_data_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """生成地壳元素氧化物浓度时序图"""
        try:
            if dust_df.empty:
                return None

            if isinstance(dust_df.index, pd.DatetimeIndex):
                x_labels = dust_df.index.strftime('%m/%d %H:%M')
                x = np.arange(len(dust_df))
            else:
                x_labels = [f't{i}' for i in range(len(dust_df))]
                x = np.arange(len(dust_df))

            valid_mask = dust_df.notna().any(axis=1)
            valid_indices = x[valid_mask]

            if len(valid_indices) == 0:
                return None

            fig, ax = plt.subplots(figsize=(14, 8))
            colors = plt.cm.Set2(np.linspace(0, 1, len(dust_df.columns) + 1))

            # 中文字体
            chinese_font = _chinese_font if _chinese_font else None

            for i, col in enumerate(dust_df.columns):
                valid_mask_col = dust_df[col].notna()
                valid_idx_col = x[valid_mask_col]
                valid_vals = dust_df[col].values[valid_mask_col]
                if len(valid_idx_col) > 0:
                    ax.plot(valid_idx_col, valid_vals, color=colors[i],
                           linewidth=2, marker='o', markersize=4, label=col,
                           alpha=0.85, markeredgecolor='white', markeredgewidth=0.5)

            valid_crustal_mask = crustal_series.notna()
            valid_crustal_idx = x[valid_crustal_mask]
            valid_crustal_vals = crustal_series.values[valid_crustal_mask]

            if len(valid_crustal_idx) > 0:
                ax.plot(valid_crustal_idx, valid_crustal_vals, color=colors[-1],
                       linewidth=2.5, linestyle='--', marker='s', markersize=5,
                       label='地壳物质总量', alpha=0.9)

            ax.set_xlabel('时间', fontsize=12, fontweight='bold', fontproperties=chinese_font)
            ax.set_ylabel(r'氧化物浓度 ($\mu$g/m$^3$)', fontsize=12, fontweight='bold', fontproperties=chinese_font)
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.legend(loc='upper right', fontsize=10, framealpha=0.9, ncol=2, prop=chinese_font)

            if len(x) > 24:
                tick_positions = [i for i in range(len(x)) if x[i] % 6 == 0]
                tick_labels = [x_labels[i] if i < len(x_labels) else '' for i in tick_positions]
                plt.xticks(tick_positions, tick_labels, rotation=45, ha='right', fontsize=9)
            else:
                step = max(1, len(valid_indices) // 10)
                plt.xticks(valid_indices[::step],
                          [x_labels[i] if i < len(x_labels) else '' for i in valid_indices[::step]],
                          rotation=45, ha='right', fontsize=9)

            plt.title('地壳元素氧化物浓度时序变化', fontsize=14, fontweight='bold', pad=15, fontproperties=chinese_font)
            plt.tight_layout()

            chart_id = f"crustal_timeseries_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(fig, chart_id, "地壳元素氧化物浓度时序变化", "crustal_timeseries", "pm_crustal_analysis", source_data_id=source_data_id)

        except Exception as e:
            logger.warning(f"生地壳元素时序图失败: {e}")
            return None

    def generate_crustal_boxplot_chart(
        self,
        dust_df: pd.DataFrame,
        source_data_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """生地壳元素氧化物浓度分布箱线图"""
        try:
            if dust_df.empty:
                return None

            boxplot_data = []
            labels = []
            for col in dust_df.columns:
                col_data = dust_df[col].dropna().values
                if len(col_data) > 0:
                    boxplot_data.append(col_data)
                    labels.append(col)

            if len(boxplot_data) == 0:
                return None

            fig, ax = plt.subplots(figsize=(12, 8))

            # 中文字体
            chinese_font = _chinese_font if _chinese_font else None

            bp = ax.boxplot(boxplot_data, labels=labels, patch_artist=True,
                           medianprops={'color': 'red', 'linewidth': 2},
                           flierprops={'marker': 'o', 'markerfacecolor': 'gray', 'markersize': 5})

            colors = plt.cm.Set2(np.linspace(0, 1, len(boxplot_data)))
            for patch, color in zip(bp['boxes'], colors):
                patch.set_facecolor(color)
                patch.set_alpha(0.7)

            ax.set_xlabel('地壳元素氧化物', fontsize=12, fontweight='bold', fontproperties=chinese_font)
            ax.set_ylabel(r'浓度 ($\mu$g/m$^3$)', fontsize=12, fontweight='bold', fontproperties=chinese_font)
            ax.grid(True, alpha=0.3, linestyle='--', axis='y')
            plt.xticks(rotation=45, ha='right', fontsize=10)

            stats_text = f'元素数: {len(labels)}\n'
            means = [np.mean(data) for data in boxplot_data]
            stats_text += r'平均浓度: %.2f $\mu$g/m$^3$' % np.mean(means)
            ax.text(0.95, 0.95, stats_text, transform=ax.transAxes,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.8),
                   verticalalignment='top', horizontalalignment='right', fontsize=11, fontproperties=chinese_font)

            plt.title('地壳元素氧化物浓度分布', fontsize=14, fontweight='bold', pad=15, fontproperties=chinese_font)
            plt.tight_layout()

            chart_id = f"crustal_boxplot_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(fig, chart_id, "地壳元素氧化物浓度分布", "crustal_boxplot", "pm_crustal_analysis", source_data_id=source_data_id)

        except Exception as e:
            logger.warning(f"生地壳元素箱线图失败: {e}")
            return None

    # ==================== 微量元素分析图表 ====================

    def generate_trace_enrichment_chart(
        self,
        divided: pd.DataFrame,
        source_data_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """生成微量元素富集因子柱状图"""
        try:
            if divided is None or divided.empty:
                return None

            avg = divided.mean().sort_values(ascending=False)

            fig, ax = plt.subplots(figsize=(12, 6))

            colors = plt.cm.viridis(np.linspace(0, 1, len(avg)))
            bars = ax.bar(range(len(avg)), avg.values, color=colors, alpha=0.8, edgecolor='black', linewidth=0.5)

            ax.set_xlabel('元素', fontsize=12, fontweight='bold')
            ax.set_ylabel('富集因子（相对于Taylor丰度）', fontsize=12, fontweight='bold')
            ax.set_xticks(range(len(avg)))
            ax.set_xticklabels(avg.index, rotation=45, ha='right', fontsize=10)
            ax.grid(True, alpha=0.3, axis='y')

            # 添加数值标签
            for bar, val in zip(bars, avg.values):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                       f'{val:.2f}', ha='center', va='bottom', fontsize=9)

            plt.title('微量元素富集因子对比', fontsize=14, fontweight='bold', pad=15)
            plt.tight_layout()

            chart_id = f"trace_enrichment_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(fig, chart_id, "微量元素富集因子（相对于Taylor丰度）", "trace_enrichment_bar", "pm_trace_analysis", source_data_id=source_data_id)

        except Exception as e:
            logger.warning(f"生成微量元素富集图失败: {e}")
            return None

    # ==================== 重构分析图表 ====================

    def generate_reconstruction_timeseries_chart(
        self,
        df_out: pd.DataFrame,
        available_cols: List[str],
        timestamps: List[str],
        source_data_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """生成PM2.5七大组分重构时序图"""
        try:
            if not available_cols or df_out.empty:
                return None

            fig, ax = plt.subplots(figsize=(14, 8))
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2']

            for i, col in enumerate(available_cols):
                if col in df_out.columns:
                    data = df_out[col].values
                    ax.plot(range(len(data)), data, linewidth=2, marker='o', markersize=3,
                           label=col, color=colors[i % len(colors)], alpha=0.8)

            ax.set_xlabel('时间', fontsize=12, fontweight='bold')
            ax.set_ylabel(r'浓度 ($\mu$g/m$^3$)', fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.legend(loc='upper right', fontsize=10, framealpha=0.9, ncol=2)

            # 设置X轴标签
            step = max(1, len(timestamps) // 10)
            ax.set_xticks(range(0, len(timestamps), step))
            ax.set_xticklabels([timestamps[i] if i < len(timestamps) else '' for i in range(0, len(timestamps), step)],
                              rotation=45, ha='right', fontsize=9)

            plt.title('PM2.5 七大组分重构时序图', fontsize=14, fontweight='bold', pad=15)
            plt.tight_layout()

            chart_id = f"reconstruction_timeseries_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return self._create_visual(fig, chart_id, "PM2.5 七大组分重构时序图", "reconstruction_timeseries", "pm_reconstruction", source_data_id=source_data_id)

        except Exception as e:
            logger.warning(f"生成重构时序图失败: {e}")
            return None

    # ==================== 一键生成所有图表 ====================

    def generate_carbon_charts(
        self,
        result_df: pd.DataFrame,
        pm25: Optional[pd.Series] = None,
        source_data_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """一键生成碳组分分析所有图表"""
        visuals = []

        logger.info(
            "[ParticulateVisualizer] generate_carbon_charts 开始",
            result_df_columns=list(result_df.columns),
            has_pm25=pm25 is not None,
            result_df_shape=result_df.shape if hasattr(result_df, 'shape') else None
        )

        bar_chart = self.generate_carbon_bar_chart(result_df, pm25, source_data_id=source_data_id)
        logger.info(
            "[ParticulateVisualizer] generate_carbon_bar_chart 结果",
            has_chart=bar_chart is not None
        )
        if bar_chart:
            visuals.append(bar_chart)

        scatter_chart = self.generate_ec_oc_scatter_chart(result_df, source_data_id=source_data_id)
        logger.info(
            "[ParticulateVisualizer] generate_ec_oc_scatter_chart 结果",
            has_chart=scatter_chart is not None
        )
        if scatter_chart:
            visuals.append(scatter_chart)

        logger.info(
            "[ParticulateVisualizer] generate_carbon_charts 完成",
            total_visuals=len(visuals)
        )
        return visuals

    def generate_soluble_charts(
        self,
        df: pd.DataFrame,
        available_ions: List[str],
        ternary_df: pd.DataFrame,
        nor_series: Optional[pd.Series],
        sor_series: Optional[pd.Series],
        cation_total: pd.Series,
        anion_total: pd.Series,
        pm25: Optional[pd.Series] = None,
        source_data_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """一键生成水溶性离子分析所有图表"""
        visuals = []

        logger.info(
            "[ParticulateVisualizer] generate_soluble_charts 开始",
            df_columns=list(df.columns),
            available_ions=available_ions,
            ternary_df_columns=list(ternary_df.columns) if isinstance(ternary_df, pd.DataFrame) else None,
            nor_not_none=nor_series is not None,
            sor_not_none=sor_series is not None,
            cation_not_none=cation_total is not None,
            anion_not_none=anion_total is not None,
            df_shape=df.shape if hasattr(df, 'shape') else None
        )

        ion_chart = self.generate_ion_timeseries_chart(df, available_ions, pm25, source_data_id=source_data_id)
        logger.info(
            "[ParticulateVisualizer] generate_ion_timeseries_chart 结果",
            has_chart=ion_chart is not None
        )
        if ion_chart:
            visuals.append(ion_chart)

        ternary_chart = self.generate_ternary_chart(ternary_df, pm25, source_data_id=source_data_id)
        logger.info(
            "[ParticulateVisualizer] generate_ternary_chart 结果",
            has_chart=ternary_chart is not None,
            has_valid_data=isinstance(ternary_df, pd.DataFrame) and 'x' in ternary_df.columns and not ternary_df['x'].isna().all()
        )
        if ternary_chart:
            visuals.append(ternary_chart)

        sor_nor_chart = self.generate_sor_nor_chart(nor_series, sor_series, pm25, source_data_id=source_data_id)
        logger.info(
            "[ParticulateVisualizer] generate_sor_nor_chart 结果",
            has_chart=sor_nor_chart is not None
        )
        if sor_nor_chart:
            visuals.append(sor_nor_chart)

        balance_chart = self.generate_charge_balance_chart(cation_total, anion_total, source_data_id=source_data_id)
        logger.info(
            "[ParticulateVisualizer] generate_charge_balance_chart 结果",
            has_chart=balance_chart is not None
        )
        if balance_chart:
            visuals.append(balance_chart)

        logger.info(
            "[ParticulateVisualizer] generate_soluble_charts 完成",
            total_visuals=len(visuals)
        )
        return visuals

    def generate_crustal_charts(
        self,
        dust_df: pd.DataFrame,
        crustal_series: pd.Series,
        source_data_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """一键生成地壳元素分析所有图表"""
        visuals = []

        logger.info(
            "[ParticulateVisualizer] generate_crustal_charts 开始",
            dust_df_columns=list(dust_df.columns) if isinstance(dust_df, pd.DataFrame) else None,
            dust_df_empty=dust_df.empty if isinstance(dust_df, pd.DataFrame) else True,
            crustal_not_none=crustal_series is not None
        )

        ts_chart = self.generate_crustal_timeseries_chart(dust_df, crustal_series, source_data_id=source_data_id)
        logger.info(
            "[ParticulateVisualizer] generate_crustal_timeseries_chart 结果",
            has_chart=ts_chart is not None
        )
        if ts_chart:
            visuals.append(ts_chart)

        box_chart = self.generate_crustal_boxplot_chart(dust_df, source_data_id=source_data_id)
        logger.info(
            "[ParticulateVisualizer] generate_crustal_boxplot_chart 结果",
            has_chart=box_chart is not None
        )
        if box_chart:
            visuals.append(box_chart)

        logger.info(
            "[ParticulateVisualizer] generate_crustal_charts 完成",
            total_visuals=len(visuals)
        )
        return visuals

    def generate_trace_charts(
        self,
        divided: pd.DataFrame,
        source_data_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """一键生成微量元素分析所有图表"""
        visuals = []

        enrichment_chart = self.generate_trace_enrichment_chart(divided, source_data_id=source_data_id)
        if enrichment_chart:
            visuals.append(enrichment_chart)

        return visuals

    def generate_reconstruction_charts(
        self,
        df_out: pd.DataFrame,
        available_cols: List[str],
        timestamps: List[str],
        source_data_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """一键生成重构分析所有图表"""
        visuals = []

        ts_chart = self.generate_reconstruction_timeseries_chart(df_out, available_cols, timestamps, source_data_id=source_data_id)
        if ts_chart:
            visuals.append(ts_chart)

        return visuals
